"""Issue management (§4.5; docs/slice14_issue_spec.md; I-1…I-16). The one owner of stakeholder and issue writes.

Stakeholders: a named client-side person, no login (D-4); org unit optional (I-2); the live name is unique per org
unit (I-16). Retiring one is refused while a live issue names them (I-7) — lifecycle.retire finds that through the
FK. Audit labels carry ids and numbers only, never a name or title (R7).

Issues: ISS-0001 minted at save (§9.8). Which route sets which status (R2): raise starts OPEN; PATCH moves between
open-behaviour statuses only, and is refused on a closed issue ("use reopen", N1); only `resolve` sets a closed one,
with a resolution; only `reopen` returns to OPEN, clearing resolved_at / resolved_by and keeping the resolution text
(R3). Every branch reads the status's behaviour, never its code (law 5); OPEN is the one code looked up by value
(pinned, I-1). Locks (R11): the raiser is read FOR SHARE before its liveness check, so a stakeholder retire (FOR
UPDATE, then a count of live issues) and an issue save are serialised; the issue row itself is guarded by row_version
(sara B L-4)."""
from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import BfcNode, BusinessRequirement, CodeMaster, Issue, IssueBr, OrgUnit, Stakeholder
from models.shared import ISSUE_STATUS_BEHAVIOURS
from services import lifecycle, numbering
from services.baseline import local_today
from services.code_master import resolve, validate_required_code

OPEN, CLOSED = ISSUE_STATUS_BEHAVIOURS                # models.shared, migration 0061 (sara B L-6)
ISSUE_TEXT = ("title", "description")                 # law 6: the free fields a request may set



def _text(value: str | None, field: str, required: bool = False) -> str | None:
    v = (value or "").strip()
    if required and not v:
        raise HTTPException(422, f"{field} cannot be empty")
    if len(v) > 200:
        raise HTTPException(422, f"{field} is longer than 200 characters")
    return v or None


def _org_unit(db: Session, project_id: int, org_unit_id: int | None) -> int | None:
    """R11: the unit is read FOR SHARE, so a unit retire and a stakeholder save are serialised. Another project's
    unit is the same 422 as a missing one (a bad id in a body, as client_org.create_role; sara A M-3)."""
    if org_unit_id is None:
        return None
    unit = db.scalars(select(OrgUnit).where(OrgUnit.org_unit_id == org_unit_id,
                                            OrgUnit.project_id == project_id)).one_or_none()
    if unit is None:
        raise HTTPException(422, "Choose an org unit in this project")
    lifecycle.lock_for_share(db, unit)
    if not unit.is_active:
        raise HTTPException(409, f"{lifecycle.label(unit)} is retired. Restore it first.")
    return unit.org_unit_id


def _check_name_free(db: Session, project_id: int, org_unit_id: int | None, name: str,
                     stakeholder_id: int | None = None) -> None:
    """I-16: unique among live stakeholders of the same unit, as uq_stk_name_live normalises it. The index still
    decides a race; this names the clash in the ordinary case."""
    q = select(Stakeholder.stakeholder_id).where(
        Stakeholder.project_id == project_id, Stakeholder.is_active,
        func.coalesce(Stakeholder.org_unit_id, 0) == (org_unit_id or 0),
        func.lower(func.btrim(Stakeholder.stakeholder_name)) == name.strip().lower())
    if stakeholder_id is not None:
        q = q.where(Stakeholder.stakeholder_id != stakeholder_id)
    if db.scalar(q.limit(1)) is not None:
        raise HTTPException(409, "A stakeholder with this name already exists in this org unit")


def list_stakeholders(db: Session, project_id: int, include_retired: bool = False) -> list[Stakeholder]:
    q = select(Stakeholder).where(Stakeholder.project_id == project_id)
    if not include_retired:
        q = q.where(Stakeholder.is_active)
    return list(db.scalars(q.order_by(func.lower(Stakeholder.stakeholder_name), Stakeholder.stakeholder_id)))


