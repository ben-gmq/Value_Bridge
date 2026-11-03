"""Benefits (§4.9, D-14; docs/slice_benefits_spec.md, BN-1…BN-6). The one owner of benefit and benefit-link writes,
and of the two reports that read them (the value ranking and the benefit gap).

A benefit is what the engagement is *for*: a measure moving from a baseline to a target, with an accountable org role
(criterion 59). Solutions deliver shares of it (benefit_solution.contribution_pct); a benefit's live shares total at
most 100 % (BN-2), checked here under a FOR UPDATE lock on the benefit, because a CHECK sees one row.

Value of one link = |target − baseline| × contribution % / 100, in the benefit's unit (A-40 as amended by BN-1).
Units are free text grouped by lower(btrim()) (BN-6); a ratio never mixes two units (criterion 128).

**Counting** (spec §4): a live benefit whose status behaviour is LIVE, through a live link, to a live solution whose
status is not REJECTED. Branches read the behaviour, never a status code (law 5); FORECAST and REJECTED are the codes
looked up by value (pinned). A solution **carries work** with any live FR, rated or not (R1-H1).

Audit: BENEFIT_CREATED / BENEFIT_UPDATED / BENEFIT_SOLUTION_LINKED / BENEFIT_SOLUTION_UNLINKED carry numbers, codes
and figures — never a name, description or unit text (R7). Retire / restore are lifecycle's RECORD_DELETED /
RECORD_RESTORED."""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Benefit, BenefitSolution, CodeMaster, FunctionRequirement, OrgRole, Solution
from models.shared import BENEFIT_STATUS_BEHAVIOURS
from services import audit, components, effort, lifecycle, numbering
from services.code_master import resolve, validate_required_code
from services.function_requirement import TECHNOLOGY

LIVE, ABANDONED = BENEFIT_STATUS_BEHAVIOURS
FORECAST = "FORECAST"
REJECTED = "REJECTED"                         # SOLUTION_STATUS, pinned; read as effort.summary reads it
CENT, HUNDRED = Decimal("0.01"), Decimal(100)
FIELDS = ("benefit_name", "description", "benefit_type_code", "measure_name", "measure_unit", "baseline_value",
          "target_value", "realisation_date", "accountable_org_role_id", "status_code")


def _q(v: Decimal) -> Decimal:
    return v.quantize(CENT, ROUND_HALF_UP)


def _s(v: Decimal | None) -> str | None:
    return None if v is None else str(_q(v))


def unit_key(unit: str | None) -> str:
    return (unit or "").strip().lower()


def link_value(benefit: Benefit, pct: Decimal) -> Decimal:
    """BN-1: a reduction is value too — 10 → 6 at 100 % is 4."""
    return abs(benefit.target_value - benefit.baseline_value) * pct / HUNDRED


# ---- checks ----------------------------------------------------------------------------------------------------------
def _text(value, field: str, required: bool = False) -> str | None:
    out = (value or "").strip() or None
    if required and out is None:
        raise HTTPException(422, f"{field} is required")
    return out


