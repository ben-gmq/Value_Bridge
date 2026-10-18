"""Code-list maintenance (wave 1g; docs/slice1g_spec.md, G-1…G-5, D-71). The one owner of writes to code_master and
project_code_visibility. Reading a code for a record stays with services/code_master.resolve.

The invariant (R1, G-3): every row of a project — live or retired (R11) — holds the code_master row `resolve` returns
for its (category, code). Creating, retiring or restoring a project override therefore RE-POINTS the project's rows of
that category in the same transaction, on every code column the catalog shows (R12), with Core UPDATEs that leave
row_version alone (R13). Baseline shadows hold frozen text and are never touched (§7.7).

Locks (N3): every write at EDIT or ADMIN takes the project row FOR SHARE in its guard (access.require_project); a
code-list write on a project takes it FOR UPDATE first, so a save that picked a code waits for the re-point and then
lands on the new row, and a re-point never starts while such a save is open."""
import re

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from models import AppUser, CodeMaster, EffortRate, Project, ProjectCodeVisibility
from models.shared import FR_BEHAVIOURS, ISSUE_STATUS_BEHAVIOURS, RACI_BEHAVIOURS
from seeds.ftc_rate_card import FTC_DEFAULT_RATE_CARD
from services import audit
from services.code_master import resolve
from services.lifecycle import soft_delete

# ---- what may change ----------------------------------------------------------------------------------------------
# §7.4 + R4: the codes the application looks up by value. Relabel allowed, never retired or hidden. Every code of a
# system category is pinned too (is_system). tests/test_code_lists.py greps the services and the frontend for value
# lookups and fails on one missing here.
PINNED: frozenset[tuple[str, str]] = frozenset(
    {("BR_STATUS", c) for c in ("DRAFT", "CONFIRMED", "BASELINED", "SUPERSEDED")}
    | {("FR_FULFILMENT_STATUS", "SPECIFIED")}
    | {("SOLUTION_STATUS", c) for c in ("PROPOSED", "REJECTED")}
    | {("BR_LINE_KIND", c) for c in ("RULE", "OUTPUT")}
    | {("PROJECT_STATUS", "PLANNING")}
    | {("ISSUE_STATUS", c) for c in ("OPEN", "IN_PROGRESS", "RESOLVED", "DEFERRED", "CLOSED")}   # I-1: pinned
    | {("ISSUE_SEVERITY", "CRITICAL")}                              # I-13: the M3 tile counts it by code
    | {("FR_TYPE", t) for t, _ in FTC_DEFAULT_RATE_CARD}          # the rate card is keyed by them (R4)
    | {("FR_COMPLEXITY", c) for _, c in FTC_DEFAULT_RATE_CARD}
)
# §7.2, G-2, I-1: never overridden or hidden per project
COMPANY_ONLY = frozenset({"PROJECT_TEMPLATE", "PROJECT_STATUS", "ISSUE_STATUS"})
BEHAVIOUR_CATEGORIES = frozenset({"FR_TYPE", "RACI_TYPE", "ISSUE_STATUS"})
CODE_FORMAT = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")                # R7

# R12: code columns the re-point never reaches, each with its reason. A code FK in neither this list nor the
# re-point's discovered set fails tests/test_code_lists.py::test_every_code_column_is_repointed_or_excluded.
EXCLUDED: dict[tuple[str, str], str] = {
    ("user_access_grant", "project_role_code_id"): "retired table, SELECT-only (D-40)",
    ("project", "status_code_id"): "PROJECT_STATUS is company-only (G-2)",
    ("import_batch", "status_code_id"): "IMPORT_STATUS is a system category",
    ("project_component", "component_code_id"): "PROJECT_COMPONENT is a system category",
    ("project_template_component", "component_code_id"): "PROJECT_COMPONENT is a system category",
    ("project_template_component", "template_code_id"): "PROJECT_TEMPLATE is company-only (§7.2)",
    ("project_code_visibility", "code_id"): "names the company row a project hid — not a value a record holds",
}
# R2 protects the meaning of statuses: a project's wording of a pinned status is a platform admin's to give. FR types
# and complexities are pinned only as rate-card keys, so a project admin may rename them for the project (G-6, Q-38).
RELABEL_BY_PROJECT_ADMIN: frozenset[str] = frozenset({"FR_TYPE", "FR_COMPLEXITY"})