def create_stakeholder(db: Session, actor_id: int, project_id: int, fields: dict) -> Stakeholder:
    name = _text(fields.get("stakeholder_name"), "stakeholder_name", required=True)
    unit_id = _org_unit(db, project_id, fields.get("org_unit_id"))
    _check_name_free(db, project_id, unit_id, name)
    stk = Stakeholder(project_id=project_id, org_unit_id=unit_id, stakeholder_name=name,
                      job_title=_text(fields.get("job_title"), "job_title"),
                      is_bpo=bool(fields.get("is_bpo", False)), created_by=actor_id)
    db.add(stk)
    db.commit()
    db.refresh(stk)
    return stk


def update_stakeholder(db: Session, actor_id: int, stk: Stakeholder, row_version: int, fields: dict) -> Stakeholder:
    lifecycle.check_live(stk, row_version)
    if "stakeholder_name" in fields:
        stk.stakeholder_name = _text(fields["stakeholder_name"], "stakeholder_name", required=True)
    if "job_title" in fields:
        stk.job_title = _text(fields["job_title"], "job_title")
    if "is_bpo" in fields:
        if fields["is_bpo"] is None:
            raise HTTPException(422, "is_bpo cannot be empty")
        stk.is_bpo = fields["is_bpo"]
    if "org_unit_id" in fields:
        stk.org_unit_id = _org_unit(db, stk.project_id, fields["org_unit_id"])
    _check_name_free(db, stk.project_id, stk.org_unit_id, stk.stakeholder_name, stk.stakeholder_id)
    stk.updated_by = actor_id
    db.commit()
    db.refresh(stk)
    return stk


def restore_stakeholder(db: Session, actor_id: int, stk: Stakeholder) -> Stakeholder:
    """A live namesake in the same unit may have been added meanwhile → 409. A retired unit refuses through
    lifecycle.restore (RESTORE_FIRST)."""
    lifecycle.lock(db, stk)
    if stk.is_active:
        raise HTTPException(409, f"{lifecycle.label(stk)} is not retired")
    _check_name_free(db, stk.project_id, stk.org_unit_id, stk.stakeholder_name, stk.stakeholder_id)
    lifecycle.restore(db, actor_id, stk)
    db.refresh(stk)
    return stk


# ---- issues (§4.5 raise_issue / resolve_issue; spec §14 R2, R3, R9, R11, R12) ---------------------------------------
def _raiser(db: Session, project_id: int, stakeholder_id: int | None) -> int:
    """R11: read FOR SHARE, so a stakeholder retire and an issue save are serialised. A missing, foreign or retired
    raiser is the same 422 (criterion 2) — it is a choice in the body, not the resource addressed."""
    if stakeholder_id is None:
        raise HTTPException(422, "raised_by_stakeholder_id is required")
    stk = db.scalars(select(Stakeholder).where(Stakeholder.stakeholder_id == stakeholder_id,
                                               Stakeholder.project_id == project_id)).one_or_none()
    if stk is not None:
        lifecycle.lock_for_share(db, stk)
    if stk is None or not stk.is_active:
        raise HTTPException(422, "Choose a live stakeholder of this project as the raiser")
    return stk.stakeholder_id


def _status(db: Session, project_id: int, code: str) -> CodeMaster:
    return validate_required_code(db, project_id, "ISSUE_STATUS", code, "status_code")


def _open_status(db: Session, project_id: int) -> CodeMaster:
    row = next((c for c in resolve(db, project_id, "ISSUE_STATUS") if c.code == "OPEN"), None)
    if row is None or row.behaviour_code != OPEN:
        raise HTTPException(500, "Something went wrong.")
    return row


def _dates(raised: date, target: date | None) -> None:
    if target is not None and target < raised:
        raise HTTPException(422, "The target date cannot be before the raised date")


def _set_status(issue: Issue, row: CodeMaster) -> None:
    issue.status_code_id, issue.status_behaviour = row.code_id, row.behaviour_code


def list_issues(db: Session, project_id: int, include_retired: bool = False, *, open_only: bool = False,
                status: str | None = None, severity: str | None = None, issue_type: str | None = None,
                raiser: int | None = None, area: str | None = None) -> list[Issue]:
    q = select(Issue).where(Issue.project_id == project_id)
    if area:                                                  # R4: the dashboard's own area rule
        q = q.where(Issue.issue_id.in_(issues_in_area(db, project_id, area) or {-1}))
    if not include_retired:
        q = q.where(Issue.is_active)
    if open_only:
        q = q.where(Issue.status_behaviour == OPEN)
    for code, col, cat in ((status, Issue.status_code_id, "ISSUE_STATUS"),
                           (severity, Issue.severity_code_id, "ISSUE_SEVERITY"),
                           (issue_type, Issue.issue_type_code_id, "ISSUE_TYPE")):
        if code:                                  # by code, so a project's override of it matches too (G-3)
            q = q.where(col.in_(select(CodeMaster.code_id).where(CodeMaster.category == cat, CodeMaster.code == code)))
    if raiser is not None:
        q = q.where(Issue.raised_by_stakeholder_id == raiser)
    return list(db.scalars(q.order_by(Issue.issue_number)).unique())


