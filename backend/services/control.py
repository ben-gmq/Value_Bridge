"""Control rules and the control panel (D-19; design §5.3 CONTROL_RULE, §7.13; docs/slice_control_a_spec.md;
CT-1…CT-4, Ben 2026-10-30).

The house tier (project_id NULL) is copied into each project — never referenced — so a project's thresholds stay what
FTC and the client agreed when the house standard moves. A rule exists only for an analysis that has a headline (CT-4):
each later slice adds its own row to HOUSE_RULES and runs seeds.seed_control_rules.

Every analysis returns {measured, unit, reason, note}. measured None + reason is NOT_MEASURED, never 0 (§7.9)."""
import getpass
import socket
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AppUser, AuditEvent, Baseline, ControlRule, FunctionRequirement, OrgRole, Project
from models.control import REGISTRY
from services import audit, baseline, components, control_reports, reports
from services.lifecycle import check_version

CENT = Decimal("0.01")

# CT-4: the analyses with a headline today, in panel order (Control-B / C in their specs' order, §2). (code, unit, comparison, flag, escalate, action)
HOUSE_RULES = (
    ("priced_diff", "PCT", "PCT_GT", Decimal(5), Decimal(10),
     "Raise a CR to steering; name the displacement"),
    ("coverage", "COUNT", "GT", Decimal(0), None,
     "Assign owner + date per gap; do not pass the gate"),
    ("solution_matrix", "PCT", "PCT_GT", Decimal(70), Decimal(85),
     "Commission the org/process workstream, or lower the benefit forecast"),
    ("interface_load", "PCT", "PCT_GT", Decimal(25), Decimal(35),
     "Stand up an integration workstream; book test environments"),
    # Control-B1 (CB-1, CB-4): an area changed at two freezes running flags, three escalates; any entity needing a
    # data-ownership decision flags, more than five escalate.
    ("requirement_volatility", "COUNT", "GT", Decimal(1), Decimal(2),
     "Pull the area out of the current wave; re-run the workshop"),
    # Control-B2 (CB-2, CB-3): one org unit responsible or accountable for more than 40 % of the changes flags, over
    # 60 % escalates; an affected unit with no voice on more than 10 % flags, over 25 % escalates.
    ("org_impact_heatmap", "PCT", "PCT_GT", Decimal(40), Decimal(60),
     "Dedicated change agent and a capacity check — they are usually the SMEs too"),
    ("stakeholder_engagement", "PCT", "PCT_GT", Decimal(10), Decimal(25),
     "Interview before sign-off — silence becomes rejection at UAT"),
    ("data_migration_map", "COUNT", "GT", Decimal(0), Decimal(5),
     "Data ownership decision before design freeze"),
    # Control-C (CC-1, CC-2): more than half of the changed steps in one L1 area flags, over 70 % escalates; any shared
    # entity with no business owner flags, more than five escalate.
    ("process_change_intensity", "PCT", "PCT_GT", Decimal(50), Decimal(70),
     "Check the change workload and the change-management plan for that area before the next gate"),
    ("master_data_candidates", "COUNT", "GT", Decimal(0), Decimal(5),
     "Assign a single owner; it becomes a managed cross-workstream dependency"),
)
ORDER = {code: i for i, (code, *_) in enumerate(HOUSE_RULES)}
UNIT = {code: unit for code, unit, *_ in HOUSE_RULES}
# Shown under the panel: the analyses still to come and what brings each (spec §1).
COMING = (("benefit_gap", "BENEFITS"), ("risk_register", "RISKS"))
EDITABLE = ("threshold_value", "escalate_value", "owner_org_role_id", "prescribed_action", "escalation_path",
            "is_enabled")
TEXT_FIELDS = ("prescribed_action", "escalation_path")         # CT-3: audited as "changed" only — they name people
NO_HOUSE = "The FTC house control rules are not seeded: run seeds.seed_control_rules"


