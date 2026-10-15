"""The project's DFD rule (D-70; slice13_spec §4.2, §7.2; slice13_schema §2; S13-1): which DFD elements every
process of one chart must have before the scope can be frozen.

One reader, `codes()`: readiness, the marks, the warnings, consistency_check, the preview and the freeze all call
it. **It fails closed (DR13-D3):** a chart with no live rule row reads as the D-38 rule, never as "nothing
required", and the must-be-empty line `project_without_dfd_rule` refuses the freeze until an admin saves one.

The elements are a closed, code-defined vocabulary (each one is a predicate in services/process_flow), CHECK-listed
on the table, labelled in the screen's i18n file [Q-17]. Option A (Q-3, §8a): order stays derived from data, so
ORDER is only valid with DATA_IN and DATA_OUT; STARTED is always required (a process nothing starts cannot be
placed, A-13-3). EXTERNAL is checked per diagram, never per process, and never changes a process's light (Q-6,
Q-16). A trigger is not an element of its own: STARTED covers it (Q-14).

Changed only by `set_rule` — project ADMIN (platform admin, Q-5), optimistic lock on the project's row_version,
the preview digest the admin confirmed, audited PROJECT_DFD_RULE_CHANGED. A setting, not scope: not shadowed, not in
FREEZE_SET; the freeze copies the rule onto the baseline header."""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import AppUser, Project, ProjectDfdRule
from services import audit, lifecycle

STARTED, DATA_IN, DATA_OUT, EXTERNAL, ORDER = "STARTED", "DATA_IN", "DATA_OUT", "EXTERNAL", "ORDER"
ELEMENTS = (STARTED, DATA_IN, DATA_OUT, EXTERNAL, ORDER)          # the catalogue, in its display order
SETS = ("TO_BE", "AS_IS")
FIXED_RULE = (STARTED, DATA_OUT)                                  # D-38; also what an empty rule reads as
LOCKED = frozenset({STARTED})                                     # never droppable (ck_pdr_started_locked)
REQUIRES = {ORDER: (DATA_IN, DATA_OUT)}                           # option A: order IS data
PER_DIAGRAM = frozenset({EXTERNAL})                               # Q-6 / Q-16: a diagram-level check
# Q-4 / [Q-18]: what a NEW project starts with. Code constants; Ben reviews them after two client projects (§1a).
# Yellow (Q-13) = every rule element met, but a recommended one is missing.
RECOMMENDED = {"TO_BE": (STARTED, DATA_IN, DATA_OUT, ORDER), "AS_IS": (STARTED,)}


def ordered(codes) -> tuple[str, ...]:
    s = set(codes)
    return tuple(e for e in ELEMENTS if e in s)


def _live_by_set(db: Session, project_id: int) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {s: set() for s in SETS}
    for s, e in db.execute(select(ProjectDfdRule.bfc_set_code, ProjectDfdRule.element_code).where(
            ProjectDfdRule.project_id == project_id, ProjectDfdRule.is_active)):
        out[s].add(e)
    return out


def _read(live: set[str]) -> tuple[str, ...]:
    return ordered(live | {STARTED}) if live else FIXED_RULE


def codes(db: Session, project_id: int, bfc_set: str) -> tuple[str, ...]:
    """The chart's rule. No live row (a raw-SQL import, a restore from a dump) → the D-38 rule: never open."""
    return _read(_live_by_set(db, project_id)[bfc_set])


def rules(db: Session, project_id: int) -> dict[str, tuple[str, ...]]:
    """Both charts in one read."""
    return {s: _read(live) for s, live in _live_by_set(db, project_id).items()}