def raise_issue(db: Session, actor_id: int, project_id: int, fields: dict, commit: bool = True) -> Issue:
    """recorded_by is the JWT user, never the body (§9.2); the raiser is a stakeholder (D-4, D8). The raised date is
    the day raised, today in ICT unless given (I-6, R12)."""
    title = _text(fields.get("title"), "title", required=True)
    severity = validate_required_code(db, project_id, "ISSUE_SEVERITY", fields.get("severity_code"), "severity_code")
    itype = validate_required_code(db, project_id, "ISSUE_TYPE", fields.get("issue_type_code"), "issue_type_code")
    raised = fields.get("raised_date") or local_today()
    _dates(raised, fields.get("target_date"))
    raiser = _raiser(db, project_id, fields.get("raised_by_stakeholder_id"))
    issue = Issue(project_id=project_id, issue_number=numbering.next_number(db, project_id, "ISSUE"), title=title,
                  description=(fields.get("description") or "").strip() or None,
                  severity_code_id=severity.code_id, issue_type_code_id=itype.code_id,
                  raised_by_stakeholder_id=raiser, recorded_by_user_id=actor_id, raised_date=raised,
                  target_date=fields.get("target_date"), created_by=actor_id)
    _set_status(issue, _open_status(db, project_id))
    db.add(issue)
    db.flush()
    if not commit:                                            # slice 1e: an import writes more in this transaction
        return issue
    db.commit()
    db.refresh(issue)
    return issue


def update_issue(db: Session, actor_id: int, issue: Issue, row_version: int, fields: dict,
                 commit: bool = True) -> Issue:
    """R2 / N1: a status change here stays among the open statuses, and none at all while the issue is closed."""
    lifecycle.check_live(issue, row_version)
    if "status_code" in fields:
        row = _status(db, issue.project_id, fields["status_code"])
        if row.code_id != issue.status_code_id:
            if issue.status_behaviour != OPEN:
                raise HTTPException(409, f"{issue.issue_number} is closed: reopen it first")
            if row.behaviour_code != OPEN:
                raise HTTPException(422, "Resolve the issue to close it (a resolution is required)")
            _set_status(issue, row)
    if "title" in fields:
        issue.title = _text(fields["title"], "title", required=True)
    if "description" in fields:
        issue.description = (fields["description"] or "").strip() or None
    if "severity_code" in fields:
        issue.severity_code_id = validate_required_code(db, issue.project_id, "ISSUE_SEVERITY",
                                                        fields["severity_code"], "severity_code").code_id
    if "issue_type_code" in fields:
        issue.issue_type_code_id = validate_required_code(db, issue.project_id, "ISSUE_TYPE",
                                                          fields["issue_type_code"], "issue_type_code").code_id
    if "raised_date" in fields:
        if fields["raised_date"] is None:
            raise HTTPException(422, "raised_date cannot be empty")
        issue.raised_date = fields["raised_date"]
    if "target_date" in fields:
        issue.target_date = fields["target_date"]
    _dates(issue.raised_date, issue.target_date)
    if "raised_by_stakeholder_id" in fields:                     # R9: duplicates can be merged, then retired
        issue.raised_by_stakeholder_id = _raiser(db, issue.project_id, fields["raised_by_stakeholder_id"])
    issue.updated_by = actor_id
    db.flush()
    if not commit:                                            # slice 1e
        return issue
    db.commit()
    db.refresh(issue)
    return issue