def _accountable(db: Session, project_id: int, role_id: int | None) -> int:
    """A live org role of this project, read FOR SHARE so its retire and this save are serialised (SR-5)."""
    if role_id is None:
        raise HTTPException(422, "Choose the benefit's accountable org role")
    row = db.get(OrgRole, role_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(422, "Choose a live org role of this project")
    lifecycle.lock_for_share(db, row)
    if not row.is_active:
        raise HTTPException(422, "Choose a live org role of this project")
    return role_id


def _changes_something(b: Benefit) -> None:
    if b.target_value == b.baseline_value:              # BN-1; ck_benefit_changes_something backs it
        raise HTTPException(422, "The target must differ from the baseline")


def _pinned_status(db: Session, project_id: int, code: str, behaviour: str) -> CodeMaster:
    row = next((c for c in resolve(db, project_id, "BENEFIT_STATUS") if c.code == code), None)
    if row is None or row.behaviour_code != behaviour:
        raise HTTPException(500, "Something went wrong.")        # pinned and behaviour-fixed: never reached
    return row


def _snapshot(b: Benefit) -> dict:
    """What the audit keeps: codes and figures, no text (R7)."""
    return {"type": b.benefit_type_code, "status": b.status_code, "baseline_value": _s(b.baseline_value),
            "target_value": _s(b.target_value), "accountable_org_role_id": b.accountable_org_role_id,
            "realisation_date": b.realisation_date.isoformat() if b.realisation_date else None}


def _finish(db: Session, b: Benefit) -> Benefit:
    db.commit()
    db.refresh(b)
    return b


# ---- reads -----------------------------------------------------------------------------------------------------------
def live_links(db: Session, *, benefit_id: int | None = None, solution_id: int | None = None,
               project_id: int | None = None) -> list[BenefitSolution]:
    q = select(BenefitSolution).where(BenefitSolution.is_active)
    if benefit_id is not None:
        q = q.where(BenefitSolution.benefit_id == benefit_id)
    if solution_id is not None:
        q = q.where(BenefitSolution.solution_id == solution_id)
    if project_id is not None:
        q = q.where(BenefitSolution.project_id == project_id)
    return list(db.scalars(q).unique())


def link_out(link: BenefitSolution) -> dict:
    b, s = link.benefit_row, link.solution_row
    return {"benefit_solution_id": link.benefit_solution_id, "benefit_id": b.benefit_id,
            "benefit_number": b.benefit_number, "benefit_name": b.benefit_name, "measure_unit": b.measure_unit,
            "solution_id": s.solution_id, "solution_number": s.solution_number, "solution_name": s.solution_name,
            "solution_status_code": s.status_code, "solution_rejected": s.status_code == REJECTED,
            "contribution_pct": _s(link.contribution_pct), "value": _s(link_value(b, link.contribution_pct)),
            "row_version": link.row_version}


def decorate(db: Session, b: Benefit) -> Benefit:
    """The register's extra columns: live link total and the linked solution numbers."""
    links = sorted(live_links(db, benefit_id=b.benefit_id), key=lambda ln: ln.solution_row.solution_number)
    b.link_total_pct = _s(sum((ln.contribution_pct for ln in links), Decimal(0)))
    b.linked_solutions = [ln.solution_row.solution_number for ln in links]
    b.links = [link_out(ln) for ln in links]
    b.accountable_org_role_code = db.scalar(select(OrgRole.org_role_code).where(
        OrgRole.org_role_id == b.accountable_org_role_id))
    return b


def list_benefits(db: Session, project_id: int, include_retired: bool = False, *, status: str | None = None,
                  unit: str | None = None) -> list[Benefit]:
    q = select(Benefit).where(Benefit.project_id == project_id)
    if not include_retired:
        q = q.where(Benefit.is_active)
    if status:                                   # by code, so a project's wording of it matches too (G-3)
        q = q.where(Benefit.status_code_id.in_(select(CodeMaster.code_id).where(
            CodeMaster.category == "BENEFIT_STATUS", CodeMaster.code == status)))
    if unit:
        q = q.where(func.lower(func.btrim(Benefit.measure_unit)) == unit_key(unit))
    return [decorate(db, b) for b in db.scalars(q.order_by(Benefit.benefit_number)).unique()]


# ---- benefit writes --------------------------------------------------------------------------------------------------
def create_benefit(db: Session, actor_id: int, project_id: int, fields: dict) -> Benefit:
    status = _pinned_status(db, project_id, FORECAST, LIVE)
    typ = validate_required_code(db, project_id, "BENEFIT_TYPE", fields.get("benefit_type_code"), "benefit_type_code")
    b = Benefit(project_id=project_id, benefit_name=_text(fields.get("benefit_name"), "benefit_name", True),
                description=_text(fields.get("description"), "description"),
                benefit_type_code_id=typ.code_id,
                measure_name=_text(fields.get("measure_name"), "measure_name", True),
                measure_unit=_text(fields.get("measure_unit"), "measure_unit", True),
                baseline_value=fields["baseline_value"], target_value=fields["target_value"],
                realisation_date=fields.get("realisation_date"),
                status_code_id=status.code_id, status_behaviour=LIVE, created_by=actor_id)
    _changes_something(b)
    b.accountable_org_role_id = _accountable(db, project_id, fields.get("accountable_org_role_id"))
    b.benefit_number = numbering.next_number(db, project_id, "BEN")      # at save, after every check (§9.8)
    db.add(b)
    db.flush()
    db.refresh(b)
    audit.record(db, "BENEFIT_CREATED", actor_id=actor_id, project_id=project_id, target_table="benefit",
                 target_id=b.benefit_id, detail={"benefit_number": b.benefit_number, **_snapshot(b)})
    return _finish(db, b)


def update_benefit(db: Session, actor_id: int, b: Benefit, row_version: int, fields: dict) -> Benefit:
    lifecycle.lock(db, b)
    lifecycle.check_live(b, row_version)
    before = _snapshot(b)
    for field in ("benefit_name", "measure_name", "measure_unit"):
        if field in fields:
            setattr(b, field, _text(fields[field], field, required=True))
    if "description" in fields:
        b.description = _text(fields["description"], "description")
    if "benefit_type_code" in fields:
        b.benefit_type_code_id = validate_required_code(db, b.project_id, "BENEFIT_TYPE", fields["benefit_type_code"],
                                                        "benefit_type_code").code_id
    if "status_code" in fields:
        row = validate_required_code(db, b.project_id, "BENEFIT_STATUS", fields["status_code"], "status_code")
        b.status_code_id, b.status_behaviour = row.code_id, row.behaviour_code
    for field in ("baseline_value", "target_value"):
        if field in fields:
            if fields[field] is None:
                raise HTTPException(422, f"{field} cannot be empty")
            setattr(b, field, fields[field])
    _changes_something(b)
    if "realisation_date" in fields:
        b.realisation_date = fields["realisation_date"]
    if "accountable_org_role_id" in fields:
        b.accountable_org_role_id = _accountable(db, b.project_id, fields["accountable_org_role_id"])
    b.updated_by = actor_id
    db.flush()
    db.refresh(b)
    audit.record(db, "BENEFIT_UPDATED", actor_id=actor_id, project_id=b.project_id, target_table="benefit",
                 target_id=b.benefit_id, detail={"benefit_number": b.benefit_number, "before": before,
                                                 "after": _snapshot(b), "fields": sorted(fields)})
    return _finish(db, b)


def retire_benefit(db: Session, actor_id: int, b: Benefit, row_version: int) -> None:
    """lifecycle.retire locks the benefit FOR UPDATE, then refuses while a live link names it (409, both ends)."""
    lifecycle.retire(db, actor_id, b, row_version)


def restore_benefit(db: Session, actor_id: int, b: Benefit) -> Benefit:
    """A retired accountable role refuses through lifecycle.restore; the number comes back with it."""
    lifecycle.lock(db, b)
    lifecycle.restore(db, actor_id, b)
    db.refresh(b)
    return b


# ---- link writes -----------------------------------------------------------------------------------------------------
def _solution_of(db: Session, b: Benefit, solution_id: int) -> Solution:
    """DR1-S1 / R1-M6: missing or of another project is the same 404; a retired one of this project is 409."""
    s = db.get(Solution, solution_id)
    if s is None or s.project_id != b.project_id:
        raise HTTPException(404, "Not found")
    lifecycle.lock_for_share(db, s)                       # SR-5: a solution retire waits for this link
    if not s.is_active:
        raise HTTPException(409, f"{s.solution_number} is retired. Restore it first.")
    return s


def link_solution(db: Session, actor_id: int, b: Benefit, solution_id: int, pct: Decimal) -> BenefitSolution:
    """Create, restore or re-weight the one (benefit, solution) row. Lock order (spec §5.2): the benefit FOR UPDATE,
    the solution FOR SHARE, then the total of the *other* live links. The same % twice writes nothing."""
    components.require_on(db, b.project_id, "SOLUTION")
    lifecycle.lock(db, b)
    if not b.is_active:
        raise HTTPException(409, f"{b.benefit_number} is retired. Restore it first.")
    s = _solution_of(db, b, solution_id)
    pct = _q(Decimal(pct))
    if not (Decimal(0) < pct <= HUNDRED):
        raise HTTPException(422, "A contribution is more than 0 % and at most 100 %")
    others = db.scalar(select(func.coalesce(func.sum(BenefitSolution.contribution_pct), 0)).where(
        BenefitSolution.benefit_id == b.benefit_id, BenefitSolution.is_active,
        BenefitSolution.solution_id != s.solution_id))
    if others + pct > HUNDRED:                            # BN-2
        raise HTTPException(409, f"{b.benefit_number}'s other solutions already carry {_s(others)} %: "
                                 f"{_s(pct)} % more would total {_s(others + pct)} % (at most 100 %)")
    row = db.scalars(select(BenefitSolution).where(BenefitSolution.benefit_id == b.benefit_id,
                                                   BenefitSolution.solution_id == s.solution_id)).one_or_none()
    detail = {"benefit_number": b.benefit_number, "solution_number": s.solution_number, "contribution_pct": _s(pct)}
    if row is not None and row.is_active and row.contribution_pct == pct:
        return row                                        # idempotent PUT
    if row is None:
        row = BenefitSolution(project_id=b.project_id, benefit_id=b.benefit_id, solution_id=s.solution_id,
                              contribution_pct=pct, created_by=actor_id)
        db.add(row)
    else:
        detail["before_pct"] = _s(row.contribution_pct) if row.is_active else None
        detail["restored"] = not row.is_active
        row.is_active, row.deleted_at, row.deleted_by = True, None, None        # S1-7: the same row comes back
        row.contribution_pct, row.updated_by = pct, actor_id
    db.flush()
    audit.record(db, "BENEFIT_SOLUTION_LINKED", actor_id=actor_id, project_id=b.project_id,
                 target_table="benefit_solution", target_id=row.benefit_solution_id, detail=detail)
    db.commit()
    db.refresh(row)
    return row


def unlink_solution(db: Session, actor_id: int, b: Benefit, solution_id: int) -> None:
    lifecycle.lock(db, b)
    row = db.scalars(select(BenefitSolution).where(BenefitSolution.benefit_id == b.benefit_id,
                                                   BenefitSolution.solution_id == solution_id,
                                                   BenefitSolution.is_active)).one_or_none()
    if row is None:
        raise HTTPException(404, "Not found")
    lifecycle.soft_delete(row, actor_id)
    row.updated_by = actor_id
    audit.record(db, "BENEFIT_SOLUTION_UNLINKED", actor_id=actor_id, project_id=b.project_id,
                 target_table="benefit_solution", target_id=row.benefit_solution_id,
                 detail={"benefit_number": b.benefit_number, "solution_number": row.solution_row.solution_number,
                         "contribution_pct": _s(row.contribution_pct)})
    db.commit()


# ---- the two reports (spec §8) ---------------------------------------------------------------------------------------
class _Facts:
    """One read of a project's solutions, FRs, benefits and links; both reports and the panel use it."""

    def __init__(self, db: Session, project_id: int):
        self.on = components.enabled(db, project_id)
        self.sols = {s.solution_id: s for s in db.scalars(select(Solution).where(
            Solution.project_id == project_id, Solution.is_active)).unique()}
        self.rejected = {sid for sid, s in self.sols.items() if s.status_code == REJECTED}
        self.frs: dict[int | None, list[FunctionRequirement]] = defaultdict(list)
        for f in db.scalars(select(FunctionRequirement).where(FunctionRequirement.project_id == project_id,
                                                              FunctionRequirement.is_active)).unique():
            self.frs[f.solution_id].append(f)
        self.benefits = {b.benefit_id: b for b in db.scalars(select(Benefit).where(
            Benefit.project_id == project_id, Benefit.is_active)).unique()}
        self.links = [ln for ln in live_links(db, project_id=project_id) if ln.benefit_id in self.benefits]
        self.counting = [ln for ln in self.links
                         if self.benefits[ln.benefit_id].status_behaviour == LIVE
                         and ln.solution_id in self.sols and ln.solution_id not in self.rejected]
        self.counting_ids = {ln.benefit_solution_id for ln in self.counting}
        self.effort_on = {"EFFORT", "FUNCTION_REQUIREMENT"} <= self.on

    def counting_solutions(self) -> dict[int, Solution]:
        return {sid: s for sid, s in self.sols.items() if sid not in self.rejected}

    def rated(self, sid) -> Decimal:
        return sum((f.effort_days for f in self.frs.get(sid, ()) if f.effort_days is not None), Decimal(0))


def _sol(s: Solution) -> dict:
    return {"solution_id": s.solution_id, "solution_number": s.solution_number, "solution_name": s.solution_name}


def value_ranking(db: Session, project_id: int) -> dict:
    """§8.1, criteria 60 and 128: one ranking per unit; the bottom quartile named; a displacement candidate only when
    it delivers nothing elsewhere (R1-M5); partly rated never ranked (R1-H1)."""
    f = _Facts(db, project_id)
    if "BENEFIT" not in f.on:
        return {"measured": False, "reason": "BENEFIT_OFF", "units": [], "untagged_effort_days": None,
                "reconciliation": None}
    value: dict[str, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))     # unit key → sid → value
    spelling: dict[str, Benefit] = {}
    for ln in f.counting:
        b = f.benefits[ln.benefit_id]
        k = unit_key(b.measure_unit)
        value[k][ln.solution_id] += link_value(b, ln.contribution_pct)
    for b in f.benefits.values():                                             # A-B9: the latest spelling shown
        k = unit_key(b.measure_unit)
        cur = spelling.get(k)
        if b.status_behaviour == LIVE and (cur is None or (b.updated_at, b.benefit_id) > (cur.updated_at, cur.benefit_id)):
            spelling[k] = b
    units = []
    for k in sorted(value, key=lambda k: spelling[k].measure_unit.strip().lower()):
        entry = {"unit_key": k, "unit": spelling[k].measure_unit.strip(), "ranked": [], "partly_rated": [],
                 "no_work": [], "values": [], "benefits": _benefit_lines(f, k)}
        ranked = []
        for sid, v in value[k].items():
            s, frs = f.sols[sid], f.frs.get(sid, [])
            row = {**_sol(s), "value": _s(v)}
            if not f.effort_on:
                entry["values"].append(row)
                continue
            rated = [x for x in frs if x.effort_days is not None]
            days = f.rated(sid)
            if not frs or (len(rated) == len(frs) and days == 0):
                entry["no_work"].append(row)
            elif len(rated) < len(frs):
                entry["partly_rated"].append({**row, "fr_count": len(frs), "rated_count": len(rated),
                                              "rated_effort_days": _s(days)})
            else:
                ranked.append((v / days, s.solution_number, sid, v, days))
        ranked.sort(key=lambda r: (-r[0], r[1]))
        n = len(ranked)
        bottom = ceil(n / 4) if n >= 4 else 0
        for i, (ratio, _, sid, v, days) in enumerate(ranked):
            elsewhere = [{"unit": spelling[o].measure_unit.strip(), "value": _s(value[o][sid])}
                         for o in sorted(value) if o != k and value[o].get(sid)]
            low = i >= n - bottom
            entry["ranked"].append({"rank": i + 1, **_sol(f.sols[sid]), "value": _s(v), "effort_days": _s(days),
                                    "ratio": _s(ratio), "bottom_quartile": low,
                                    "displacement_candidate": low and not elsewhere,
                                    "also_delivers": elsewhere if low else []})
        for lst in ("partly_rated", "no_work", "values"):
            entry[lst].sort(key=lambda r: r["solution_number"])
        units.append(entry)
    return {"measured": f.effort_on, "reason": None if f.effort_on else "EFFORT_OFF", "units": units,
            "untagged_effort_days": _s(f.rated(None)) if f.effort_on else None,
            "reconciliation": _reconciliation(db, project_id, f) if f.effort_on else None}