def is_pinned(row: CodeMaster) -> bool:
    return row.is_system or (row.category, row.code) in PINNED


def _admin_relabel_only(row: CodeMaster) -> bool:
    """R2: a project's wording of this code is a platform admin's to give."""
    return is_pinned(row) and row.category not in RELABEL_BY_PROJECT_ADMIN


def _system(db: Session, category: str) -> bool:
    return bool(db.scalar(select(func.bool_or(CodeMaster.is_system)).where(CodeMaster.category == category,
                                                                           CodeMaster.project_id.is_(None))))


def _known(db: Session, category: str) -> None:
    if not db.scalar(select(func.count()).where(CodeMaster.category == category, CodeMaster.project_id.is_(None))):
        raise HTTPException(404, f"No code list called {category}")


def _label(label: str | None) -> str:
    v = (label or "").strip()
    if not v or len(v) > 200:
        raise HTTPException(422, "A label is required (up to 200 characters)")
    return v


def _behaviour(category: str, behaviour: str | None) -> str | None:
    if category in BEHAVIOUR_CATEGORIES and not behaviour:
        raise HTTPException(422, f"A {category} code needs a behaviour")
    allowed = {"FR_TYPE": FR_BEHAVIOURS, "RACI_TYPE": RACI_BEHAVIOURS,
               "ISSUE_STATUS": ISSUE_STATUS_BEHAVIOURS}.get(category)
    if allowed and behaviour not in allowed:                        # sara 1g L7: a clear 422, not the CHECK's
        raise HTTPException(422, f"Behaviour must be one of {', '.join(allowed)}")
    if category not in BEHAVIOUR_CATEGORIES and behaviour:
        raise HTTPException(422, f"{category} codes carry no behaviour")
    return behaviour


def _lock_project(db: Session, project_id: int) -> None:
    db.execute(select(Project.project_id).where(Project.project_id == project_id).with_for_update())


# ---- the re-point (R1, R11–R13) -----------------------------------------------------------------------------------
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_COLUMNS: dict[str, list[dict]] = {}          # per database; the catalog changes only with a migration (sara 1g L4)


def code_columns(db: Session) -> list[dict]:
    """Every live-table column holding a code_master id, with its category (from the generated `<x>_category`
    column, read by attrelid so a same-named table in another schema never answers — sara 1g L2) and the table's
    primary key — read from the catalog, so a new table is covered without a list. Baseline tables are left out by
    name (sara 1g L3); every identifier is checked before it is formatted into SQL (sara 1g L1)."""
    key = str(db.get_bind().url)
    if key in _COLUMNS:
        return _COLUMNS[key]
    from models.baseline import SHADOW_TABLES
    frozen = {t.name for t in SHADOW_TABLES.values()} | {"baseline"}
    rows = db.execute(text("""
        SELECT cl.relname AS tbl, a1.attname AS col, a2.attname AS cat_col,
               pg_get_expr(d.adbin, d.adrelid) AS cat_expr,
               (SELECT a.attname FROM pg_index i JOIN pg_attribute a
                         ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
                 WHERE i.indrelid = c.conrelid AND i.indisprimary) AS pk
        FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_attribute a1 ON a1.attrelid = c.conrelid AND a1.attnum = c.conkey[1]
        LEFT JOIN pg_attribute a2 ON a2.attrelid = c.conrelid AND a2.attnum = c.conkey[2]
        LEFT JOIN pg_attrdef d ON d.adrelid = c.conrelid AND d.adnum = c.conkey[2]
        WHERE c.contype = 'f' AND c.confrelid = 'code_master'::regclass AND c.conrelid <> 'code_master'::regclass
        ORDER BY 1, 2""")).mappings().all()
    out = []
    for r in rows:
        if r["tbl"] in frozen:
            continue
        for ident in (r["tbl"], r["col"], r["pk"]):
            if not _IDENT.match(ident or ""):
                raise RuntimeError(f"code column identifier not safe to format: {ident!r}")
        m = re.match(r"^'([A-Z_]+)'", r["cat_expr"] or "")
        out.append({"table": r["tbl"], "column": r["col"], "category": m.group(1) if m else None, "pk": r["pk"]})
    _COLUMNS[key] = out
    return out