# ---- the house tier and copying it ---------------------------------------------------------------------------------
def seed_house(db: Session) -> list[str]:
    """Insert the house rows that are missing; never overwrite one (after the first run they are platform-admin
    data). No author (deviation 7j). No commit."""
    have = set(db.scalars(select(ControlRule.analysis_code).where(ControlRule.project_id.is_(None))))
    added = []
    for code, _unit, comparison, flag, escalate, action in HOUSE_RULES:
        if code not in have:
            db.add(ControlRule(project_id=None, analysis_code=code, comparison=comparison, threshold_value=flag,
                               escalate_value=escalate, prescribed_action=action, is_house_default=True))
            added.append(code)
    db.flush()
    return added


def copy_to_project(db: Session, project_id: int, actor_id: int, require_house: bool = False,
                    enabled: bool = True) -> list[str]:
    """Copy each house rule the project lacks (CT-4); owner NULL until the project names one (CT-1). No commit —
    create_project owns the transaction. An empty house tier is a 409 when `require_house` (create_project).
    CB-5: a running engagement's copies arrive switched off (`enabled=False`) until the client agrees them."""
    house = db.scalars(select(ControlRule).where(ControlRule.project_id.is_(None))
                       .order_by(ControlRule.control_rule_id)).all()
    # round 2 N4: every analysis the code can measure must have its house row, not merely one row.
    if require_house and set(ORDER) - {h.analysis_code for h in house}:
        raise HTTPException(409, NO_HOUSE)
    have = set(db.scalars(select(ControlRule.analysis_code).where(ControlRule.project_id == project_id)))
    added = []
    for h in house:
        if h.analysis_code in have:
            continue
        db.add(ControlRule(project_id=project_id, analysis_code=h.analysis_code, comparison=h.comparison,
                           threshold_value=h.threshold_value, escalate_value=h.escalate_value,
                           prescribed_action=h.prescribed_action, escalation_path=h.escalation_path,
                           is_enabled=h.is_enabled and enabled, is_house_default=False, created_by=actor_id))
        added.append(h.analysis_code)
    db.flush()
    return added


def backfill(db: Session, actor_email: str | None) -> dict:
    """CLI: the house rows, then (with an actor) every live project's missing rules — one transaction and one
    CONTROL_RULES_SEEDED audit per project; the OS user and host are recorded (DR6c-S1)."""
    house = seed_house(db)
    db.commit()
    out = {"house_added": house, "projects": []}
    if actor_email is None:
        return out
    actor = db.scalars(select(AppUser).where(func.lower(AppUser.email) == actor_email.strip().lower())).one_or_none()
    if actor is None or not actor.is_active or not actor.is_platform_admin:
        raise SystemExit("--actor-email must be an active platform admin")
    for p in db.scalars(select(Project).where(Project.is_active).order_by(Project.project_id)).all():
        added = copy_to_project(db, p.project_id, actor.app_user_id, enabled=False)          # CB-5
        if added:
            audit.record(db, "CONTROL_RULES_SEEDED", actor_id=actor.app_user_id, project_id=p.project_id,
                         detail={"analysis_codes": added, "os_user": getpass.getuser(),
                                 "host": socket.gethostname()})
        db.commit()
        out["projects"].append({"project_id": p.project_id, "added": added})
    return out


# ---- reading and editing a project's rules -------------------------------------------------------------------------
def _rules(db: Session, project_id: int) -> list[ControlRule]:
    rows = db.scalars(select(ControlRule).where(ControlRule.project_id == project_id, ControlRule.is_active)).all()
    return sorted(rows, key=lambda r: (ORDER.get(r.analysis_code, len(ORDER)), r.analysis_code))


def _rule_out(r: ControlRule, roles: dict[int, OrgRole], users: dict[int, str]) -> dict:
    role = roles.get(r.owner_org_role_id) if r.owner_org_role_id else None
    return {"analysis_code": r.analysis_code, "unit": UNIT.get(r.analysis_code, "COUNT"),
            "comparison": r.comparison, "threshold_value": r.threshold_value, "escalate_value": r.escalate_value,
            "owner_org_role_id": r.owner_org_role_id,
            "owner": {"org_role_code": role.org_role_code, "org_role_name": role.org_role_name} if role else None,
            "prescribed_action": r.prescribed_action, "escalation_path": r.escalation_path,
            "is_enabled": r.is_enabled, "change_rationale": r.change_rationale, "agreed_at": r.agreed_at,
            "last_changed_at": r.updated_at if r.row_version > 1 else None,
            "last_changed_by": users.get(r.updated_by) if r.row_version > 1 else None,
            "row_version": r.row_version}