def _benefit_lines(f: _Facts, k: str) -> list[dict]:
    """R1-M4: "x % of BEN-0003 not assigned", "y % on rejected solutions" — counting benefits of this unit."""
    out = []
    for b in sorted(f.benefits.values(), key=lambda b: b.benefit_number):
        if b.status_behaviour != LIVE or unit_key(b.measure_unit) != k:
            continue
        mine = [ln for ln in f.links if ln.benefit_id == b.benefit_id]
        counted = sum((ln.contribution_pct for ln in mine if ln.benefit_solution_id in f.counting_ids), Decimal(0))
        rejected = sum((ln.contribution_pct for ln in mine if ln.solution_id in f.rejected), Decimal(0))
        if counted < HUNDRED or rejected:
            out.append({"benefit_id": b.benefit_id, "benefit_number": b.benefit_number,
                        "unassigned_pct": _s(HUNDRED - counted), "on_rejected_pct": _s(rejected)})
    return out


def _reconciliation(db: Session, project_id: int, f: _Facts) -> dict:
    """R1-L1, R2-M1: per solution, once — never from the per-unit rankings, where a two-unit solution appears twice."""
    with_value = {ln.solution_id for ln in f.counting}
    buckets = {"with_value": Decimal(0), "no_benefit": Decimal(0), "rejected": Decimal(0), "untagged": f.rated(None)}
    for sid in f.sols:
        key = "rejected" if sid in f.rejected else "with_value" if sid in with_value else "no_benefit"
        buckets[key] += f.rated(sid)
    es = effort.summary(db, project_id)
    theirs = es["total_days"] + es["rejected"]["days"]
    ours = sum(buckets.values(), Decimal(0))
    return {**{k: _s(v) for k, v in buckets.items()}, "total_days": _s(ours), "effort_summary_days": _s(theirs),
            "difference": _s(ours - theirs)}