def validate(raw) -> tuple[str, ...]:
    """§7.2: a known element set, STARTED in it, ORDER only with both data elements. 422 otherwise."""
    unknown = sorted({c for c in raw if c not in ELEMENTS})
    if unknown:
        raise HTTPException(422, f"Unknown DFD element: {', '.join(unknown)}")
    got = set(raw)
    for e in LOCKED:
        if e not in got:
            raise HTTPException(422, "Something must start every process: that element is always required")
    for e, needs in REQUIRES.items():
        if e in got and not set(needs) <= got:
            raise HTTPException(422, "The order is derived from the data, so it needs both data in and data out")
    return ordered(got)


# ---- writing ---------------------------------------------------------------------------------------------

def _apply(db: Session, project_id: int, bfc_set: str, want: tuple[str, ...], actor_id: int) -> None:
    """Restore or insert the wanted rows, retire the rest (S1-7: a re-added element is the same row)."""
    rows = {r.element_code: r for r in db.scalars(select(ProjectDfdRule).where(
        ProjectDfdRule.project_id == project_id, ProjectDfdRule.bfc_set_code == bfc_set)
        .order_by(ProjectDfdRule.project_dfd_rule_id).with_for_update())}
    for e in ELEMENTS:
        r = rows.get(e)
        if e in want:
            if r is None:
                db.add(ProjectDfdRule(project_id=project_id, bfc_set_code=bfc_set, element_code=e,
                                      created_by=actor_id))
            elif not r.is_active:
                r.is_active, r.deleted_at, r.deleted_by, r.updated_by = True, None, None, actor_id
        elif r is not None and r.is_active:
            lifecycle.soft_delete(r, actor_id)
            r.updated_by = actor_id
    db.flush()


def initial_rows(db: Session, project_id: int, rule: dict | None, actor_id: int) -> dict[str, list[str]]:
    """create_project, same transaction: each chart gets the body's set or RECOMMENDED (Q-4)."""
    rule = rule or {}
    unknown = sorted(set(rule) - set(SETS))
    if unknown:
        raise HTTPException(422, f"dfd_rule: unknown chart {', '.join(unknown)}")
    out = {}
    for s in SETS:
        want = validate(rule[s]) if s in rule else RECOMMENDED[s]
        _apply(db, project_id, s, want, actor_id)
        out[s] = list(want)
    return out


# ---- reading: the settings card -------------------------------------------------------------------------

def describe(db: Session, project: Project) -> dict:
    """GET /projects/{id}/dfd-rule: per chart its codes, whether it applies (its DFD on) and whether it fell back to
    D-38 for want of rows; the catalogue with what is locked, what each needs and what is recommended."""
    from services import process_flow
    live = _live_by_set(db, project.project_id)
    on = process_flow.sets_with_dfd_on(db, project.project_id)
    return {
        "project_id": project.project_id,
        "row_version": project.row_version,
        "charts": [{"bfc_set_code": s, "codes": list(_read(live[s])), "rule_applies": s in on,
                    "fallback": not live[s], "recommended": list(RECOMMENDED[s])} for s in SETS],
        "catalogue": [{"code": e, "locked": e in LOCKED, "requires": list(REQUIRES.get(e, ())),
                       "per_diagram": e in PER_DIAGRAM} for e in ELEMENTS],
    }


def preview(db: Session, project: Project, bfc_set: str, raw) -> dict:
    """What a proposed rule would do to one chart now: lights under it, and how many processes (and, for EXTERNAL,
    diagrams) would block the next freeze. Writes nothing. The digest pins exactly what the admin saw (DR8-P2)."""
    from services import process_flow
    want = validate(raw)
    r = process_flow.readiness(db, project.project_id, bfc_set, rule=want)
    counts = {"READY": 0, "PARTIAL": 0, "NOT_READY": 0}
    for p in r["processes"].values():
        counts[p["light"]] += 1
    blocked = sorted(i for i, p in r["processes"].items() if p["light"] == process_flow.NOT_READY)
    diagrams = ([d["bfc_node_id"] for d in process_flow.diagrams_missing_external(db, project.project_id, bfc_set,
                                                                                         rule=want)]
                if r["rule_applies"] and EXTERNAL in want else [])
    body = {"bfc_set_code": bfc_set, "codes": list(want), "rule_applies": r["rule_applies"],
            "ready": counts["READY"], "partly": counts["PARTIAL"], "not_ready": counts["NOT_READY"],
            "would_block": len(blocked), "would_block_diagrams": len(diagrams)}
    digest = hashlib.sha256(json.dumps({**body, "blocked": blocked, "diagrams": sorted(diagrams)},
                                       sort_keys=True).encode()).hexdigest()
    return {**body, "current": list(codes(db, project.project_id, bfc_set)), "preview_digest": digest}