def _names(db: Session, rules: list[ControlRule]) -> tuple[dict, dict]:
    role_ids = {r.owner_org_role_id for r in rules if r.owner_org_role_id}
    user_ids = {r.updated_by for r in rules if r.updated_by}
    roles = {o.org_role_id: o for o in db.scalars(select(OrgRole).where(OrgRole.org_role_id.in_(role_ids)))} \
        if role_ids else {}
    users = {u.app_user_id: u.display_name for u in db.scalars(select(AppUser).where(
        AppUser.app_user_id.in_(user_ids)))} if user_ids else {}
    return roles, users


def list_rules(db: Session, project_id: int) -> list[dict]:
    rules = _rules(db, project_id)
    roles, users = _names(db, rules)
    return [_rule_out(r, roles, users) for r in rules]


def _clean_text(v: str | None) -> str | None:
    v = v.strip() if v is not None else None
    return v or None


def _plain(v):
    return format(v.normalize(), "f") if isinstance(v, Decimal) else v


def _reason(change_rationale: str | None) -> str:
    reason = (change_rationale or "").strip()
    if not reason:
        raise HTTPException(422, "Changing a control threshold is a governance decision and needs a reason")
    return reason


def _checked(r: ControlRule, values: dict) -> dict:
    """The number and text checks every rule edit shares — a project rule, a company default (CC-6)."""
    for f in TEXT_FIELDS:
        values[f] = _clean_text(values[f])
    threshold, escalate = values["threshold_value"], values["escalate_value"]
    if threshold is None or threshold < 0 or (escalate is not None and escalate < 0):
        raise HTTPException(422, "Thresholds are zero or more")
    if escalate is not None:
        beyond = escalate < threshold if r.comparison == "LT" else escalate > threshold
        if not beyond:
            side = "below" if r.comparison == "LT" else "above"
            raise HTTPException(422, f"The escalate value must be {side} the threshold")
    return values


def _change_detail(code: str, diff: dict, reason: str) -> dict:
    """CT-3: numbers, owner and on/off from / to; the two text fields only as changed; the reason in full."""
    return {"analysis_code": code,
            "from": {f: _plain(old) for f, (old, _) in diff.items() if f not in TEXT_FIELDS},
            "to": {f: _plain(new) for f, (_, new) in diff.items() if f not in TEXT_FIELDS},
            "text_changed": [f for f in TEXT_FIELDS if f in diff], "change_rationale": reason}


def update_rule(db: Session, actor: AppUser, project_id: int, analysis_code: str, values: dict,
                change_rationale: str, row_version: int) -> dict:
    """§7.13 maintain_control_rule at EDIT (SC-7). The body replaces every editable field (spec §4). A change with
    nothing different writes nothing. CT-3: the audit carries numbers, owner id and on/off; the two text fields only
    as changed."""
    if analysis_code not in REGISTRY:
        raise HTTPException(422, "No such analysis")
    r = db.scalar(select(ControlRule).where(ControlRule.project_id == project_id,
                                            ControlRule.analysis_code == analysis_code,
                                            ControlRule.is_active).with_for_update())
    if r is None:
        raise HTTPException(404, "This project has no rule for that analysis")
    check_version(r, row_version)
    reason = _reason(change_rationale)
    values = _checked(r, {f: values[f] for f in EDITABLE})
    owner = values["owner_org_role_id"]
    if owner is not None:
        role = db.get(OrgRole, owner)
        if role is None or role.project_id != project_id or not role.is_active:
            raise HTTPException(422, "Choose a live role of this project's organisation")
    diff = {f: (getattr(r, f), v) for f, v in values.items() if getattr(r, f) != v}
    if not diff:
        return list_rules_one(db, r)
    for f, (_, v) in diff.items():
        setattr(r, f, v)
    r.change_rationale = reason
    r.updated_by = actor.app_user_id
    audit.record(db, "CONTROL_RULE_CHANGED", actor_id=actor.app_user_id, project_id=project_id,
                 target_table="control_rule", target_id=r.control_rule_id,
                 detail=_change_detail(analysis_code, diff, reason))
    db.commit()
    db.refresh(r)
    return list_rules_one(db, r)


