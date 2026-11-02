"""Risks (§4.10, D-15; docs/slice_risks_spec.md; RK-1…RK-6, review R1 / R2). The one owner of risk writes.

A risk might happen and needs mitigation; an issue has happened and needs resolution — never merged. The score is
the database's (generated from the two weights the codes carry, law 6); this service only copies each code's
behaviour beside its id, which the composite FK then verifies. Every branch reads a behaviour, never a code (law 5);
OPEN and MATERIALISED are the codes looked up by value (pinned, R1-4).

Which route sets which status: raise starts OPEN; PATCH moves between OPEN- and CLOSED-behaviour codes; only
`materialise` sets MATERIALISED, inside the transaction that raises the issue. A materialised risk keeps its score,
codes, dates and text (the evidence it was foreseen, criterion 62) and cannot be retired (R1-2); its owner, node,
solution and wave may still be re-pointed so a restructure is never locked (RK-7, Ben 2026-11-02).

Audit (R1-3): RISK_RAISED / RISK_UPDATED / RISK_MATERIALISED carry codes, ids, numbers and the score — never title
or text (R7)."""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from models import BfcNode, CodeMaster, Issue, OrgRole, Phase, Risk, Solution
from models.shared import RISK_STATUS_BEHAVIOURS
from services import audit, components, issue as issue_service, lifecycle, numbering
from services.baseline import local_today
from services.code_master import resolve, validate_required_code

OPEN, CLOSED, MATERIALISED = RISK_STATUS_BEHAVIOURS
# What a PATCH may set, and the part of it a materialised risk still allows (R2 NEW-1).
FIELDS = ("title", "description", "probability_code", "impact_code", "mitigation", "owner_org_role_id",
          "status_code", "raised_date", "target_date", "bfc_node_id", "solution_id", "phase_id")
REPOINTABLE = frozenset({"owner_org_role_id", "bfc_node_id", "solution_id", "phase_id"})
LINKS = (("owner_org_role_id", OrgRole, "owner"), ("bfc_node_id", BfcNode, "node"),
         ("solution_id", Solution, "solution"), ("phase_id", Phase, "wave"))


# ---- checks ----------------------------------------------------------------------------------------------------------
def _text(value, field: str, required: bool = False) -> str | None:
    out = (value or "").strip() or None
    if required and out is None:
        raise HTTPException(422, f"{field} is required")
    return out


def _dates(raised: date, target: date | None) -> None:
    """R2 NEW-2: refused here with 422, so ck_risk_target_after_raised never surfaces as a 500."""
    if raised > local_today():
        raise HTTPException(422, "The raised date cannot be in the future")
    if target is not None and target < raised:
        raise HTTPException(422, "The target date cannot be before the raised date")


