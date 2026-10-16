"""Business requirements (§7.3, D-2, D-24). A BR is never created from a route: it appears with
its process step (create_node / mark_process) and the consultant edits it."""
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BfcNode, BrDataEntity, BrDataField, BusinessRequirement, DataField, Project
from services import errors, numbering, step_io
from services.code_master import resolve, validate_required_code
from services import lifecycle

log = logging.getLogger("vb")

CRUD = ("C", "R", "U", "D")
# D-59 (slice11_schema §1.2): business_logic / output_expectation are read-only legacy, copied once into lines by
# seeds.backfill_br_lines; the bodies refuse them (BrPatch forbids extra fields).
EDITABLE = ("br_statement",)
# Set only by the baseline freeze, never chosen by a person (Ben, 2026-09-29, S1-8).
SYSTEM_SET_STATUSES = frozenset({"BASELINED", "SUPERSEDED"})


def create_br(db: Session, actor_id: int, node: BfcNode) -> BusinessRequirement:
    """Same transaction as the node change; never commits. Exactly one live BR per node (D-2)."""
    if not node.is_process:
        raise HTTPException(422, "A business requirement attaches to a process step")
    draft = next((c for c in resolve(db, node.project_id, "BR_STATUS") if c.code == "DRAFT"), None)
    if draft is None:                                          # L6: detail in the log only
        log.error("BR_STATUS/DRAFT missing for project %s", node.project_id)
        raise HTTPException(500, "Something went wrong.")
    br = BusinessRequirement(project_id=node.project_id, bfc_node_id=node.bfc_node_id,
                             br_number=numbering.next_number(db, node.project_id, "BR"),
                             status_code_id=draft.code_id, created_by=actor_id)
    db.add(br)
    db.flush()
    return br


def list_brs(db: Session, project_id: int, include_retired: bool = False) -> list[BusinessRequirement]:
    q = select(BusinessRequirement).where(BusinessRequirement.project_id == project_id)
    if not include_retired:
        q = q.where(BusinessRequirement.is_active)
    return list(db.scalars(q.order_by(BusinessRequirement.br_number)))


def update_br(db: Session, actor_id: int, br: BusinessRequirement, row_version: int,
              fields: dict, status_code: str | None) -> BusinessRequirement:
    lifecycle.check_live(br, row_version)
    for k in EDITABLE:
        if k in fields:
            setattr(br, k, fields[k])
    if status_code is not None:
        if status_code in SYSTEM_SET_STATUSES:
            raise HTTPException(422, f"{status_code.title()} is set by the baseline freeze, not by hand")
        br.status_code_id = validate_required_code(db, br.project_id, "BR_STATUS", status_code,
                                                   "status_code").code_id
    br.updated_by = actor_id
    db.commit()
    db.refresh(br)                 # reload the code relationship with the new id
    return br


def _lock_live(db: Session, br: BusinessRequirement) -> None:
    lifecycle.lock_for_share(db, db.get(BfcNode, br.bfc_node_id))    # SR-5: the step first,
    lifecycle.lock_for_share(db, br)                                 # then the BR (sara M2)
    if not br.is_active:
        raise HTTPException(409, f"{br.br_number} is retired. Restore it first.")