def list_rules_one(db: Session, r: ControlRule) -> dict:
    roles, users = _names(db, [r])
    return _rule_out(r, roles, users)


# ---- the FTC company defaults (docs/slice_control_c_spec.md §3; CC-6) ----------------------------------------------
HOUSE_EDITABLE = ("threshold_value", "escalate_value", "prescribed_action", "escalation_path")   # R1-D1: never owner
RESET_FIELDS = HOUSE_EDITABLE                                                                  # CC-4: nor on / off


def _house(db: Session, lock=None) -> list[ControlRule]:
    q = select(ControlRule).where(ControlRule.project_id.is_(None), ControlRule.is_active)
    if lock == "share":
        q = q.with_for_update(read=True)
    rows = db.scalars(q).all()
    return sorted(rows, key=lambda r: (ORDER.get(r.analysis_code, len(ORDER)), r.analysis_code))


def list_house(db: Session) -> list[dict]:
    """Each company default with its change history from the audit trail (R1-P4) — what FTC's close-out review reads."""
    rows = _house(db)
    events = db.execute(select(AuditEvent, AppUser.display_name).outerjoin(
        AppUser, AppUser.app_user_id == AuditEvent.app_user_id).where(
        AuditEvent.event_type == "CONTROL_RULE_CHANGED", AuditEvent.target_table == "control_rule",
        AuditEvent.project_id.is_(None), AuditEvent.target_id.in_([r.control_rule_id for r in rows]))
        .order_by(AuditEvent.audit_event_id.desc())).all()
    history: dict[int, list[dict]] = {}
    for e, name in events:
        d = e.detail or {}
        history.setdefault(e.target_id, []).append({
            "at": e.occurred_at, "by": name, "from": d.get("from", {}), "to": d.get("to", {}),
            "text_changed": d.get("text_changed", []), "change_rationale": d.get("change_rationale")})
    _, users = _names(db, rows)
    return [{**_rule_out(r, {}, users), "history": history.get(r.control_rule_id, [])} for r in rows]


def update_house(db: Session, actor: AppUser, analysis_code: str, values: dict, change_rationale: str,
                 row_version: int) -> dict:
    """§7.13 maintain_house_default (CC-6): a platform admin, a reason, a current version; future projects only."""
    r = db.scalar(select(ControlRule).where(ControlRule.project_id.is_(None), ControlRule.analysis_code == analysis_code,
                                            ControlRule.is_active).with_for_update())
    if r is None:
        raise HTTPException(404, "There is no company default for that analysis")
    check_version(r, row_version)
    reason = _reason(change_rationale)
    values = _checked(r, {f: values[f] for f in HOUSE_EDITABLE})
    diff = {f: (getattr(r, f), v) for f, v in values.items() if getattr(r, f) != v}
    if diff:
        for f, (_, v) in diff.items():
            setattr(r, f, v)
        r.change_rationale = reason
        r.updated_by = actor.app_user_id
        audit.record(db, "CONTROL_RULE_CHANGED", actor_id=actor.app_user_id, project_id=None,
                     target_table="control_rule", target_id=r.control_rule_id,
                     detail={"house": True, **_change_detail(analysis_code, diff, reason)})
        db.commit()
        db.refresh(r)
    return next(h for h in list_house(db) if h["analysis_code"] == analysis_code)


# ---- reset a project's rules to the company defaults (spec §4; CC-4) -----------------------------------------------
STALE_RESET = "The rules or the FTC defaults changed since the preview. Open the preview again"


def _stamp(rules: list[ControlRule], house: list[ControlRule]) -> dict:
    return {"project": {r.analysis_code: r.row_version for r in rules},
            "house": {h.analysis_code: h.row_version for h in house}}