def repointed_columns(db: Session) -> list[dict]:
    return [c for c in code_columns(db) if (c["table"], c["column"]) not in EXCLUDED and c["category"]]


def _target(db: Session, project_id: int, category: str, code: str) -> CodeMaster | None:
    return next((r for r in resolve(db, project_id, category) if r.code == code), None)


def repoint(db: Session, actor_id: int, project_id: int, category: str, code: str) -> dict:
    """Move every row of the project holding any tier's row of (category, code) to the row resolve returns. No
    commit. Audited once with per-table counts and ids (R13)."""
    target = _target(db, project_id, category, code)
    if target is None:
        return {}
    ids = list(db.scalars(select(CodeMaster.code_id).where(
        CodeMaster.category == category, CodeMaster.code == code,
        (CodeMaster.project_id == project_id) | CodeMaster.project_id.is_(None))))
    moved = {}
    for c in repointed_columns(db):
        if c["category"] != category:
            continue
        got = db.execute(text(
            f'UPDATE {c["table"]} SET {c["column"]} = :t, updated_by = :a '
            f'WHERE project_id = :p AND {c["column"]} = ANY(:ids) AND {c["column"]} <> :t RETURNING {c["pk"]}'),
            {"t": target.code_id, "a": actor_id, "p": project_id, "ids": ids}).scalars().all()
        if got:
            moved[f'{c["table"]}.{c["column"]}'] = sorted(got)
    if moved:
        audit.record(db, "CODE_REPOINTED", actor_id=actor_id, project_id=project_id, target_table="code_master",
                     target_id=target.code_id,
                     detail={"category": category, "code": code, "to": target.code_id,
                             "counts": {k: len(v) for k, v in moved.items()}, "rows": moved})
    return moved


def in_use(db: Session, code_ids: list[int], project_id: int | None = None) -> dict[int, int]:
    """Live rows holding each code id — in one project, or in all (the company behaviour check, R9)."""
    if not code_ids:
        return {}
    counts: dict[int, int] = {}
    for c in code_columns(db):
        if (c["table"], c["column"]) in EXCLUDED and c["table"] != "project":
            continue
        where = f'{c["column"]} = ANY(:ids) AND is_active'
        if project_id is not None:
            if c["table"] == "project":
                continue
            where += " AND project_id = :p"
        for cid, n in db.execute(text(f'SELECT {c["column"]}, count(*) FROM {c["table"]} WHERE {where} '
                                      f'GROUP BY 1'), {"ids": code_ids, "p": project_id}):
            counts[cid] = counts.get(cid, 0) + n
    return counts


# ---- rate cells for a new FR type (R6, G-4) ------------------------------------------------------------------------
def _seed_type_cells(db: Session, actor_id: int, project_id: int, new_type: CodeMaster) -> int:
    """Copy this project's cells of the first existing FR type with the same behaviour, unconfirmed (no rationale).
    Behaviour OTHER has no source: no cells, so rating returns 422 until someone fills them (G-4)."""
    if new_type.behaviour_code == "OTHER":
        return 0
    source = next((t for t in resolve(db, project_id, "FR_TYPE")
                   if t.behaviour_code == new_type.behaviour_code and t.code != new_type.code), None)
    if source is None:
        return 0
    have = set(db.scalars(select(EffortRate.complexity_code_id).where(
        EffortRate.project_id == project_id, EffortRate.fr_type_code_id == new_type.code_id)))
    n = 0
    for cell in db.scalars(select(EffortRate).where(EffortRate.project_id == project_id, EffortRate.is_active,
                                                    EffortRate.fr_type_code_id == source.code_id)):
        if cell.complexity_code_id in have:
            continue
        db.add(EffortRate(project_id=project_id, fr_type_code_id=new_type.code_id,
                          complexity_code_id=cell.complexity_code_id, standard_days=cell.standard_days,
                          created_by=actor_id))
        n += 1
    if n:
        db.flush()
        audit.record(db, "RATE_CELLS_SEEDED", actor_id=actor_id, project_id=project_id, target_table="effort_rate",
                     detail={"fr_type": new_type.code, "copied_from": source.code, "cells": n})
    return n