def benefit_gap_report(db: Session, project_id: int) -> dict:
    """§8.2, §8.3: counting solutions that carry work and deliver no counting benefit; fragile benefits."""
    f = _Facts(db, project_id)
    reason = next((f"{c}_OFF" for c in ("BENEFIT", "FUNCTION_REQUIREMENT", "EFFORT") if c not in f.on), None)
    working = {sid: s for sid, s in f.counting_solutions().items() if f.frs.get(sid)}
    delivering = {ln.solution_id for ln in f.counting}
    gap = [{**_sol(s), "category_code": s.category_code, "fr_count": len(f.frs[sid]),
            "rated_effort_days": _s(f.rated(sid))}
           for sid, s in sorted(working.items(), key=lambda kv: kv[1].solution_number) if sid not in delivering]
    by_benefit: dict[int, list[Solution]] = defaultdict(list)
    for ln in f.counting:
        by_benefit[ln.benefit_id].append(f.sols[ln.solution_id])
    fragile = [{"benefit_id": bid, "benefit_number": f.benefits[bid].benefit_number,
                "benefit_name": f.benefits[bid].benefit_name,
                "solutions": sorted(s.solution_number for s in sols)}
               for bid, sols in sorted(by_benefit.items(), key=lambda kv: f.benefits[kv[0]].benefit_number)
               if all(s.category_code == TECHNOLOGY for s in sols)]
    if reason is None and not working:
        reason = "NO_SOLUTION_WITH_WORK"
    measured = None if reason else _s(Decimal(len(gap)) * HUNDRED / len(working))
    return {"headline": {"measured": measured, "reason": reason, "gap_count": len(gap),
                         "carrying_count": len(working)},
            "gap": [] if reason in ("BENEFIT_OFF", "FUNCTION_REQUIREMENT_OFF") else gap, "fragile": fragile}