def _plan(rules: list[ControlRule], house: list[ControlRule]) -> tuple[list[tuple], list[ControlRule]]:
    """(rule, house row, diff) for each rule a reset would change, and the house rows the project lacks."""
    mine = {r.analysis_code: r for r in rules}
    changes, added = [], []
    for h in house:
        r = mine.get(h.analysis_code)
        if r is None:
            added.append(h)
            continue
        diff = {f: (getattr(r, f), getattr(h, f)) for f in RESET_FIELDS if getattr(r, f) != getattr(h, f)}
        if diff:
            changes.append((r, h, diff))
    return changes, added


def _side(row) -> dict:
    return {f: getattr(row, f) for f in RESET_FIELDS}


def reset_preview(db: Session, project_id: int) -> dict:
    rules, house = _rules(db, project_id), _house(db)
    changes, added = _plan(rules, house)
    return {"changes": [{"analysis_code": r.analysis_code, "unit": UNIT.get(r.analysis_code, "COUNT"),
                         "comparison": r.comparison, "is_enabled": r.is_enabled, "current": _side(r),
                         "default": _side(h), "fields": list(diff)} for r, h, diff in changes],
            "added": [h.analysis_code for h in added], "stamp": _stamp(rules, house)}


def reset(db: Session, actor: AppUser, project_id: int, change_rationale: str, stamp: dict) -> dict:
    """§7.13 reset_project_rules_to_house_default at EDIT. Locks the project's rules and the house rows, refuses unless
    every version matches the preview's stamp (R1-P1, R1-P3), keeps owner and on/off (CC-4), adds missing rules off.
    Nothing to change → nothing written."""
    reason = _reason(change_rationale)
    rules = db.scalars(select(ControlRule).where(ControlRule.project_id == project_id, ControlRule.is_active)
                       .order_by(ControlRule.control_rule_id).with_for_update()).all()
    house = _house(db, lock="share")
    if _stamp(rules, house) != {"project": stamp.get("project"), "house": stamp.get("house")}:
        raise HTTPException(409, STALE_RESET)
    changes, added = _plan(rules, house)
    if not changes and not added:
        db.rollback()
        return {"changed": [], "added": []}
    for r, _h, diff in changes:
        for f, (_, v) in diff.items():
            setattr(r, f, v)
        r.change_rationale = reason
        r.updated_by = actor.app_user_id
    try:
        new = copy_to_project(db, project_id, actor.app_user_id, enabled=False) if added else []
    except IntegrityError:                         # round 2 N1: the seed added the same rule meanwhile
        db.rollback()
        raise HTTPException(409, STALE_RESET) from None
    db.flush()
    audit.record(db, "CONTROL_RULES_RESET", actor_id=actor.app_user_id, project_id=project_id,
                 detail={"change_rationale": reason, "changed": [r.analysis_code for r, _, _ in changes],
                         "added": new, "rule_ids": [r.control_rule_id for r, _, _ in changes],
                         "rules": [{k: v for k, v in _change_detail(r.analysis_code, diff, reason).items()
                                    if k != "change_rationale"} for r, _, diff in changes]})
    db.commit()
    return {"changed": [r.analysis_code for r, _, _ in changes], "added": new}


def _reset_marks(db: Session, project_id: int, rules: list[ControlRule]) -> dict[int, dict]:
    """Rules whose latest event is a reset (round 2 N2): a later CONTROL_RULE_CHANGED on the rule clears the mark, so
    a threshold the client then agreed never reads as "reset to FTC defaults" (R1-P2)."""
    resets = db.execute(select(AuditEvent, AppUser.display_name).outerjoin(
        AppUser, AppUser.app_user_id == AuditEvent.app_user_id).where(
        AuditEvent.event_type == "CONTROL_RULES_RESET", AuditEvent.project_id == project_id)
        .order_by(AuditEvent.audit_event_id)).all()
    if not resets:
        return {}
    last: dict[int, tuple] = {}
    for e, name in resets:
        for rid in (e.detail or {}).get("rule_ids", []):
            last[rid] = (e, name)
    edited = dict(db.execute(select(AuditEvent.target_id, func.max(AuditEvent.audit_event_id)).where(
        AuditEvent.event_type == "CONTROL_RULE_CHANGED", AuditEvent.target_table == "control_rule",
        AuditEvent.target_id.in_(list(last))).group_by(AuditEvent.target_id)).all())
    ids = {r.control_rule_id for r in rules}
    return {rid: {"at": e.occurred_at, "by": name, "change_rationale": (e.detail or {}).get("change_rationale")}
            for rid, (e, name) in last.items() if rid in ids and edited.get(rid, 0) < e.audit_event_id}


