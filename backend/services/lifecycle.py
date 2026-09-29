"""Soft delete and restore, in one place (§7.12 lifecycle, R2-D2, R2-S5, Q4).

`soft_delete` sets is_active, deleted_at and deleted_by together, so "revoked at / by" (§5.3) is
never half-recorded. `retire` is what every DELETE route calls: it refuses while an active row
still references the object, naming the blockers — NOTHING CASCADES. `restore` refuses while a
parent the object references is inactive.

DEPENDENTS / PARENTS are DERIVED from Base.metadata, never hand-kept: they are the FK_LIVENESS
list of §5.4.15. tests/test_lifecycle.py proves every FK between business tables is covered.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from models import (Base, BfcNode, BusinessRequirement, DataEntity, DataField, ExternalEntity,
                    OrgRole, OrgUnit)
from services import audit, errors

# §5.4.15 exclusions: tenancy and identity are not liveness parents, and a code is retired
# through code_master.maintain (R2-D8), never blocked by the rows that use it.
EXCLUDED_TARGETS = frozenset({"app_user", "project", "program", "client", "code_master"})
# Guard columns carry the target's is_active / is_process; the FK they sit in duplicates the
# plain (id, project_id) FK beside it, so they are ignored when matching rows.
GUARD_TARGET_COLUMNS = frozenset({"is_active", "is_process"})

RESTORABLE = (BfcNode, BusinessRequirement, DataEntity, DataField, ExternalEntity, OrgUnit, OrgRole)

# How a row is named in a 409, so the consultant can find it (§7.12).
LABELS = {
    "bfc_node": ("BFC node", lambda r: f"{r.hier_code} {r.node_name}"),
    "business_requirement": ("Business requirement", lambda r: r.br_number),
    "data_entity": ("Data entity", lambda r: f"{r.de_number} {r.de_name}"),
    "data_field": ("Data field", lambda r: r.field_name),
    "external_entity": ("External party", lambda r: f"{r.ext_number} {r.ext_name}"),
    "org_unit": ("Org unit", lambda r: r.org_unit_code),
    "org_role": ("Org role", lambda r: r.org_role_code),
    "bfc_node_data_entity": ("Step data", lambda r: f"step I/O {r.direction}"),
    "br_data_entity": ("Requirement data", lambda r: f"CRUD {r.crud_code}"),
    "bfc_node_org_role": ("Step role", lambda r: r.raci_behaviour.title()),
    "br_org_role": ("Requirement role", lambda r: r.raci_behaviour.title()),
    "bfc_node_external_flow": ("External flow", lambda r: f"flow {r.direction}"),
}


@dataclass(frozen=True)
class Link:
    """One FK between business tables: child.<child_cols> = parent.<parent_cols>."""
    child: type
    parent: type
    pairs: tuple[tuple[str, str], ...]          # (child column, parent column)


def _mapper_for(table_name: str):
    for m in Base.registry.mappers:
        if m.local_table.name == table_name:
            return m.class_
    return None


def _links() -> list[Link]:
    seen, out = set(), []
    for table in Base.metadata.sorted_tables:
        if "is_active" not in table.c:
            continue
        child = _mapper_for(table.name)
        for fk in table.foreign_key_constraints:
            target = fk.referred_table
            if target.name in EXCLUDED_TARGETS or "is_active" not in target.c:
                continue
            pairs = tuple(sorted(
                (e.parent.name, e.column.name) for e in fk.elements
                if e.column.name not in GUARD_TARGET_COLUMNS))
            key = (table.name, target.name, pairs)
            if key not in seen:
                seen.add(key)
                out.append(Link(child, _mapper_for(target.name), pairs))
    return out


LINKS = _links()


def dependents_of(model: type) -> list[Link]:
    return [ln for ln in LINKS if ln.parent is model]


def parents_of(model: type) -> list[Link]:
    return [ln for ln in LINKS if ln.child is model]


def _label(obj) -> str:
    name, key = LABELS.get(obj.__table__.name, (obj.__table__.name, lambda r: ""))
    return f"{name} {key(obj)}".strip()


def active_dependents(db: Session, obj) -> dict[str, tuple[list, int]]:
    """kind → (first 10 blocking rows, total count)."""
    found: dict[str, tuple[list, int]] = {}
    for ln in dependents_of(type(obj)):
        cond = and_(*(getattr(ln.child, c) == getattr(obj, p) for c, p in ln.pairs),
                    ln.child.is_active)
        if ln.child is type(obj):
            cond = and_(cond, ln.child.__mapper__.primary_key[0] != _pk(obj))
        n = db.scalar(select(func.count()).select_from(ln.child).where(cond))
        if n:
            kind = LABELS.get(ln.child.__table__.name, (ln.child.__table__.name,))[0]
            rows, total = found.get(kind, ([], 0))
            found[kind] = (rows + list(db.scalars(select(ln.child).where(cond).limit(10))), total + n)
    return found


def soft_delete(obj, actor_id: int) -> None:
    obj.is_active = False
    obj.deleted_at = datetime.now(UTC)
    obj.deleted_by = actor_id


def check_version(obj, row_version: int) -> None:
    if obj.row_version != row_version:
        raise HTTPException(409, errors.CONFLICT, headers=errors.STALE_HEADERS)


def check_live(obj, row_version: int) -> None:
    """Every update: current version, and not retired (edit a retired row by restoring it)."""
    check_version(obj, row_version)
    if not obj.is_active:
        raise HTTPException(409, f"{_label(obj)} is retired. Restore it first.")


def child_of(db: Session, model, link_id: int, owner_col: str, owner_id: int):
    """A link row addressed under its owner. Anything else is 404, never a cross-owner write."""
    row = db.get(model, link_id)
    if row is None or getattr(row, owner_col) != owner_id:
        raise HTTPException(404, "Not found")
    return row


def unlink(db: Session, actor_id: int, row, row_version: int) -> None:
    """Remove a link row (soft), audited like every DELETE. Callers check their own blockers."""
    check_version(row, row_version)
    if not row.is_active:
        raise HTTPException(409, f"{_label(row)} is already removed")
    soft_delete(row, actor_id)
    row.updated_by = actor_id
    audit.record(db, "RECORD_DELETED", actor_id=actor_id, project_id=row.project_id,
                 target_table=row.__table__.name, target_id=_pk(row), detail={"label": _label(row)})
    db.commit()


def relink(db: Session, actor_id: int, row) -> None:
    """Re-linking a removed link restores the same row, never a new one (S1-7). No commit."""
    row.is_active, row.deleted_at, row.deleted_by = True, None, None
    row.updated_by = actor_id
    audit.record(db, "RECORD_RESTORED", actor_id=actor_id, project_id=row.project_id,
                 target_table=row.__table__.name, target_id=_pk(row), detail={"label": _label(row)})


def retire(db: Session, actor_id: int, obj, row_version: int) -> None:
    """The one DELETE. Refuses with the blockers named (Q4); commits on success."""
    check_version(obj, row_version)
    if not obj.is_active:
        raise HTTPException(409, f"{_label(obj)} is already retired")
    blockers = active_dependents(db, obj)
    if blockers:
        parts = []
        for kind, (rows, total) in blockers.items():
            names = ", ".join(LABELS.get(r.__table__.name, ("", lambda _: "?"))[1](r) for r in rows[:10])
            more = f" (+{total - 10} more)" if total > 10 else ""
            parts.append(f"{kind}: {names}{more}")
        raise HTTPException(409, "Retire these first: " + "; ".join(parts))
    soft_delete(obj, actor_id)
    obj.updated_by = actor_id
    audit.record(db, "RECORD_DELETED", actor_id=actor_id, project_id=obj.project_id,
                 target_table=obj.__table__.name, target_id=_pk(obj),
                 detail={"label": _label(obj)})
    db.commit()


def inactive_parents(db: Session, obj) -> list:
    out = []
    for ln in parents_of(type(obj)):
        values = [getattr(obj, c) for c, _ in ln.pairs]
        if any(v is None for v in values):
            continue                                       # a nullable FK is a parent only where set
        cond = and_(*(getattr(ln.parent, p) == getattr(obj, c) for c, p in ln.pairs))
        parent = db.scalars(select(ln.parent).where(cond)).one_or_none()
        if parent is not None and not parent.is_active and parent is not obj:
            out.append(parent)
    return out


def restore(db: Session, actor_id: int, obj, before_activate=None) -> None:
    """Un-delete a RESTORABLE row (R2-S5). 409 while a parent is inactive (R2-D2)."""
    if not isinstance(obj, RESTORABLE):
        raise HTTPException(404, "Not found")
    if obj.is_active:
        raise HTTPException(409, f"{_label(obj)} is not retired")
    blocked = inactive_parents(db, obj)
    if blocked:
        raise HTTPException(409, f"Restore {_label(blocked[0])} first")
    if before_activate:
        before_activate(obj)
    obj.is_active, obj.deleted_at, obj.deleted_by = True, None, None
    obj.updated_by = actor_id
    audit.record(db, "RECORD_RESTORED", actor_id=actor_id, project_id=obj.project_id,
                 target_table=obj.__table__.name, target_id=_pk(obj),
                 detail={"label": _label(obj)})
    db.commit()


def _pk(obj) -> int:
    return getattr(obj, obj.__mapper__.primary_key[0].name)