# ---- reading ------------------------------------------------------------------------------------------------------
def _row(r: CodeMaster | None) -> dict | None:
    if r is None:
        return None
    return {"code_id": r.code_id, "label": r.label, "sort_order": r.sort_order, "behaviour_code": r.behaviour_code,
            "is_active": r.is_active, "row_version": r.row_version}


def hidden_ids(db: Session, project_id: int) -> set[int]:
    return set(db.scalars(select(ProjectCodeVisibility.code_id).where(
        ProjectCodeVisibility.project_id == project_id, ProjectCodeVisibility.is_active)))


def list_for_project(db: Session, project: Project) -> list[dict]:
    rows = list(db.scalars(select(CodeMaster).where(
        (CodeMaster.project_id == project.project_id) | CodeMaster.project_id.is_(None))))
    hidden = hidden_ids(db, project.project_id)
    used = in_use(db, [r.code_id for r in rows], project.project_id)
    by_cat: dict[str, dict[str, dict]] = {}
    for r in rows:
        slot = by_cat.setdefault(r.category, {}).setdefault(r.code, {"code": r.code, "company": None, "project": None})
        slot["company" if r.project_id is None else "project"] = r
    out = []
    for cat in sorted(by_cat):
        codes = by_cat[cat]
        system = any(s["company"] is not None and s["company"].is_system for s in codes.values())
        items = []
        for code, s in codes.items():
            comp, proj = s["company"], s["project"]
            ref = comp or proj
            items.append({"code": code, "company": _row(comp), "project": _row(proj),
                          "pinned": is_pinned(ref), "hidden": bool(comp and comp.code_id in hidden),
                          "in_use": sum(used.get(x.code_id, 0) for x in (comp, proj) if x is not None),
                          "sort_order": (proj if proj is not None and proj.is_active else ref).sort_order})
        items.sort(key=lambda i: (i["sort_order"], i["code"]))
        out.append({"category": cat, "is_system": system, "company_only": cat in COMPANY_ONLY, "codes": items})
    return out


def list_company(db: Session) -> list[dict]:
    rows = list(db.scalars(select(CodeMaster).where(CodeMaster.project_id.is_(None))))
    used = in_use(db, [r.code_id for r in rows])
    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r.category, []).append(
            {"code": r.code, "company": _row(r), "project": None, "pinned": is_pinned(r), "hidden": False,
             "in_use": used.get(r.code_id, 0), "sort_order": r.sort_order})
    system = {r.category for r in rows if r.is_system}
    return [{"category": c, "is_system": c in system, "company_only": c in COMPANY_ONLY,
             "codes": sorted(by_cat[c], key=lambda i: (i["sort_order"], i["code"]))} for c in sorted(by_cat)]


# ---- company library (platform admin, by route guard) --------------------------------------------------------------
def add_company_code(db: Session, actor: AppUser, category: str, code: str, label: str, behaviour: str | None,
                     sort_order: int | None) -> CodeMaster:
    _known(db, category)
    if _system(db, category):
        raise HTTPException(409, f"{category} is a system list: the application depends on every code in it")
    if not CODE_FORMAT.match(code or ""):
        raise HTTPException(422, "A code is capital letters, digits and _ (up to 40), starting with a letter")
    label, behaviour = _label(label), _behaviour(category, behaviour)
    if db.scalar(select(CodeMaster).where(CodeMaster.project_id.is_(None), CodeMaster.category == category,
                                          CodeMaster.code == code)) is not None:
        raise HTTPException(409, f"{code} already exists in {category} — restore or rename it instead")
    _refuse_project_owned(db, category, code)
    row = CodeMaster(project_id=None, category=category, code=code, label=label, behaviour_code=behaviour,
                     sort_order=sort_order if sort_order is not None else _next_sort(db, None, category),
                     created_by=actor.app_user_id)
    db.add(row)
    db.flush()
    audit.record(db, "CODE_ADDED", actor_id=actor.app_user_id, target_table="code_master", target_id=row.code_id,
                 detail={"category": category, "code": code, "label": label, "behaviour": behaviour, "tier": "company"})
    if category == "FR_TYPE":                                       # R6/G-4: every live project can rate it at once
        for pid in db.scalars(select(Project.project_id).where(Project.is_active).order_by(Project.project_id)):
            _seed_type_cells(db, actor.app_user_id, pid, _target(db, pid, "FR_TYPE", code) or row)
    db.commit()
    return row


