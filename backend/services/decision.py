"""Decisions (§4.11 record_decision / decision_log, D-17, A-41; docs/slice_decisions_spec.md; DC-1…DC-5, review D1).
The one owner of decision writes.

A decision is written once and never changed: the database refuses UPDATE and DELETE (migration 0084), so this service
only inserts. A correction is a new decision whose `supersedes_decision_id` names the one it corrects — which must be
in the same project and not yet corrected (DC-2: only the latest in a chain). Two corrections racing each other are
settled by uq_decision_superseded_once: the loser gets the same 409 (vb_app has no UPDATE, so no FOR UPDATE lock).

No component (DC-1). The recorder is the signed-in user, never a body value (law 6). Audit DECISION_RECORDED carries
numbers and codes only, never title or text (R7)."""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from models import AppUser, ControlRule, Decision
from services import audit, numbering
from services.baseline import local_today
from services.code_master import validate_required_code

SUPERSEDED_ONCE = "uq_decision_superseded_once"


def _text(value, field: str) -> str:
    out = (value or "").strip()
    if not out:
        raise HTTPException(422, f"{field} is required")
    return out


def _analysis(db: Session, project_id: int, code: str | None) -> str | None:
    """DC-3: one of this project's control rules (switched on or off); the registry itself is not enough."""
    code = (code or "").strip() or None
    if code is None:
        return None
    found = db.scalar(select(ControlRule.control_rule_id).where(ControlRule.project_id == project_id,
                                                                ControlRule.analysis_code == code,
                                                                ControlRule.is_active))
    if found is None:
        raise HTTPException(422, f"'{code}' is not one of this project's control rules")
    return code


def _decided_on(value: date | None) -> date:
    """DC-4: the meeting date, today (ICT) unless given, never in the future (D1-5: local_today, not the host's)."""
    today = local_today()
    if value is None:
        return today
    if value > today:
        raise HTTPException(422, "The decision date cannot be in the future")
    return value


def _already(db: Session, target: Decision) -> HTTPException:
    later = db.scalar(select(Decision.decision_number).where(Decision.supersedes_decision_id == target.decision_id))
    return HTTPException(409, f"{target.decision_number} was already corrected by {later}. "
                              f"Correct {later} instead" if later else f"{target.decision_number} was already corrected")


def _target(db: Session, project_id: int, decision_id: int | None) -> Decision | None:
    """Read scoped to the URL's project (D1-6): another project's decision is a 404, never the FK's 500."""
    if decision_id is None:
        return None
    target = db.scalar(select(Decision).where(Decision.decision_id == decision_id,
                                              Decision.project_id == project_id))
    if target is None:
        raise HTTPException(404, "The decision to correct was not found in this project")
    if db.scalar(select(Decision.decision_id).where(Decision.supersedes_decision_id == decision_id)) is not None:
        raise _already(db, target)
    return target


# ---- reads -----------------------------------------------------------------------------------------------------------
def list_decisions(db: Session, project_id: int, dimension: str | None = None,
                   include_superseded: bool = True) -> list[Decision]:
    """§4.11 decision_log: newest decided-on first, then the highest number (ASSUMPTION A3)."""
    later = aliased(Decision)
    q = select(Decision).where(Decision.project_id == project_id)
    if dimension:
        q = q.where(Decision.dimension_code_row.has(code=dimension))
    if not include_superseded:
        q = q.where(~select(later.decision_id).where(later.supersedes_decision_id == Decision.decision_id).exists())
    rows = list(db.scalars(q.order_by(Decision.decided_on.desc(), Decision.decision_id.desc())).unique())
    attach_chain(db, rows)
    return rows


def attach_chain(db: Session, rows: list[Decision]) -> None:
    """Sets superseded_by_* and supersedes_number on each row (worked out on read, never stored — the row is fixed)."""
    ids = [r.decision_id for r in rows]
    if not ids:
        return
    after = {s: (i, n) for s, i, n in db.execute(
        select(Decision.supersedes_decision_id, Decision.decision_id, Decision.decision_number)
        .where(Decision.supersedes_decision_id.in_(ids)))}
    before_ids = [r.supersedes_decision_id for r in rows if r.supersedes_decision_id is not None]
    before = dict(db.execute(select(Decision.decision_id, Decision.decision_number)
                             .where(Decision.decision_id.in_(before_ids))).all()) if before_ids else {}
    names = dict(db.execute(select(AppUser.app_user_id, AppUser.display_name)
                            .where(AppUser.app_user_id.in_({r.decided_by_user_id for r in rows}))).all())
    for r in rows:
        r.superseded_by_id, r.superseded_by_number = after.get(r.decision_id, (None, None))
        r.supersedes_number = before.get(r.supersedes_decision_id)
        r.decided_by_name = names.get(r.decided_by_user_id)


# ---- writes ----------------------------------------------------------------------------------------------------------
def record_decision(db: Session, actor_id: int, project_id: int, fields: dict) -> Decision:
    dimension = validate_required_code(db, None, "PM_DIMENSION", fields.get("dimension_code"), "dimension_code")
    target = _target(db, project_id, fields.get("supersedes_decision_id"))
    row = Decision(project_id=project_id, title=_text(fields.get("title"), "title"),
                   decision_text=_text(fields.get("decision_text"), "decision_text"),
                   alternative_rejected=_text(fields.get("alternative_rejected"), "alternative_rejected"),
                   analysis_code=_analysis(db, project_id, fields.get("analysis_code")),
                   dimension_code_id=dimension.code_id, decided_on=_decided_on(fields.get("decided_on")),
                   decided_by_user_id=actor_id, created_by=actor_id,
                   supersedes_decision_id=target.decision_id if target else None)
    row.decision_number = numbering.next_number(db, project_id, "DEC")     # at save, after every check (§9.8)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()                                                        # the number goes with it
        if SUPERSEDED_ONCE in str(exc.orig):
            raise _already(db, db.get(Decision, target.decision_id)) from None
        raise
    audit.record(db, "DECISION_RECORDED", actor_id=actor_id, project_id=project_id, target_table="decision",
                 target_id=row.decision_id,
                 detail={"decision_number": row.decision_number, "dimension": dimension.code,
                         "analysis": row.analysis_code,
                         "supersedes": target.decision_number if target else None})
    db.commit()
    db.refresh(row)
    attach_chain(db, [row])
    return row


def read_decision(db: Session, row: Decision) -> Decision:
    attach_chain(db, [row])
    return row