# ---- the analyses' headlines (§7.9 contract) -----------------------------------------------------------------------
def _measure(measured=None, reason=None, **figures) -> dict:
    if measured is not None:
        measured = Decimal(str(measured)).quantize(CENT, ROUND_HALF_UP)
    return {"measured": measured, "reason": reason, "figures": figures}


def _priced_diff(db: Session, project_id: int, on: frozenset) -> dict:
    """Net effort growth % from the agreed (client-approved) baseline to live (A1). CT-2: unrated added or changed
    FRs are named, and turn a GREEN into FLAG in the verdict."""
    agreed = baseline.agreed_id(baseline.list_baselines(db, project_id))
    if agreed is None:
        return _measure(reason="NO_AGREED_BASELINE")
    b = db.get(Baseline, agreed)
    if "EFFORT" not in on:
        return _measure(reason="EFFORT_OFF")
    if not baseline.verify(db, b):                                  # review D4: this row only
        return _measure(reason="BASELINE_DAMAGED", baseline_label=b.version_label)
    d = baseline.diff(db, project_id, b, baseline.LIVE)
    p = baseline.priced(d, b, baseline.LIVE, frozenset(baseline.components_of(db, b.baseline_id)), on)
    if not p["available"]:
        return _measure(reason="EFFORT_OFF")
    t = p["totals"]
    if not t["base_days"]:
        return _measure(reason="NO_BASE_EFFORT", baseline_label=b.version_label)
    # round 2 N1: only ADDED / CHANGED lines whose live side is unrated — a removed unrated FR can never be rated.
    unrated = sum(1 for x in p["lines"] if x["unrated"] and x["change"] in ("ADDED", "CHANGED"))
    pct = Decimal(str(t["net_days"])) * 100 / Decimal(str(t["base_days"]))
    return _measure(pct, baseline_label=b.version_label, added_days=t["added_days"],
                    removed_days=t["removed_days"], net_days=t["net_days"], base_days=t["base_days"],
                    unrated_count=unrated)


def _coverage(db: Session, project_id: int) -> dict:
    """Rows on the coverage report's warning lines (A2); every warning line off → not measured (review D3)."""
    lines = [ln for ln in reports.coverage(db, project_id)["lines"] if ln["severity"] == "warning"]
    on = [ln for ln in lines if ln["rows"] is not None]
    if not on:
        return _measure(reason="COMPONENTS_OFF")
    return _measure(sum(len(ln["rows"]) for ln in on))


def _solution_matrix(db: Session, project_id: int, on: frozenset) -> dict:
    if "SOLUTION" not in on:
        return _measure(reason="SOLUTION_OFF")
    share = reports.solution_matrix(db, project_id)["technology_share"]
    return _measure(share) if share is not None else _measure(reason="NO_SOLUTIONS")


def _interface_load(db: Session, project_id: int, on: frozenset) -> dict:
    """INTERFACE FRs as % of live FRs — by the type's behaviour, never its code (VB law 5)."""
    if "FUNCTION_REQUIREMENT" not in on:
        return _measure(reason="FUNCTION_REQUIREMENT_OFF")
    total, iface = db.execute(select(
        func.count(), func.count().filter(FunctionRequirement.fr_type_behaviour == "INTERFACE")).where(
        FunctionRequirement.project_id == project_id, FunctionRequirement.is_active)).one()
    if not total:
        return _measure(reason="NO_FRS")
    return _measure(Decimal(iface) * 100 / Decimal(total), interface_count=iface, fr_count=total)


def _from_report(report: dict) -> dict:
    """A Control-B report's own headline, so the tab and the panel read one computation (spec §3)."""
    h = dict(report["headline"])
    return _measure(h.pop("measured"), h.pop("reason"), **h)