def set_rule(db: Session, actor: AppUser, project: Project, bfc_set: str, raw, row_version: int,
             preview_digest: str) -> dict:
    """PUT: one chart's rule. Serialised on the project row; 409 on a stale row_version or when the preview the admin
    confirmed no longer holds; 422 on an invalid set. The project's row_version is bumped by the mapper, never the
    body (law 6). Saving the same set again changes nothing and records nothing."""
    db.execute(select(Project.project_id).where(Project.project_id == project.project_id).with_for_update())
    db.refresh(project)
    if project.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    want = validate(raw)
    p = preview(db, project, bfc_set, want)
    if p["preview_digest"] != preview_digest:
        raise HTTPException(409, "The processes changed since you previewed this rule. Review it again; "
                                 "nothing was saved.")
    live = _live_by_set(db, project.project_id)[bfc_set]
    before = _read(live)
    if live == set(want):
        return describe(db, project)
    _apply(db, project.project_id, bfc_set, want, actor.app_user_id)
    project.updated_by = actor.app_user_id
    flag_modified(project, "updated_by")             # bump project.row_version even when the actor is unchanged
    audit.record(db, "PROJECT_DFD_RULE_CHANGED", actor_id=actor.app_user_id, project_id=project.project_id,
                 target_table="project_dfd_rule", target_id=project.project_id,
                 detail={"bfc_set_code": bfc_set, "from": list(before), "to": list(want),
                         "would_block": p["would_block"], "would_block_diagrams": p["would_block_diagrams"]})
    db.commit()
    db.refresh(project)
    return describe(db, project)


# ---- consistency_check lines (must be empty) ---------------------------------------------------------------

def without_rule(db: Session, project_id: int | None) -> list[dict]:
    """DR13-D3: each (project, chart) with no live rule row — whatever the project's is_active. The readers apply
    D-38 meanwhile; this line refuses the freeze until an admin saves a rule."""
    q = select(Project.project_id, Project.project_code).order_by(Project.project_id)
    if project_id is not None:
        q = q.where(Project.project_id == project_id)
    have = {(p, s) for p, s in db.execute(
        select(ProjectDfdRule.project_id, ProjectDfdRule.bfc_set_code).where(ProjectDfdRule.is_active)
        .where(*(() if project_id is None else (ProjectDfdRule.project_id == project_id,))).distinct())}
    return [{"project_id": p, "project_code": code, "bfc_set_code": s}
            for p, code in db.execute(q) for s in SETS if (p, s) not in have]


def invalid(db: Session, project_id: int | None) -> list[dict]:
    """The cross-row rule a CHECK cannot see: a live element whose required elements are not live on that chart."""
    live: dict[tuple[int, str], set[str]] = {}
    q = select(ProjectDfdRule.project_id, ProjectDfdRule.bfc_set_code, ProjectDfdRule.element_code).where(
        ProjectDfdRule.is_active)
    if project_id is not None:
        q = q.where(ProjectDfdRule.project_id == project_id)
    for p, s, e in db.execute(q):
        live.setdefault((p, s), set()).add(e)
    return [{"project_id": p, "bfc_set_code": s, "element_code": e, "needs": list(needs)}
            for (p, s), got in sorted(live.items()) for e, needs in REQUIRES.items()
            if e in got and not set(needs) <= got]