def _linked(db: Session, project_id: int, model, row_id: int | None, what: str, required: bool = False):
    """A live row of this project, read FOR SHARE so its retire and this save are serialised (SR-5). A missing,
    foreign or retired one is the same 422 — it is a choice in the body, not the resource addressed."""
    if row_id is None:
        if required:
            raise HTTPException(422, f"Choose the risk's {what}")
        return None
    row = db.get(model, row_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(422, f"Choose a live {what} of this project")
    lifecycle.lock_for_share(db, row)
    if not row.is_active:
        raise HTTPException(422, f"Choose a live {what} of this project")
    return row_id


def _pinned_status(db: Session, project_id: int, code: str, behaviour: str) -> CodeMaster:
    row = next((c for c in resolve(db, project_id, "RISK_STATUS") if c.code == code), None)
    if row is None or row.behaviour_code != behaviour:
        raise HTTPException(500, "Something went wrong.")        # pinned and behaviour-fixed (R1-4): never reached
    return row


def _snapshot(risk: Risk) -> dict:
    """What the audit keeps of a score: codes and the number, no text (R1-3, R7)."""
    return {"probability": risk.probability_code_row.code if risk.probability_code_row else None,
            "impact": risk.impact_code_row.code if risk.impact_code_row else None,
            "status": risk.status_code_row.code if risk.status_code_row else None,
            "exposure_score": risk.exposure_score}


def _set_code(db: Session, risk: Risk, field: str, code: str | None) -> None:
    if field == "probability_code":
        row = validate_required_code(db, risk.project_id, "RISK_PROBABILITY", code, field)
        risk.probability_code_id, risk.probability_weight = row.code_id, row.behaviour_code
    else:
        row = validate_required_code(db, risk.project_id, "RISK_IMPACT", code, field)
        risk.impact_code_id, risk.impact_weight = row.code_id, row.behaviour_code


def _finish(db: Session, risk: Risk) -> Risk:
    db.commit()
    db.refresh(risk)
    return risk


# ---- reads -----------------------------------------------------------------------------------------------------------
def list_risks(db: Session, project_id: int, include_retired: bool = False, *, status: str | None = None,
               owner_org_role_id: int | None = None, phase_id: int | None = None,
               issue_id: int | None = None) -> list[Risk]:
    """The register (§4.10 risk_register): open first, highest exposure, then oldest raised."""
    q = select(Risk).where(Risk.project_id == project_id)
    if not include_retired:
        q = q.where(Risk.is_active)
    if status:                                   # by code, so a project's wording of it matches too (G-3)
        q = q.where(Risk.status_code_id.in_(select(CodeMaster.code_id).where(
            CodeMaster.category == "RISK_STATUS", CodeMaster.code == status)))
    if owner_org_role_id is not None:
        q = q.where(Risk.owner_org_role_id == owner_org_role_id)
    if phase_id is not None:
        q = q.where(Risk.phase_id == phase_id)
    if issue_id is not None:
        q = q.where(Risk.materialised_issue_id == issue_id)
    q = q.order_by(case((Risk.status_behaviour == OPEN, 0), else_=1), Risk.exposure_score.desc(),
                   Risk.raised_date, Risk.risk_number)
    return list(db.scalars(q).unique())


# ---- writes ----------------------------------------------------------------------------------------------------------
def raise_risk(db: Session, actor_id: int, project_id: int, fields: dict) -> Risk:
    raised = fields.get("raised_date") or local_today()
    _dates(raised, fields.get("target_date"))
    status = _pinned_status(db, project_id, "OPEN", OPEN)
    risk = Risk(project_id=project_id, title=_text(fields.get("title"), "title", required=True),
                description=_text(fields.get("description"), "description"),
                mitigation=_text(fields.get("mitigation"), "mitigation"),
                status_code_id=status.code_id, status_behaviour=OPEN, raised_date=raised,
                target_date=fields.get("target_date"), created_by=actor_id)
    for field in ("probability_code", "impact_code"):
        _set_code(db, risk, field, fields.get(field))
    for field, model, what in LINKS:
        setattr(risk, field, _linked(db, project_id, model, fields.get(field), what,
                                     required=field == "owner_org_role_id"))
    risk.risk_number = numbering.next_number(db, project_id, "RSK")      # at save, after every check (§9.8)
    db.add(risk)
    db.flush()
    db.refresh(risk)                                                     # the generated score
    audit.record(db, "RISK_RAISED", actor_id=actor_id, project_id=project_id, target_table="risk",
                 target_id=risk.risk_id, detail={"risk_number": risk.risk_number, **_snapshot(risk)})
    return _finish(db, risk)


def update_risk(db: Session, actor_id: int, risk: Risk, row_version: int, fields: dict) -> Risk:
    lifecycle.lock(db, risk)
    lifecycle.check_live(risk, row_version)
    if risk.status_behaviour == MATERIALISED and set(fields) - REPOINTABLE:
        raise HTTPException(409, f"{risk.risk_number} has materialised: its score, dates and text are the record it "
                                 f"was foreseen. Only its owner, node, solution and wave can change")
    before = _snapshot(risk)
    if "status_code" in fields:
        row = validate_required_code(db, risk.project_id, "RISK_STATUS", fields["status_code"], "status_code")
        if row.behaviour_code == MATERIALISED:
            raise HTTPException(422, "Promote the risk to an issue to mark it materialised")
        risk.status_code_id, risk.status_behaviour = row.code_id, row.behaviour_code
    if "title" in fields:
        risk.title = _text(fields["title"], "title", required=True)
    for field in ("description", "mitigation"):
        if field in fields:
            setattr(risk, field, _text(fields[field], field))
    for field in ("probability_code", "impact_code"):
        if field in fields:
            _set_code(db, risk, field, fields[field])
    if "raised_date" in fields:
        if fields["raised_date"] is None:
            raise HTTPException(422, "raised_date cannot be empty")
        risk.raised_date = fields["raised_date"]
    if "target_date" in fields:
        risk.target_date = fields["target_date"]
    _dates(risk.raised_date, risk.target_date)
    for field, model, what in LINKS:
        if field in fields:
            setattr(risk, field, _linked(db, risk.project_id, model, fields[field], what,
                                         required=field == "owner_org_role_id"))
    risk.updated_by = actor_id
    db.flush()
    db.refresh(risk)
    audit.record(db, "RISK_UPDATED", actor_id=actor_id, project_id=risk.project_id, target_table="risk",
                 target_id=risk.risk_id, detail={"risk_number": risk.risk_number, "before": before,
                                                 "after": _snapshot(risk), "fields": sorted(fields)})
    return _finish(db, risk)


def materialise(db: Session, actor_id: int, risk: Risk, row_version: int, fields: dict) -> tuple[Risk, object]:
    """§4.10 promote_risk_to_issue: one transaction — the issue raised (title and description copied, raised today,
    its own optional target date, R1-1), the link set, the status MATERIALISED. The risk row stays (criterion 62)."""
    components.require_on(db, risk.project_id, "ISSUE")             # RISK: the route guard
    lifecycle.lock(db, risk)
    lifecycle.check_live(risk, row_version)
    if risk.status_behaviour == MATERIALISED:
        raise HTTPException(409, f"{risk.risk_number} has already materialised")
    status = _pinned_status(db, risk.project_id, "MATERIALISED", MATERIALISED)
    issue = issue_service.raise_issue(db, actor_id, risk.project_id, {
        "title": risk.title, "description": risk.description, "severity_code": fields.get("severity_code"),
        "issue_type_code": fields.get("issue_type_code"),
        "raised_by_stakeholder_id": fields.get("raised_by_stakeholder_id"),
        "target_date": fields.get("target_date")}, commit=False)
    before = _snapshot(risk)
    risk.materialised_issue_id = issue.issue_id
    risk.status_code_id, risk.status_behaviour = status.code_id, MATERIALISED
    risk.updated_by = actor_id
    db.flush()
    db.refresh(risk)
    audit.record(db, "RISK_MATERIALISED", actor_id=actor_id, project_id=risk.project_id, target_table="risk",
                 target_id=risk.risk_id, detail={"risk_number": risk.risk_number, "issue_number": issue.issue_number,
                                                 "before": before, "after": _snapshot(risk)})
    db.commit()
    db.refresh(risk)
    db.refresh(issue)
    return risk, issue


def retire_risk(db: Session, actor_id: int, risk: Risk, row_version: int) -> None:
    """RK-7: a materialised risk is the record it was foreseen — never retired."""
    if risk.status_behaviour == MATERIALISED:
        raise HTTPException(409, f"{risk.risk_number} has materialised: it stays as the record it was foreseen")
    lifecycle.retire(db, actor_id, risk, row_version)


def restore_risk(db: Session, actor_id: int, risk: Risk) -> Risk:
    """A retired owner, node, solution or wave refuses through lifecycle.restore; the number comes back with it."""
    lifecycle.lock(db, risk)
    lifecycle.restore(db, actor_id, risk)
    db.refresh(risk)
    return risk


def issue_number_of(db: Session, risk: Risk) -> str | None:
    if risk.materialised_issue_id is None:
        return None
    return db.scalar(select(Issue.issue_number).where(Issue.issue_id == risk.materialised_issue_id))


def risk_of_issue(db: Session, issue_id: int) -> Risk | None:
    """The issue page's "materialised from" (there is at most one, uq_risk_issue)."""
    return db.scalars(select(Risk).where(Risk.materialised_issue_id == issue_id)).first()