def headline(db: Session, project_id: int, code: str, on: frozenset) -> dict:
    if code == "priced_diff":
        return _priced_diff(db, project_id, on)
    if code == "coverage":
        return _coverage(db, project_id)
    if code == "solution_matrix":
        return _solution_matrix(db, project_id, on)
    if code == "interface_load":
        return _interface_load(db, project_id, on)
    if code == "requirement_volatility":
        return _from_report(control_reports.requirement_volatility(db, project_id))
    if code == "org_impact_heatmap":
        return _from_report(control_reports.org_impact_heatmap(db, project_id))
    if code == "stakeholder_engagement":
        return _from_report(control_reports.stakeholder_engagement(db, project_id))
    if code == "data_migration_map":
        return _from_report(control_reports.data_migration_map(db, project_id))
    if code == "process_change_intensity":
        return _from_report(control_reports.process_change_intensity(db, project_id))
    if code == "master_data_candidates":
        return _from_report(control_reports.master_data_candidates(db, project_id))
    return _measure(reason="NOT_BUILT")


def _breaches(measured: Decimal, limit: Decimal | None, comparison: str) -> bool:
    if limit is None:
        return False
    return measured < limit if comparison == "LT" else measured > limit       # equal is not a breach


def verdict(rule: ControlRule, m: dict) -> str | None:
    if not rule.is_enabled:
        return None
    if m["measured"] is None:
        return "NOT_MEASURED"
    if _breaches(m["measured"], rule.escalate_value, rule.comparison):
        return "ESCALATE"
    if _breaches(m["measured"], rule.threshold_value, rule.comparison):
        return "FLAG"
    if rule.analysis_code == "priced_diff" and m["figures"].get("unrated_count"):
        return "FLAG"                                                          # CT-2: uncosted growth is not GREEN
    return "GREEN"


def _switched_on_ever(db: Session, rules: list[ControlRule]) -> set[int]:
    """Rules whose on/off a person has ever set — any CONTROL_RULE_CHANGED carrying is_enabled. A rule that is off and
    never was set arrived off from the backfill: "not yet agreed with the client" (CB-5, review round 2 N2 — naming
    an owner does not make it "switched off"). A rule copied off because its house row was off reads the same way
    (sara B1 L6, accepted: the house tier switches rules off only when FTC has not agreed them either)."""
    ids = [r.control_rule_id for r in rules if not r.is_enabled]
    if not ids:
        return set()
    return set(db.scalars(select(AuditEvent.target_id).where(
        AuditEvent.event_type == "CONTROL_RULE_CHANGED", AuditEvent.target_table == "control_rule",
        AuditEvent.target_id.in_(ids), AuditEvent.detail["to"].has_key("is_enabled"))))


def panel(project_id: int) -> dict:
    """§7.13 control_panel: one read-only REPEATABLE READ snapshot (as diff_for_api), so every figure describes one
    state of the data. CB-5: a switched-off rule is still measured and shown with no verdict."""
    with SessionLocal() as db:
        db.connection(execution_options={"isolation_level": "REPEATABLE READ", "postgresql_readonly": True})
        on = frozenset(components.enabled(db, project_id))
        rules = _rules(db, project_id)
        roles, users = _names(db, rules)
        set_by_hand = _switched_on_ever(db, rules)
        marks = _reset_marks(db, project_id, rules)
        rows = []
        for r in rules:
            m = headline(db, project_id, r.analysis_code, on)
            off = None if r.is_enabled else "SWITCHED_OFF" if r.control_rule_id in set_by_hand else "NOT_YET_AGREED"
            rows.append({**_rule_out(r, roles, users), **m, "verdict": verdict(r, m), "off_state": off,
                         "reset": marks.get(r.control_rule_id)})
        db.rollback()
    have = {r["analysis_code"] for r in rows}
    # round 2 N4: a measurable rule the project lacks is listed too, so a missing rule always shows somewhere.
    missing = [{"analysis_code": c, "brought_by": "SEED"} for c in ORDER if c not in have]
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "rows": rows,
            "coming": missing + [{"analysis_code": c, "brought_by": by} for c, by in COMING if c not in have]}
