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
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AppUser, AuditEvent, Baseline, ControlRule, FunctionRequirement, OrgRole, Project
from models.control import REGISTRY
from services import audit, baseline, components, control_reports, reports
from services.lifecycle import check_version

CENT = Decimal("0.01")

# CT-4: the four analyses with a headline today, in panel order. (code, unit, comparison, flag, escalate, action)
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
    ("data_migration_map", "COUNT", "GT", Decimal(0), Decimal(5),
     "Data ownership decision before design freeze"),
)
ORDER = {code: i for i, (code, *_) in enumerate(HOUSE_RULES)}
UNIT = {code: unit for code, unit, *_ in HOUSE_RULES}
# Shown under the panel: the analyses still to come and what brings each (spec §1).
COMING = (("org_impact_heatmap", "CONTROL_B"), ("stakeholder_engagement", "CONTROL_B"),
          ("benefit_gap", "BENEFITS"), ("risk_register", "RISKS"))
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
    reason = (change_rationale or "").strip()
    if not reason:
        raise HTTPException(422, "Changing a control threshold is a governance decision and needs a reason")
    values = {f: values[f] for f in EDITABLE}
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
                 detail={"analysis_code": analysis_code,
                         "from": {f: _plain(old) for f, (old, _) in diff.items() if f not in TEXT_FIELDS},
                         "to": {f: _plain(new) for f, (_, new) in diff.items() if f not in TEXT_FIELDS},
                         "text_changed": [f for f in TEXT_FIELDS if f in diff],
                         "change_rationale": reason})
    db.commit()
    db.refresh(r)
    return list_rules_one(db, r)


def list_rules_one(db: Session, r: ControlRule) -> dict:
    roles, users = _names(db, [r])
    return _rule_out(r, roles, users)


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
    if code == "data_migration_map":
        return _from_report(control_reports.data_migration_map(db, project_id))
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
    an owner does not make it "switched off")."""
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
        rows = []
        for r in rules:
            m = headline(db, project_id, r.analysis_code, on)
            off = None if r.is_enabled else "SWITCHED_OFF" if r.control_rule_id in set_by_hand else "NOT_YET_AGREED"
            rows.append({**_rule_out(r, roles, users), **m, "verdict": verdict(r, m), "off_state": off})
        db.rollback()
    have = {r["analysis_code"] for r in rows}
    # round 2 N4: a measurable rule the project lacks is listed too, so a missing rule always shows somewhere.
    missing = [{"analysis_code": c, "brought_by": "SEED"} for c in ORDER if c not in have]
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "rows": rows,
            "coming": missing + [{"analysis_code": c, "brought_by": by} for c, by in COMING if c not in have]}