def _refuse_project_owned(db: Session, category: str, code: str) -> None:
    """R8/R14: a company code some project already owns as its own would silently become an override there."""
    owners = db.execute(select(Project.project_code).join(CodeMaster, CodeMaster.project_id == Project.project_id)
                        .where(CodeMaster.category == category, CodeMaster.code == code)
                        .order_by(Project.project_code)).scalars().all()
    if owners:
        raise HTTPException(409, f"{code} is already a project's own code in {', '.join(owners)} — pick another code")


def _next_sort(db: Session, project_id: int | None, category: str) -> int:
    q = select(func.coalesce(func.max(CodeMaster.sort_order), 0)).where(CodeMaster.category == category)
    q = q.where(CodeMaster.project_id.is_(None) | (CodeMaster.project_id == project_id)) if project_id else \
        q.where(CodeMaster.project_id.is_(None))
    return db.scalar(q) + 10


# ---- a project's lists (project admin, by route guard) ------------------------------------------------------------
def add_project_code(db: Session, actor: AppUser, project: Project, category: str, code: str, label: str,
                     behaviour: str | None, sort_order: int | None) -> CodeMaster:
    """A project row: an override of the company code (same code, new label — re-points the project's rows), or a
    project-only code. A retired row is restored, never re-inserted (R1)."""
    _lock_project(db, project.project_id)
    _known(db, category)
    if _system(db, category):
        raise HTTPException(409, f"{category} is a system list: the application depends on every code in it")
    if category in COMPANY_ONLY:
        raise HTTPException(409, f"{category} is kept company-wide; a project cannot rename or add to it")
    label = _label(label)
    company = db.scalar(select(CodeMaster).where(CodeMaster.project_id.is_(None), CodeMaster.category == category,
                                                 CodeMaster.code == code))
    mine = db.scalar(select(CodeMaster).where(CodeMaster.project_id == project.project_id,
                                              CodeMaster.category == category, CodeMaster.code == code))
    if mine is not None and mine.is_active:
        raise HTTPException(409, f"{code} already has this project's wording — change it instead")
    if company is not None:
        if not company.is_active:
            raise HTTPException(409, f"{code} is retired in the company library")
        if _admin_relabel_only(company) and not actor.is_platform_admin:
            raise HTTPException(403, f"{code} is one the application relies on: only a platform administrator "
                                     f"may rename it (R2)")
        if behaviour and behaviour != company.behaviour_code:      # R10
            raise HTTPException(409, f"A renamed {code} keeps its behaviour ({company.behaviour_code}) — add a new "
                                     f"code for a different behaviour")
        behaviour = company.behaviour_code
    else:
        if not CODE_FORMAT.match(code or ""):
            raise HTTPException(422, "A code is capital letters, digits and _ (up to 40), starting with a letter")
        if mine is None:
            behaviour = _behaviour(category, behaviour)
        elif behaviour and behaviour != mine.behaviour_code:
            raise HTTPException(409, f"{code} keeps its behaviour ({mine.behaviour_code})")
        else:
            behaviour = mine.behaviour_code
    if mine is not None:                                            # restore the same row (S1-7, R1)
        mine.is_active, mine.deleted_at, mine.deleted_by = True, None, None
        mine.label, mine.updated_by = label, actor.app_user_id
        if sort_order is not None:
            mine.sort_order = sort_order
        row, event = mine, "CODE_RESTORED"
    else:
        row = CodeMaster(project_id=project.project_id, category=category, code=code, label=label,
                         behaviour_code=behaviour, created_by=actor.app_user_id,
                         sort_order=sort_order if sort_order is not None else
                         (company.sort_order if company else _next_sort(db, project.project_id, category)))
        db.add(row)
        event = "CODE_OVERRIDDEN" if company is not None else "CODE_ADDED"
    db.flush()
    audit.record(db, event, actor_id=actor.app_user_id, project_id=project.project_id, target_table="code_master",
                 target_id=row.code_id, detail={"category": category, "code": code, "label": label,
                                                "company_label": company.label if company else None})
    repoint(db, actor.app_user_id, project.project_id, category, code)
    if category == "FR_TYPE" and company is None:                   # a project-only type: rate cells (G-4)
        _seed_type_cells(db, actor.app_user_id, project.project_id, row)
    db.commit()
    return row