def resolve_issue(db: Session, actor_id: int, issue: Issue, row_version: int, status_code: str,
                  resolution: str | None) -> Issue:
    """§4.5: a closed status needs a non-empty resolution; resolved_at / resolved_by come from the server. RESOLVED →
    CLOSED is a resolve too (a new resolution text and stamp)."""
    lifecycle.check_live(issue, row_version)
    row = _status(db, issue.project_id, status_code)
    if row.behaviour_code != CLOSED:
        raise HTTPException(422, f"{status_code} is an open status: use edit to set it")
    text_ = (resolution or "").strip()
    if not text_:
        raise HTTPException(422, "A resolution is required")
    _set_status(issue, row)
    issue.resolution = text_
    issue.resolved_at, issue.resolved_by_user_id = datetime.now(UTC), actor_id
    issue.updated_by = actor_id
    db.commit()
    db.refresh(issue)
    return issue


def reopen_issue(db: Session, actor_id: int, issue: Issue, row_version: int) -> Issue:
    """R3: back to OPEN; resolved_at / resolved_by clear; the resolution text stays until the next resolve."""
    lifecycle.check_live(issue, row_version)
    if issue.status_behaviour != CLOSED:
        raise HTTPException(409, f"{issue.issue_number} is not closed")
    _set_status(issue, _open_status(db, issue.project_id))
    issue.resolved_at = issue.resolved_by_user_id = None
    issue.updated_by = actor_id
    db.commit()
    db.refresh(issue)
    return issue


def restore_issue(db: Session, actor_id: int, issue: Issue) -> Issue:
    """A retired raiser refuses through lifecycle.restore (restore them first); the number comes back with the row."""
    lifecycle.lock(db, issue)
    lifecycle.restore(db, actor_id, issue)
    db.refresh(issue)
    return issue


# ---- links to BRs (§4.5 link_issue_br; spec §14 R1, R11; I-8) ------------------------------------------------------
def links_of(db: Session, issue: Issue, include_retired: bool = False) -> list[IssueBr]:
    q = select(IssueBr).where(IssueBr.issue_id == issue.issue_id)
    if not include_retired:
        q = q.where(IssueBr.is_active)
    return sorted(db.scalars(q), key=lambda r: r.br_row.br_number)