def _link(db: Session, actor_id: int, br: BusinessRequirement, data_entity_id: int, crud_code: str,
          usage_note: str | None) -> BrDataEntity:
    """One entity-level tick and the step I/O that licenses it (D-24). No lock, no commit: the callers own both."""
    if crud_code not in CRUD:
        raise HTTPException(422, "crud_code must be one of C, R, U, D")
    node = db.get(BfcNode, br.bfc_node_id)
    step_io.ensure_step_io(db, actor_id, node, data_entity_id, "I" if crud_code == "R" else "O")
    row = db.scalars(select(BrDataEntity).where(
        BrDataEntity.br_id == br.br_id, BrDataEntity.data_entity_id == data_entity_id,
        BrDataEntity.crud_code == crud_code)).one_or_none()
    if row is None:
        row = BrDataEntity(project_id=br.project_id, br_id=br.br_id, bfc_node_id=br.bfc_node_id,
                           data_entity_id=data_entity_id, crud_code=crud_code,
                           usage_note=usage_note, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{br.br_number} already has {crud_code} on that entity")
    else:                                                     # re-link restores (S1-7)
        lifecycle.relink(db, actor_id, row)
        if usage_note is not None:                            # sara L1: re-ticking keeps the note it had
            row.usage_note = usage_note
    db.flush()
    return row


def link_data_entity(db: Session, actor_id: int, br: BusinessRequirement, data_entity_id: int,
                     crud_code: str, usage_note: str | None) -> BrDataEntity:
    """D-24: the step I/O that licenses the CRUD is created in the same transaction."""
    _lock_live(db, br)
    row = _link(db, actor_id, br, data_entity_id, crud_code, usage_note)
    db.commit()
    db.refresh(row)
    return row


def list_data_links(db: Session, br: BusinessRequirement) -> list[BrDataEntity]:
    return list(db.scalars(select(BrDataEntity).where(BrDataEntity.br_id == br.br_id,
                                                      BrDataEntity.is_active)))


def _live_ticks(db: Session, br_id: int) -> list[BrDataField]:
    return list(db.scalars(select(BrDataField).where(BrDataField.br_id == br_id, BrDataField.is_active)))


def unlink_data_entity(db: Session, actor_id: int, row: BrDataEntity, row_version: int) -> None:
    """The step I/O stays: it is a fact about the step, removed on its own (§7.3). An entity action whose attribute
    ticks are still live is refused, naming them (D-60b): the CRUD grid removes both in one save."""
    held = [t for t in _live_ticks(db, row.br_id)
            if (t.data_entity_id, t.crud_code) == (row.data_entity_id, row.crud_code)]
    if held:
        names = ", ".join(sorted(t.field_row.field_name for t in held))
        raise HTTPException(409, f"Untick these attributes first ({row.crud_code}): {names}")
    lifecycle.unlink(db, actor_id, row, row_version)


# ---- the CRUD grid: entity and attribute ticks in one save (D-60b, slice11_schema §2) ------------------------
ATTRIBUTE_CRUD = ("C", "R", "U")          # Delete stays entity-level (Q-8)


def grid(db: Session, br: BusinessRequirement) -> dict:
    """The live entity and attribute ticks, and the information lines: under FULL depth an entity action with no
    attribute ticked (`br_entity_without_attributes`); never a warning, nothing under KEYS_ONLY (Q-9)."""
    entities, ticks = list_data_links(db, br), _live_ticks(db, br.br_id)
    info = []
    project = db.get(Project, br.project_id)
    if project.data_model_depth == "FULL":
        ticked = {(t.data_entity_id, t.crud_code) for t in ticks}
        info = [{"code": "br_entity_without_attributes", "data_entity_id": e.data_entity_id, "crud_code": e.crud_code}
                for e in entities if e.crud_code in ATTRIBUTE_CRUD and (e.data_entity_id, e.crud_code) not in ticked]
    return {"entities": entities, "attributes": ticks, "info": info}


def save_grid(db: Session, actor_id: int, br: BusinessRequirement, entity_ticks: set[tuple[int, str]],
              attribute_ticks: dict[tuple[int, str], str | None], known: dict[tuple[str, int], int]) -> dict:
    """The whole grid as the person left it, in ONE transaction (D-60b). `known` is every live row the screen was
    showing, by (table, id) → row_version: a row added, changed or removed by someone else since is a 409, never
    overwritten. Order: attribute ticks retired first (nothing cascades), then entity ticks, then attributes added —
    the licence FK refuses an attribute tick whose entity action is not live."""
    _lock_live(db, br)
    live_e = {(r.data_entity_id, r.crud_code): r for r in list_data_links(db, br)}
    live_a = {(r.data_field_id, r.crud_code): r for r in _live_ticks(db, br.br_id)}
    now = {("br_data_entity", r.br_data_entity_id): r.row_version for r in live_e.values()}
    now |= {("br_data_field", r.br_data_field_id): r.row_version for r in live_a.values()}
    if now != known:
        raise HTTPException(409, errors.CONFLICT, headers=errors.STALE_HEADERS)
    if any(c not in CRUD for _, c in entity_ticks):
        raise HTTPException(422, "crud_code must be one of C, R, U, D")
    fields = {}
    for field_id, crud in sorted(attribute_ticks):            # sorted: field locks are taken in one order
        if crud not in ATTRIBUTE_CRUD:
            raise HTTPException(422, "An attribute takes C, R or U; Delete stays on the entity")
        f = fields.get(field_id) or db.get(DataField, field_id)
        if f is None or f.project_id != br.project_id:
            raise HTTPException(404, "Not found")
        if field_id not in fields and (field_id, crud) not in live_a:
            lifecycle.lock_for_share(db, f)                   # sara M1 (SR-5): a field retire waits for this save
        if not f.is_active and (field_id, crud) not in live_a:
            raise HTTPException(409, f"{lifecycle.label(f)} is retired. Restore it first.")
        if (f.data_entity_id, crud) not in entity_ticks:
            raise HTTPException(422, f"Tick {crud} on the entity before ticking it on {f.field_name}")
        fields[field_id] = f
    for key, row in live_a.items():
        if key not in attribute_ticks:
            lifecycle.retire_row(db, actor_id, row)
    db.flush()
    for key, row in live_e.items():
        if key not in entity_ticks:
            lifecycle.retire_row(db, actor_id, row)
    db.flush()
    for de_id, crud in sorted(entity_ticks - live_e.keys()):
        _link(db, actor_id, br, de_id, crud, None)
    for (field_id, crud), note in sorted(attribute_ticks.items()):
        row = live_a.get((field_id, crud))
        if row is not None:
            if row.usage_note != note:
                row.usage_note, row.updated_by = note, actor_id
            continue
        row = db.scalars(select(BrDataField).where(BrDataField.br_id == br.br_id,
                                                   BrDataField.data_field_id == field_id,
                                                   BrDataField.crud_code == crud)).one_or_none()
        if row is None:
            db.add(BrDataField(project_id=br.project_id, br_id=br.br_id, data_entity_id=fields[field_id].data_entity_id,
                               crud_code=crud, data_field_id=field_id, usage_note=note, created_by=actor_id))
        else:                                                 # re-ticking restores the same row (S1-7)
            lifecycle.relink(db, actor_id, row)
            row.usage_note = note
    db.commit()
    return grid(db, br)