def update_code(db: Session, actor: AppUser, row: CodeMaster, row_version: int, label: str | None,
                sort_order: int | None, behaviour: str | None) -> CodeMaster:
    if row.project_id is not None:
        _lock_project(db, row.project_id)
    db.refresh(row)
    if row.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if row.is_system:
        raise HTTPException(409, f"{row.category} is a system list: the application depends on every code in it")
    if row.project_id is not None and row.category in COMPANY_ONLY:
        raise HTTPException(409, f"{row.category} is kept company-wide")
    before = {"label": row.label, "sort_order": row.sort_order, "behaviour": row.behaviour_code}
    if label is not None:
        if row.project_id is not None and _admin_relabel_only(row) and not actor.is_platform_admin:
            raise HTTPException(403, f"{row.code} is one the application relies on: only a platform administrator "
                                     f"may rename it (R2)")
        row.label = _label(label)
    if sort_order is not None:
        row.sort_order = sort_order
    if behaviour is not None and behaviour != row.behaviour_code:
        _behaviour(row.category, behaviour)
        if row.category == "ISSUE_STATUS" and is_pinned(row):         # sara A M-2: reopen writes OPEN by value
            raise HTTPException(409, f"{row.code} is one the application relies on, so its behaviour is fixed")
        company = row.project_id is None
        if not company and db.scalar(select(CodeMaster).where(
                CodeMaster.project_id.is_(None), CodeMaster.category == row.category, CodeMaster.code == row.code)):
            raise HTTPException(409, f"A renamed {row.code} keeps the company behaviour — add a new code instead")
        if company and db.scalar(select(func.count()).where(CodeMaster.project_id.is_not(None),
                                                            CodeMaster.category == row.category,
                                                            CodeMaster.code == row.code)):
            raise HTTPException(409, f"Projects have renamed {row.code}, so its behaviour is fixed — add a new code")
        uses = sum(in_use(db, [row.code_id], None if company else row.project_id).values())
        uses += db.scalar(select(func.count()).where(EffortRate.fr_type_code_id == row.code_id)) or 0
        if uses:
            raise HTTPException(409, f"{row.code} is in use, so its behaviour is fixed — add a new code instead (Q6)")
        row.behaviour_code = behaviour
    row.updated_by = actor.app_user_id
    after = {"label": row.label, "sort_order": row.sort_order, "behaviour": row.behaviour_code}
    audit.record(db, "CODE_CHANGED", actor_id=actor.app_user_id, project_id=row.project_id,
                 target_table="code_master", target_id=row.code_id,
                 detail={"category": row.category, "code": row.code, "before": before, "after": after})
    db.commit()
    return row