def link_br(db: Session, actor_id: int, issue: Issue, br_id: int, commit: bool = True) -> IssueBr:
    """A BR of another project — live, retired or missing — is the same 422 (criterion 4). Lock order (R11, SR-5):
    the step, then the BR, then the issue, all FOR SHARE, so a step retire and a link are serialised."""
    br = db.scalars(select(BusinessRequirement).where(BusinessRequirement.br_id == br_id,
                                                      BusinessRequirement.project_id == issue.project_id)).one_or_none()
    if br is None:
        raise HTTPException(422, "Choose a requirement of this project")
    lifecycle.lock_for_share(db, db.get(BfcNode, br.bfc_node_id))
    lifecycle.lock_for_share(db, br)
    lifecycle.lock_for_share(db, issue)
    for end in (br, issue):
        if not end.is_active:
            raise HTTPException(409, f"{lifecycle.label(end)} is retired. Restore it first.")
    row = db.scalars(select(IssueBr).where(IssueBr.issue_id == issue.issue_id, IssueBr.br_id == br.br_id)
                     .with_for_update(of=IssueBr)).one_or_none()
    if row is None:
        row = IssueBr(project_id=issue.project_id, issue_id=issue.issue_id, br_id=br.br_id, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{issue.issue_number} is already linked to {br.br_number}")
    else:                                                     # re-link restores the same row (S1-7)
        lifecycle.relink(db, actor_id, row)
    db.flush()
    if not commit:                                            # slice 1e
        return row
    db.commit()
    db.refresh(row)
    return row


def unlink_br(db: Session, actor_id: int, row: IssueBr, row_version: int) -> None:
    """R1: the caller fetched the link under its issue (lifecycle.child_of), so another issue's link is a 404."""
    lifecycle.unlink(db, actor_id, row, row_version)


# ---- the dashboard (§4.5 issue_dashboard; R4 / I-12, R5, I-11, I-13) ------------------------------------------------
NO_AREA = None


def _areas(db: Session, project_id: int) -> tuple[dict[int, set[int]], dict[int, BfcNode]]:
    """R4: issue id → the L1 areas it touches through a live link to a live BR of a live step; and the L1 nodes."""
    nodes = {n.bfc_node_id: n for n in db.scalars(select(BfcNode).where(BfcNode.project_id == project_id,
                                                                         BfcNode.is_active))}
    l1 = {(n.bfc_set_code, n.hier_code): n for n in nodes.values() if n.level_no == 1}
    rows = db.execute(select(IssueBr.issue_id, BusinessRequirement.bfc_node_id)
                      .join(BusinessRequirement, BusinessRequirement.br_id == IssueBr.br_id)
                      .where(IssueBr.project_id == project_id, IssueBr.is_active, BusinessRequirement.is_active))
    out: dict[int, set[int]] = {}
    for issue_id, node_id in rows:
        step = nodes.get(node_id)
        area = step and l1.get((step.bfc_set_code, step.hier_code.split(".", 1)[0]))
        if area is not None:
            out.setdefault(issue_id, set()).add(area.bfc_node_id)
    return out, {n.bfc_node_id: n for n in l1.values()}


def issues_in_area(db: Session, project_id: int, area: str) -> set[int]:
    """The list's area filter, by the same rule (R4): an L1 node id, or "none" for issues with no area."""
    by_issue, _ = _areas(db, project_id)
    if area == "none":
        every = set(db.scalars(select(Issue.issue_id).where(Issue.project_id == project_id)))
        return every - set(by_issue)
    try:
        wanted = int(area)
    except ValueError:
        raise HTTPException(422, "area must be an L1 node id or 'none'")
    return {i for i, a in by_issue.items() if wanted in a}


def open_counts(open_: list[Issue]) -> dict:
    """The one definition behind the dashboard's tiles and the M3 tile (sara C M3): open issues, of which severity
    CRITICAL only (I-13), and overdue — target date passed in ICT, DEFERRED included (I-11, R5)."""
    today = local_today()
    return {"open": len(open_), "critical": sum(1 for i in open_ if i.severity_code == "CRITICAL"),
            "overdue": sum(1 for i in open_ if i.target_date is not None and i.target_date < today)}


def dashboard(db: Session, project_id: int) -> dict:
    """Open issues (every open-behaviour status, DEFERRED included — I-11) by severity × type, by area (rows do not
    sum to the total — R4), by raiser, and overdue (target date passed, ICT — R5). `critical` is the M3 tile's figure:
    open issues of severity CRITICAL only (I-13)."""
    open_ = list_issues(db, project_id, open_only=True)
    severities = [c.code for c in sorted(resolve(db, project_id, "ISSUE_SEVERITY"), key=lambda c: c.sort_order)]
    types = [c.code for c in sorted(resolve(db, project_id, "ISSUE_TYPE"), key=lambda c: c.sort_order)]
    matrix = {s: {t: 0 for t in types} for s in severities}
    for i in open_:
        matrix.setdefault(i.severity_code, {t: 0 for t in types}).setdefault(i.issue_type_code, 0)
        matrix[i.severity_code][i.issue_type_code] += 1
    by_issue, l1 = _areas(db, project_id)
    area_counts: dict[int | None, int] = {}
    for i in open_:
        for a in by_issue.get(i.issue_id) or {NO_AREA}:
            area_counts[a] = area_counts.get(a, 0) + 1
    areas = [{"area_id": a, "hier_code": l1[a].hier_code, "name": l1[a].node_name,
              "bfc_set_code": l1[a].bfc_set_code, "open": n}
             for a, n in sorted(((a, n) for a, n in area_counts.items() if a is not NO_AREA),
                                key=lambda x: (l1[x[0]].bfc_set_code != "TO_BE", l1[x[0]].hier_code))]
    names = {s.stakeholder_id: s.stakeholder_name for s in db.scalars(
        select(Stakeholder).where(Stakeholder.project_id == project_id))}
    raisers: dict[int, int] = {}
    for i in open_:
        raisers[i.raised_by_stakeholder_id] = raisers.get(i.raised_by_stakeholder_id, 0) + 1
    return {
        **open_counts(open_),
        "severities": severities, "types": types,
        "by_severity_type": [{"severity_code": s, "counts": matrix[s]} for s in matrix],
        "by_area": areas, "no_area": area_counts.get(NO_AREA, 0),
        "by_raiser": sorted(({"stakeholder_id": k, "name": names.get(k, ""), "open": n} for k, n in raisers.items()),
                            key=lambda r: (-r["open"], r["name"].lower())),
    }