def retire_code(db: Session, actor: AppUser, row: CodeMaster, row_version: int) -> None:
    """Company or project-only: leaves the pickers; rows holding it keep it (§5.4.15). A project override: the
    company label returns and the project's rows re-point to it (R1)."""
    if row.project_id is not None:
        _lock_project(db, row.project_id)
    db.refresh(row)
    if row.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if not row.is_active:
        raise HTTPException(409, f"{row.code} is already retired")
    company = None if row.project_id is None else db.scalar(select(CodeMaster).where(
        CodeMaster.project_id.is_(None), CodeMaster.category == row.category, CodeMaster.code == row.code))
    if row.is_system or (is_pinned(row) and company is None):
        raise HTTPException(409, f"{row.code} is one the application relies on: it can be renamed, never retired")
    soft_delete(row, actor.app_user_id)
    row.updated_by = actor.app_user_id
    audit.record(db, "CODE_RETIRED", actor_id=actor.app_user_id, project_id=row.project_id,
                 target_table="code_master", target_id=row.code_id,
                 detail={"category": row.category, "code": row.code, "override": company is not None})
    db.flush()
    if company is not None:
        repoint(db, actor.app_user_id, row.project_id, row.category, row.code)
    db.commit()


def restore_code(db: Session, actor: AppUser, row: CodeMaster, row_version: int) -> CodeMaster:
    if row.project_id is not None:
        _lock_project(db, row.project_id)
    db.refresh(row)
    if row.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if row.is_active:
        raise HTTPException(409, f"{row.code} is not retired")
    # R14 holds by construction for a company row: while it exists (live or retired) no project can make a project-only
    # code of the same code, so every same-code project row is an override and must not block the restore (sara 1g M3).
    row.is_active, row.deleted_at, row.deleted_by = True, None, None
    row.updated_by = actor.app_user_id
    audit.record(db, "CODE_RESTORED", actor_id=actor.app_user_id, project_id=row.project_id,
                 target_table="code_master", target_id=row.code_id,
                 detail={"category": row.category, "code": row.code})
    db.flush()
    if row.project_id is not None:
        repoint(db, actor.app_user_id, row.project_id, row.category, row.code)
    db.commit()
    return row


# ---- hide / unhide (A2, G-1) ---------------------------------------------------------------------------------------
def hide(db: Session, actor: AppUser, project: Project, code_id: int) -> ProjectCodeVisibility:
    _lock_project(db, project.project_id)
    row = db.get(CodeMaster, code_id)
    if row is None or (row.project_id is not None and row.project_id != project.project_id):
        raise HTTPException(404, "Not found")
    if row.project_id is not None:
        raise HTTPException(422, "A project's own code is retired, not hidden")
    if row.is_system or is_pinned(row):
        raise HTTPException(409, f"{row.code} is one the application relies on: it cannot be hidden")
    if row.category in COMPANY_ONLY:
        raise HTTPException(409, f"{row.category} is kept company-wide")
    v = db.scalar(select(ProjectCodeVisibility).where(ProjectCodeVisibility.project_id == project.project_id,
                                                      ProjectCodeVisibility.code_id == code_id))
    if v is not None and v.is_active:
        raise HTTPException(409, f"{row.code} is already hidden in this project")
    if v is not None:
        v.is_active, v.deleted_at, v.deleted_by, v.updated_by = True, None, None, actor.app_user_id
    else:
        v = ProjectCodeVisibility(project_id=project.project_id, code_id=code_id, created_by=actor.app_user_id)
        db.add(v)
    db.flush()
    audit.record(db, "CODE_HIDDEN", actor_id=actor.app_user_id, project_id=project.project_id,
                 target_table="project_code_visibility", target_id=v.project_code_visibility_id,
                 detail={"category": row.category, "code": row.code})
    db.commit()
    return v


def unhide(db: Session, actor: AppUser, project: Project, code_id: int) -> None:
    _lock_project(db, project.project_id)
    v = db.scalar(select(ProjectCodeVisibility).where(ProjectCodeVisibility.project_id == project.project_id,
                                                      ProjectCodeVisibility.code_id == code_id,
                                                      ProjectCodeVisibility.is_active))
    if v is None:
        raise HTTPException(404, "That code is not hidden in this project")
    soft_delete(v, actor.app_user_id)
    v.updated_by = actor.app_user_id
    row = db.get(CodeMaster, code_id)
    audit.record(db, "CODE_UNHIDDEN", actor_id=actor.app_user_id, project_id=project.project_id,
                 target_table="project_code_visibility", target_id=v.project_code_visibility_id,
                 detail={"category": row.category, "code": row.code})
    db.commit()
