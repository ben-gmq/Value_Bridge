"""Change requests (§4.11, §7.13 change control, D-16; docs/slice_change_requests_spec.md; CR-1…CR-3, Ben 2026-11-03).
The one owner of change_request and cr_impact writes.

A change is raised against one agreed baseline (FROZEN, APPROVED, or the SUPERSEDED one carrying the client approval,
SC-2) and drafted in the working set (CR-1): the team marks each BR / FR it touches ADD, MODIFY or REMOVE (the seeds).
"Trace and price" walks the live links out from the seeds and records every object reached (computed, never typed,
criterion 64). The price is working set minus agreed baseline, over the seed FRs only (Q3): ADD + live days, REMOVE −
agreed days, MODIFY live − agreed. Exposure (agreed days of traced, unseeded FRs) sits beside it, never added. Benefit
value is per unit, never one total (Q9, CR-2).

Deciding writes one DECISION and the CR's status in one transaction (criterion 66). An approved increase is covered by
one approved decrease on the same baseline (each used once) and/or a budget record for what the cut leaves (CR-3).
A rejected or undecided edit left in the working set is listed and warned at the next freeze (`unagreed_edits`); the
team undoes it, the app does not (CR-1).

Statuses branch on their behaviour (law 5): OPEN (DRAFT / ANALYSED), PRICED, DEFERRED, APPROVED, REJECTED. The status
and impact-type codes written by value are pinned and company-only. Audit events carry numbers, codes and day totals —
never a title, rationale or budget text (R7)."""
from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (AppUser, Application, ApplicationSolution, Baseline, Benefit, BenefitSolution, BrDataEntity,
                    BrFunctionRequirement, BrSolution, BusinessRequirement, ChangeRequest, CodeMaster, ControlRule,
                    CrImpact, DataEntity, Decision, FunctionRequirement, Phase, Solution, SolutionDependency,
                    SolutionPhase)
from models.change_request import IMPACT_COLUMNS
from services import audit, baseline as baseline_service, benefit as benefit_service, components, freeze_set
from services import decision as decision_service, lifecycle, numbering
from services.code_master import resolve, validate_required_code

OPEN, PRICED, DEFERRED, APPROVED, REJECTED = "OPEN", "PRICED", "DEFERRED", "APPROVED", "REJECTED"
UNDECIDED = (OPEN, PRICED, DEFERRED)            # may be seeded, traced, priced and decided
OUTCOMES = (APPROVED, REJECTED, DEFERRED)       # CR_STATUS codes, pinned; each its own behaviour
ADD, MODIFY, REMOVE = "ADD", "MODIFY", "REMOVE"  # CR_IMPACT_TYPE, pinned (CR-1)
DRAFT_CODE, ANALYSED_CODE, PRICED_CODE = "DRAFT", "ANALYSED", "PRICED"
AGREEABLE = ("FROZEN", "APPROVED")              # BASELINE_STATUS, a system category
SUPERSEDED = "SUPERSEDED"
SCOPE = "SCOPE"                                 # PM_DIMENSION
PRICED_DIFF = "priced_diff"                     # DC-3: the analysis behind a CR decision, when the project has it
BENEFIT_SPEC = 7                                # hash spec at which benefits joined the freeze set
CENT, ZERO, HUNDRED = Decimal("0.01"), Decimal(0), Decimal(100)
FR_TABLE, BR_TABLE = "function_requirement", "business_requirement"

# column → (model, number column, name column, kind shown, component that must be on to reach it)
KINDS = {
    "impacted_br_id": (BusinessRequirement, "br_number", "br_statement", "BR", None),
    "impacted_fr_id": (FunctionRequirement, "fr_number", "fr_name", "FR", None),
    "impacted_solution_id": (Solution, "solution_number", "solution_name", "SOLUTION", "SOLUTION"),
    "impacted_application_id": (Application, "application_code", "application_name", "APPLICATION", "APPLICATION"),
    "impacted_data_entity_id": (DataEntity, "de_number", "de_name", "DATA_ENTITY", None),
    "impacted_phase_id": (Phase, "phase_code", "phase_name", "WAVE", "PHASING"),
    "impacted_benefit_id": (Benefit, "benefit_number", "benefit_name", "BENEFIT", "BENEFIT"),
}
KIND_ORDER = {v[3]: n for n, v in enumerate(KINDS.values())}
TRACE_PARTS = ("SOLUTION", "APPLICATION", "PHASING", "BENEFIT")


def _q(v: Decimal) -> Decimal:
    return Decimal(v).quantize(CENT, ROUND_HALF_UP)


def _s(v: Decimal | None) -> str | None:
    return None if v is None else str(_q(v))


def _text(value, field: str) -> str:
    out = (value or "").strip()
    if not out:
        raise HTTPException(422, f"{field} is required")
    return out


def _key(row: CrImpact) -> tuple[str, int]:
    col = next(c for c in IMPACT_COLUMNS if getattr(row, c) is not None)
    return col, getattr(row, col)


def _state(cr: ChangeRequest) -> str:
    return cr.status_behaviour


def _require_undecided(cr: ChangeRequest) -> None:
    if _state(cr) not in UNDECIDED:
        raise HTTPException(409, f"{cr.cr_number} is {cr.status_code_row.label.lower()}: a decided change request "
                                 f"is final")


def _status(db: Session, project_id: int, code: str) -> CodeMaster:
    row = next((c for c in resolve(db, project_id, "CR_STATUS") if c.code == code), None)
    if row is None:
        raise HTTPException(500, "Something went wrong.")          # pinned and company-only: never reached
    return row


def _set_status(db: Session, cr: ChangeRequest, code: str) -> None:
    row = _status(db, cr.project_id, code)
    cr.status_code_id, cr.status_behaviour = row.code_id, row.behaviour_code


def _clear_price(cr: ChangeRequest) -> None:
    cr.effort_delta_days = cr.effort_exposed_days = cr.unrated_fr_count = cr.priced_at = None


def _baseline_label(db: Session, baseline_id: int) -> str:
    return db.scalar(select(Baseline.version_label).where(Baseline.baseline_id == baseline_id))


def _shadow_rows(db: Session, target: Baseline, table: str, ids) -> dict[int, dict]:
    """The target's frozen rows of one table, by source id (empty when the table was not frozen at its spec)."""
    ids = list(ids)
    if not ids:
        return {}
    t = freeze_set.shadow(table)
    return {r["source_id"]: dict(r) for r in db.execute(
        select(t).where(t.c.baseline_id == target.baseline_id, t.c.source_id.in_(ids))).mappings()}


# ---- raise -----------------------------------------------------------------------------------------------------------
def _target(db: Session, project_id: int, baseline_id: int) -> Baseline:
    """Criteria 63, 190: read scoped to the project FOR SHARE (a freeze's supersede takes FOR UPDATE, so they
    serialise); FROZEN, APPROVED or the agreed SUPERSEDED one; and it must carry prices."""
    b = db.scalar(select(Baseline).where(Baseline.baseline_id == baseline_id, Baseline.project_id == project_id)
                  .with_for_update(read=True, of=Baseline))
    if b is None:
        raise HTTPException(404, "That baseline was not found in this project")
    agreed = baseline_service.agreed_id(baseline_service.list_baselines(db, project_id))
    if not (b.status_code in AGREEABLE or (b.status_code == SUPERSEDED and b.baseline_id == agreed)):
        raise HTTPException(422, f"{b.version_label} is superseded and was never agreed: raise the change against the "
                                 f"agreed baseline or the latest frozen one")
    if "EFFORT" not in baseline_service.components_of(db, b.baseline_id):
        raise HTTPException(422, f"{b.version_label} was frozen without effort: this baseline carries no prices")
    return b


def raise_change_request(db: Session, actor_id: int, project_id: int, fields: dict) -> ChangeRequest:
    origin = validate_required_code(db, project_id, "CR_ORIGIN", fields.get("origin_code"), "origin_code")
    target = _target(db, project_id, fields.get("against_baseline_id"))
    status = _status(db, project_id, DRAFT_CODE)
    cr = ChangeRequest(project_id=project_id, title=_text(fields.get("title"), "title"),
                       rationale=_text(fields.get("rationale"), "rationale"), against_baseline_id=target.baseline_id,
                       origin_code_id=origin.code_id, status_code_id=status.code_id,
                       status_behaviour=status.behaviour_code, raised_by_user_id=actor_id, created_by=actor_id)
    cr.cr_number = numbering.next_number(db, project_id, "CR")          # at save, after every check (§9.8)
    db.add(cr)
    db.flush()
    audit.record(db, "CR_RAISED", actor_id=actor_id, project_id=project_id, target_table="change_request",
                 target_id=cr.change_request_id,
                 detail={"cr_number": cr.cr_number, "origin": origin.code, "against": target.version_label})
    db.commit()
    db.refresh(cr)
    return cr


def update_change_request(db: Session, actor_id: int, cr: ChangeRequest, row_version: int, fields: dict) -> ChangeRequest:
    lifecycle.lock(db, cr)
    lifecycle.check_live(cr, row_version)
    _require_undecided(cr)
    for field in ("title", "rationale"):
        if field in fields:
            setattr(cr, field, _text(fields[field], field))
    if "origin_code" in fields:
        cr.origin_code_id = validate_required_code(db, cr.project_id, "CR_ORIGIN", fields["origin_code"],
                                                   "origin_code").code_id
    cr.updated_by = actor_id
    db.flush()
    audit.record(db, "CR_UPDATED", actor_id=actor_id, project_id=cr.project_id, target_table="change_request",
                 target_id=cr.change_request_id, detail={"cr_number": cr.cr_number, "fields": sorted(fields)})
    db.commit()
    db.refresh(cr)
    return cr


# ---- seeds -----------------------------------------------------------------------------------------------------------
def _seed_object(db: Session, project_id: int, seed: dict):
    """A live BR or FR of this project; another project's (or a missing) id is the same 404. An FR is locked FOR
    UPDATE, so two change requests seeding it at once serialise before the overlap check (R2 auditor L)."""
    br_id, fr_id = seed.get("br_id"), seed.get("fr_id")
    if (br_id is None) == (fr_id is None):
        raise HTTPException(422, "Each seed names one business requirement or one function requirement")
    model, oid, col = ((FunctionRequirement, fr_id, "impacted_fr_id") if fr_id is not None
                       else (BusinessRequirement, br_id, "impacted_br_id"))
    obj = db.get(model, oid)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "Not found")
    lifecycle.lock(db, obj, read=model is BusinessRequirement)
    if not obj.is_active:
        raise HTTPException(422, f"{_number(obj, col)} is retired: a seed is live when it is set")
    return col, obj


def _number(obj, col: str) -> str:
    return getattr(obj, KINDS[col][1])


def set_seeds(db: Session, actor_id: int, cr: ChangeRequest, row_version: int, seeds: list[dict]) -> ChangeRequest:
    lifecycle.lock(db, cr)
    lifecycle.check_live(cr, row_version)
    _require_undecided(cr)
    target = db.get(Baseline, cr.against_baseline_id)
    chosen: dict[tuple[str, int], tuple[object, CodeMaster]] = {}
    for seed in seeds:
        typ = validate_required_code(db, cr.project_id, "CR_IMPACT_TYPE", seed.get("impact_type_code"),
                                     "impact_type_code")
        col, obj = _seed_object(db, cr.project_id, seed)
        key = (col, lifecycle.pk(obj))
        if key in chosen:
            raise HTTPException(422, f"{_number(obj, col)} is listed twice")
        chosen[key] = (obj, typ)
    for table, col in ((FR_TABLE, "impacted_fr_id"), (BR_TABLE, "impacted_br_id")):
        frozen = _shadow_rows(db, target, table, [i for c, i in chosen if c == col])
        for (c, i), (obj, typ) in chosen.items():
            if c != col:
                continue
            if typ.code == ADD and i in frozen:
                raise HTTPException(422, f"{_number(obj, c)} is already in {target.version_label}: mark it modify "
                                         f"or remove")
            if typ.code in (MODIFY, REMOVE) and i not in frozen:
                raise HTTPException(422, f"{_number(obj, c)} is not in {target.version_label}: mark it add")
    _refuse_overlap(db, cr, [i for c, i in chosen if c == "impacted_fr_id"])
    rows = {_key(r): r for r in db.scalars(select(CrImpact).where(CrImpact.change_request_id == cr.change_request_id))}
    for key, row in rows.items():                       # the trace and every dropped seed go; re-tracing restores
        if row.is_active and key not in chosen:
            lifecycle.soft_delete(row, actor_id)
            row.updated_by = actor_id
    for key, (obj, typ) in chosen.items():
        row = rows.get(key)
        if row is None:
            row = CrImpact(project_id=cr.project_id, change_request_id=cr.change_request_id, **{key[0]: key[1]},
                           is_seed=True, impact_type_code_id=typ.code_id, reached_via="SEED", created_by=actor_id)
            db.add(row)
        else:
            row.is_active, row.deleted_at, row.deleted_by = True, None, None
            row.is_seed, row.impact_type_code_id, row.reached_via = True, typ.code_id, "SEED"
            row.updated_by = actor_id
        row.effort_delta_days = row.agreed_effort_days = None
        row.value_unit = row.value_at_stake = row.value_change = None
    _clear_price(cr)
    _set_status(db, cr, DRAFT_CODE)                     # a deferred CR keeps its decision: the next one supersedes it
    cr.updated_by = actor_id
    db.flush()
    audit.record(db, "CR_SEEDS_SET", actor_id=actor_id, project_id=cr.project_id, target_table="change_request",
                 target_id=cr.change_request_id,
                 detail={"cr_number": cr.cr_number,
                         "seeds": sorted([_number(o, k[0]), t.code] for k, (o, t) in chosen.items())})
    db.commit()
    db.refresh(cr)
    return cr


def _refuse_overlap(db: Session, cr: ChangeRequest, fr_ids: list[int]) -> None:
    """CR-1 (R1 auditor M): one FR is a seed of one undecided change at a time, and never of a change approved
    against the same baseline — otherwise one live edit is priced twice."""
    if not fr_ids:
        return
    other = db.execute(
        select(ChangeRequest.cr_number, FunctionRequirement.fr_number)
        .select_from(CrImpact)
        .join(ChangeRequest, ChangeRequest.change_request_id == CrImpact.change_request_id)
        .join(FunctionRequirement, FunctionRequirement.fr_id == CrImpact.impacted_fr_id)
        .where(CrImpact.impacted_fr_id.in_(fr_ids), CrImpact.is_seed, CrImpact.is_active, ChangeRequest.is_active,
               ChangeRequest.change_request_id != cr.change_request_id,
               or_(ChangeRequest.status_behaviour.in_(UNDECIDED),
                   (ChangeRequest.status_behaviour == APPROVED)
                   & (ChangeRequest.against_baseline_id == cr.against_baseline_id)))
        .order_by(FunctionRequirement.fr_number)).first()
    if other is not None:
        raise HTTPException(409, f"{other.fr_number} is already a seed of {other.cr_number}: one change to it at a time")


# ---- trace -----------------------------------------------------------------------------------------------------------
def _trace(db: Session, project_id: int, seeds: list[CrImpact], on: frozenset) -> dict[tuple[str, int], str]:
    """Every live object reached from the seeds over live links, with the first route that reached it (A8). Seeds are
    not repeated as traced rows. A part whose component is off is not walked (its rows are not live work)."""
    reached: dict[tuple[str, int], str] = {}

    def reach(col: str, ids, route: str) -> None:
        for i in sorted(ids):
            reached.setdefault((col, i), route)

    brs = {r.impacted_br_id for r in seeds if r.impacted_br_id is not None}
    seed_frs = {r.impacted_fr_id for r in seeds if r.impacted_fr_id is not None}
    frs = set(seed_frs)
    if brs:
        found = set(db.scalars(select(BrFunctionRequirement.fr_id)
                               .join(FunctionRequirement, FunctionRequirement.fr_id == BrFunctionRequirement.fr_id)
                               .where(BrFunctionRequirement.br_id.in_(brs), BrFunctionRequirement.is_active,
                                      FunctionRequirement.is_active)))
        reach("impacted_fr_id", found, "BR_FR")
        frs |= found
    sols: set[int] = set()
    if "SOLUTION" in on:
        if brs:
            found = set(db.scalars(select(BrSolution.solution_id)
                                   .join(Solution, Solution.solution_id == BrSolution.solution_id)
                                   .where(BrSolution.br_id.in_(brs), BrSolution.is_active, Solution.is_active)))
            reach("impacted_solution_id", found, "BR_SOLUTION")
            sols |= found
        if frs:
            found = set(db.scalars(select(FunctionRequirement.solution_id)
                                   .join(Solution, Solution.solution_id == FunctionRequirement.solution_id)
                                   .where(FunctionRequirement.fr_id.in_(frs), FunctionRequirement.is_active,
                                          Solution.is_active)))
            reach("impacted_solution_id", found, "FR_SOLUTION")
            sols |= found
    if brs:
        reach("impacted_data_entity_id", db.scalars(
            select(BrDataEntity.data_entity_id).join(DataEntity, DataEntity.data_entity_id == BrDataEntity.data_entity_id)
            .where(BrDataEntity.br_id.in_(brs), BrDataEntity.is_active, DataEntity.is_active)), "BR_ENTITY")
    if sols and "APPLICATION" in on:
        reach("impacted_application_id", db.scalars(
            select(ApplicationSolution.application_id)
            .join(Application, Application.application_id == ApplicationSolution.application_id)
            .where(ApplicationSolution.solution_id.in_(sols), ApplicationSolution.is_active, Application.is_active)),
            "SOLUTION_APP")
    if sols and "PHASING" in on:
        reach("impacted_phase_id", db.scalars(
            select(SolutionPhase.phase_id).join(Phase, Phase.phase_id == SolutionPhase.phase_id)
            .where(SolutionPhase.solution_id.in_(sols), SolutionPhase.is_active, Phase.is_active)), "SOLUTION_WAVE")
    if sols and "BENEFIT" in on:
        reach("impacted_benefit_id", db.scalars(
            select(BenefitSolution.benefit_id).join(Benefit, Benefit.benefit_id == BenefitSolution.benefit_id)
            .where(BenefitSolution.solution_id.in_(sols), BenefitSolution.is_active, Benefit.is_active)),
            "SOLUTION_BENEFIT")
    seed_keys = {_key(r) for r in seeds}
    return {k: v for k, v in reached.items() if k not in seed_keys}


# ---- price -----------------------------------------------------------------------------------------------------------
class _Price:
    """The figures of one change over the live working set and its target, computed without writing (analyse
    stores them; decide and the CR page re-run them to see what moved)."""

    def __init__(self, db: Session, cr: ChangeRequest, target: Baseline):
        self.db, self.cr, self.target = db, cr, target
        self.on = components.enabled(db, cr.project_id)
        self.seeds = list(db.scalars(select(CrImpact).where(CrImpact.change_request_id == cr.change_request_id,
                                                            CrImpact.is_active, CrImpact.is_seed)))
        self.reached = _trace(db, cr.project_id, self.seeds, self.on) if self.seeds else {}
        fr_ids = {r.impacted_fr_id for r in self.seeds if r.impacted_fr_id} | {
            i for c, i in self.reached if c == "impacted_fr_id"}
        self.frs = {f.fr_id: f for f in db.scalars(select(FunctionRequirement)
                                                   .where(FunctionRequirement.fr_id.in_(fr_ids))).unique()}
        frozen = _shadow_rows(db, target, FR_TABLE, fr_ids)
        self.agreed = {i: r["effort_days"] for i, r in frozen.items()}
        self.seed_delta: dict[int, Decimal | None] = {}
        self.unrated: list[str] = []
        self.retired: list[str] = []
        for r in self.seeds:
            if r.impacted_br_id is not None:
                br = db.get(BusinessRequirement, r.impacted_br_id)
                if not br.is_active and r.impact_type_code != REMOVE:
                    self.retired.append(br.br_number)
                continue
            f, agreed = self.frs[r.impacted_fr_id], self.agreed.get(r.impacted_fr_id)
            if r.impact_type_code == REMOVE:
                self.seed_delta[f.fr_id] = -(agreed or ZERO)
            elif not f.is_active:
                self.retired.append(f.fr_number)
                self.seed_delta[f.fr_id] = None
            elif f.effort_days is None:
                self.unrated.append(f.fr_number)
                self.seed_delta[f.fr_id] = None
            else:
                self.seed_delta[f.fr_id] = f.effort_days - (agreed or ZERO) if r.impact_type_code == MODIFY \
                    else f.effort_days
        self.delta = _q(sum((d for d in self.seed_delta.values() if d is not None), ZERO))
        self.exposed = _q(sum((self.agreed.get(i) or ZERO for c, i in self.reached if c == "impacted_fr_id"), ZERO))
        self.values = self._benefits()

    def _benefits(self) -> dict[int, tuple[str, Decimal, Decimal | None]]:
        """benefit id → (unit, value at stake, value change or None when not measured against the target)."""
        sols = {i for c, i in self.reached if c == "impacted_solution_id"}
        bens = [i for c, i in self.reached if c == "impacted_benefit_id"]
        if not bens:
            return {}
        measured = self.measured()
        frozen_b = _shadow_rows(self.db, self.target, "benefit", bens) if measured else {}
        t = freeze_set.shadow("benefit_solution")
        frozen_pct: dict[int, Decimal] = defaultdict(Decimal)
        if measured:
            for bid, pct in self.db.execute(select(t.c.benefit_id, t.c.contribution_pct).where(
                    t.c.baseline_id == self.target.baseline_id, t.c.benefit_id.in_(bens), t.c.solution_id.in_(sols))):
                frozen_pct[bid] += pct
        live_pct: dict[int, Decimal] = defaultdict(Decimal)
        for ln in benefit_service.live_links(self.db, project_id=self.cr.project_id):
            if ln.benefit_id in bens and ln.solution_id in sols:
                live_pct[ln.benefit_id] += ln.contribution_pct
        out = {}
        for b in self.db.scalars(select(Benefit).where(Benefit.benefit_id.in_(bens))).unique():
            stake = abs(b.target_value - b.baseline_value) * live_pct[b.benefit_id] / HUNDRED
            change = None
            if measured:
                fb = frozen_b.get(b.benefit_id)
                was = abs(fb["target_value"] - fb["baseline_value"]) * frozen_pct[b.benefit_id] / HUNDRED if fb else ZERO
                change = _q(stake - was)
            out[b.benefit_id] = (b.measure_unit.strip(), _q(stake), change)
        return out

    def measured(self) -> bool:
        return _measured(self.db, self.target)


def _measured(db: Session, target: Baseline) -> bool:
    """A6: value change is measured only against a target that froze benefits (spec 7+, BENEFIT on)."""
    return (target.hash_spec_version >= BENEFIT_SPEC
            and "BENEFIT" in baseline_service.components_of(db, target.baseline_id))


def analyse(db: Session, actor_id: int, cr: ChangeRequest, row_version: int) -> ChangeRequest:
    """Trace and price, one action (spec §1). Rows reached before are restored; rows no longer reached retire."""
    lifecycle.lock(db, cr)
    lifecycle.check_live(cr, row_version)
    _require_undecided(cr)
    p = _Price(db, cr, db.get(Baseline, cr.against_baseline_id))
    if not p.seeds:
        raise HTTPException(422, "Mark at least one requirement the change adds, modifies or removes first")
    if p.retired:
        raise HTTPException(422, f"{', '.join(sorted(p.retired))} retired since it was seeded: set the seeds again")
    rows = {_key(r): r for r in db.scalars(select(CrImpact).where(CrImpact.change_request_id == cr.change_request_id))}
    for key, row in rows.items():
        if row.is_active and not row.is_seed and key not in p.reached:
            lifecycle.soft_delete(row, actor_id)
            row.updated_by = actor_id
    for key, route in p.reached.items():
        row = rows.get(key)
        if row is None:
            row = CrImpact(project_id=cr.project_id, change_request_id=cr.change_request_id, **{key[0]: key[1]},
                           is_seed=False, reached_via=route, created_by=actor_id)
            db.add(row)
            rows[key] = row
        else:
            row.is_active, row.deleted_at, row.deleted_by = True, None, None
            row.is_seed, row.impact_type_code_id, row.reached_via, row.updated_by = False, None, route, actor_id
        row.effort_delta_days = None
    db.flush()                                          # new rows take is_active from the server default
    for key, row in rows.items():
        if not row.is_active:
            continue
        col, oid = key
        row.agreed_effort_days = p.agreed.get(oid) if col == "impacted_fr_id" else None
        if row.is_seed and col == "impacted_fr_id":
            d = p.seed_delta.get(oid)
            row.effort_delta_days = None if d is None else _q(d)
        unit, stake, change = p.values.get(oid, (None, None, None)) if col == "impacted_benefit_id" else (None,) * 3
        row.value_unit, row.value_at_stake, row.value_change = unit, stake, change
    cr.effort_delta_days, cr.effort_exposed_days = p.delta, p.exposed
    cr.unrated_fr_count, cr.priced_at = len(p.unrated), datetime.now(UTC)
    _set_status(db, cr, ANALYSED_CODE if p.unrated else PRICED_CODE)
    cr.updated_by = actor_id
    db.flush()
    audit.record(db, "CR_PRICED", actor_id=actor_id, project_id=cr.project_id, target_table="change_request",
                 target_id=cr.change_request_id,
                 detail={"cr_number": cr.cr_number, "status": ANALYSED_CODE if p.unrated else PRICED_CODE,
                         "effort_delta_days": _s(p.delta), "effort_exposed_days": _s(p.exposed),
                         "unrated": sorted(p.unrated), "reached": len(p.reached)})
    db.commit()
    db.refresh(cr)
    return cr


# ---- decide ----------------------------------------------------------------------------------------------------------
def _cut(db: Session, cr: ChangeRequest, cut_id: int) -> ChangeRequest:
    """CR-3: one approved decrease of this project, on the same baseline, not used before. Locked FOR UPDATE; a race
    between two increases claiming it is settled by uq_cr_displaces_once."""
    cut = db.scalar(select(ChangeRequest).where(ChangeRequest.change_request_id == cut_id,
                                                ChangeRequest.project_id == cr.project_id)
                    .with_for_update(of=ChangeRequest))
    if cut is None:
        raise HTTPException(404, "The change request offered as a cut was not found in this project")
    if cut.change_request_id == cr.change_request_id or _state(cut) != APPROVED or not (cut.effort_delta_days or 0) < 0:
        raise HTTPException(422, f"{cut.cr_number} is not an approved decrease: only one can cover an increase")
    if cut.against_baseline_id != cr.against_baseline_id:
        raise HTTPException(422, f"{cut.cr_number} changes {_baseline_label(db, cut.against_baseline_id)}, not "
                                 f"{_baseline_label(db, cr.against_baseline_id)}: a cut covers an increase on the "
                                 f"same baseline")
    user = db.scalar(select(ChangeRequest.cr_number).where(ChangeRequest.displaces_cr_id == cut.change_request_id))
    if user is not None:
        raise HTTPException(409, f"{cut.cr_number} already covers {user}: each cut is used once")
    return cut


def _cover(db: Session, cr: ChangeRequest, fields: dict) -> tuple[ChangeRequest | None, Decimal | None]:
    """(cut, budget days). Criterion 65: an approved increase not covered by both together is a 422."""
    cut_id = fields.get("displaces_cr_id")
    ref = (fields.get("budget_reference") or "").strip() or None
    by = (fields.get("budget_approved_by") or "").strip() or None
    delta = cr.effort_delta_days
    if delta <= 0:
        if cut_id is not None or ref or by:
            raise HTTPException(422, f"{cr.cr_number} does not add effort: it needs no cut or budget")
        return None, None
    cut = _cut(db, cr, cut_id) if cut_id is not None else None
    left = delta + (cut.effort_delta_days if cut else ZERO)        # the cut's delta is negative
    if left <= 0:
        if ref or by:
            raise HTTPException(422, f"{cut.cr_number} covers the whole increase: no budget record is needed")
        return cut, None
    if not (ref and by):
        covered = f" {cut.cr_number} covers {_s(-cut.effort_delta_days)} days;" if cut else ""
        raise HTTPException(422, f"{cr.cr_number} adds {_s(delta)} days.{covered} {_s(left)} days need a budget "
                                 f"record (reference and who approved it) or an approved cut")
    return cut, _q(left)


def _analysis(db: Session, project_id: int) -> str | None:
    found = db.scalar(select(ControlRule.control_rule_id).where(ControlRule.project_id == project_id,
                                                                ControlRule.analysis_code == PRICED_DIFF,
                                                                ControlRule.is_active))
    return PRICED_DIFF if found is not None else None


def _write_decision(db: Session, actor_id: int, cr: ChangeRequest, outcome: CodeMaster, fields: dict) -> Decision:
    title = f"{cr.cr_number} {outcome.label}: {cr.title}"
    return decision_service.insert_decision(
        db, actor_id, cr.project_id,
        {"title": title if len(title) <= 200 else title[:199] + "…", "decision_text": fields.get("rationale"),
         "alternative_rejected": fields.get("alternative_rejected"), "dimension_code": SCOPE,
         "analysis_code": _analysis(db, cr.project_id), "decided_on": fields.get("decided_on"),
         "supersedes_decision_id": cr.decision_id}, via_cr=True)


def decide(db: Session, actor_id: int, cr: ChangeRequest, row_version: int, fields: dict) -> ChangeRequest:
    lifecycle.lock(db, cr)
    lifecycle.check_live(cr, row_version)
    _require_undecided(cr)
    code = (fields.get("outcome_code") or "").strip()
    if code not in OUTCOMES:
        raise HTTPException(422, "The outcome is approved, rejected or deferred")
    outcome = _status(db, cr.project_id, code)
    if outcome.behaviour_code == DEFERRED and _state(cr) == DEFERRED:
        raise HTTPException(409, f"{cr.cr_number} is already deferred and nothing has changed")
    cut, budget = None, None
    if outcome.behaviour_code == APPROVED:
        if cr.priced_at is None or cr.unrated_fr_count != 0:    # PRICED, or DEFERRED after a full price
            raise HTTPException(409, f"{cr.cr_number} is not priced: trace and price it before approving")
        # seed FRs FOR SHARE until the decision commits; the overlap re-checked under them (sara H1)
        _refuse_overlap(db, cr, _seed_fr_ids(db, cr, share=True))
        p = _Price(db, cr, db.get(Baseline, cr.against_baseline_id))
        if p.retired:
            raise HTTPException(409, f"{', '.join(sorted(p.retired))} retired since pricing: set the seeds again")
        if p.delta != cr.effort_delta_days or len(p.unrated) != cr.unrated_fr_count:
            raise HTTPException(409, f"The price of {cr.cr_number} has moved ({_s(cr.effort_delta_days)} → "
                                     f"{_s(p.delta)} days): trace and price again")
        cut, budget = _cover(db, cr, fields)
    elif fields.get("displaces_cr_id") is not None or fields.get("budget_reference") or fields.get("budget_approved_by"):
        raise HTTPException(422, "Only an approval takes a cut or a budget record")
    dec = _write_decision(db, actor_id, cr, outcome, fields)
    cr.status_code_id, cr.status_behaviour, cr.decision_id = outcome.code_id, outcome.behaviour_code, dec.decision_id
    if cut is not None:
        cr.displaces_cr_id = cut.change_request_id
    if budget is not None:
        cr.budget_increase_days = budget
        cr.budget_reference = fields["budget_reference"].strip()
        cr.budget_approved_by = fields["budget_approved_by"].strip()
    cr.updated_by = actor_id
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if "uq_cr_displaces_once" in str(exc.orig):
            raise HTTPException(409, "That cut was just used by another change request: choose another") from None
        raise
    audit.record(db, "CR_DECIDED", actor_id=actor_id, project_id=cr.project_id, target_table="change_request",
                 target_id=cr.change_request_id,
                 detail={"cr_number": cr.cr_number, "outcome": code, "decision_number": dec.decision_number,
                         "effort_delta_days": _s(cr.effort_delta_days),
                         "cut": cut.cr_number if cut else None, "budget_increase_days": _s(budget)})
    db.commit()
    db.refresh(cr)
    return cr


def correct_decision(db: Session, actor_id: int, cr: ChangeRequest, row_version: int, fields: dict) -> ChangeRequest:
    """A decided CR's decision (wrong date, text or alternative) corrected: a superseding DEC, same outcome (R2 M)."""
    lifecycle.lock(db, cr)
    lifecycle.check_live(cr, row_version)
    if _state(cr) not in OUTCOMES or cr.decision_id is None:
        raise HTTPException(409, f"{cr.cr_number} has no decision to correct")
    dec = _write_decision(db, actor_id, cr, cr.status_code_row, fields)
    before = db.scalar(select(Decision.decision_number).where(Decision.decision_id == cr.decision_id))
    cr.decision_id, cr.updated_by = dec.decision_id, actor_id
    db.flush()
    audit.record(db, "CR_DECISION_CORRECTED", actor_id=actor_id, project_id=cr.project_id,
                 target_table="change_request", target_id=cr.change_request_id,
                 detail={"cr_number": cr.cr_number, "decision_number": dec.decision_number, "supersedes": before})
    db.commit()
    db.refresh(cr)
    return cr


# ---- retire / restore ------------------------------------------------------------------------------------------------
def retire(db: Session, actor_id: int, cr: ChangeRequest, row_version: int) -> None:
    """Open only: a CR with a decision on record (deferred included) is evidence and stays (spec §1)."""
    lifecycle.lock(db, cr)
    if _state(cr) not in UNDECIDED or cr.decision_id is not None:
        raise HTTPException(409, f"{cr.cr_number} has a decision on record: it is kept as evidence")
    lifecycle.retire(db, actor_id, cr, row_version)


def _seed_fr_ids(db: Session, cr: ChangeRequest, *, share: bool) -> list[int]:
    """The CR's live seed FRs, locked: FOR SHARE while deciding, FOR UPDATE (as set_seeds) while restoring."""
    q = (select(FunctionRequirement.fr_id).join(CrImpact, CrImpact.impacted_fr_id == FunctionRequirement.fr_id)
         .where(CrImpact.change_request_id == cr.change_request_id, CrImpact.is_seed, CrImpact.is_active)
         .order_by(FunctionRequirement.fr_id).with_for_update(read=share, of=FunctionRequirement))
    return list(db.scalars(q))


def restore(db: Session, actor_id: int, cr: ChangeRequest) -> ChangeRequest:
    """sara H1: a retired CR's seeds stop blocking others (CR-1), so bringing it back re-checks the overlap."""
    lifecycle.lock(db, cr)
    if not cr.is_active:
        _refuse_overlap(db, cr, _seed_fr_ids(db, cr, share=False))
    lifecycle.restore(db, actor_id, cr)
    db.refresh(cr)
    return cr


# ---- reads -----------------------------------------------------------------------------------------------------------
def _names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.execute(select(AppUser.app_user_id, AppUser.display_name)
                           .where(AppUser.app_user_id.in_(ids))).all()) if ids else {}


def cr_out(db: Session, cr: ChangeRequest, decisions: dict | None = None, names: dict | None = None,
           labels: dict | None = None, numbers: dict | None = None) -> dict:
    dec = (decisions or {}).get(cr.decision_id) if decisions is not None else (
        db.get(Decision, cr.decision_id) if cr.decision_id else None)
    names = names if names is not None else _names(db, [cr.raised_by_user_id, dec.decided_by_user_id if dec else None])
    label = (labels or {}).get(cr.against_baseline_id) if labels is not None else _baseline_label(
        db, cr.against_baseline_id)
    cut = (numbers or {}).get(cr.displaces_cr_id) if numbers is not None else (
        db.scalar(select(ChangeRequest.cr_number).where(ChangeRequest.change_request_id == cr.displaces_cr_id))
        if cr.displaces_cr_id else None)
    return {"change_request_id": cr.change_request_id, "project_id": cr.project_id, "cr_number": cr.cr_number,
            "title": cr.title, "rationale": cr.rationale, "origin_code": cr.origin_code,
            "status_code": cr.status_code, "status_behaviour": cr.status_behaviour,
            "against_baseline_id": cr.against_baseline_id, "against_label": label,
            "raised_by_user_id": cr.raised_by_user_id, "raised_by_name": names.get(cr.raised_by_user_id),
            "effort_delta_days": _s(cr.effort_delta_days), "effort_exposed_days": _s(cr.effort_exposed_days),
            "unrated_fr_count": cr.unrated_fr_count, "priced_at": cr.priced_at,
            "decision_id": cr.decision_id, "decision_number": dec.decision_number if dec else None,
            "decided_on": dec.decided_on if dec else None,
            "decided_by_name": names.get(dec.decided_by_user_id) if dec else None,
            "displaces_cr_id": cr.displaces_cr_id, "displaces_cr_number": cut,
            "budget_increase_days": _s(cr.budget_increase_days), "budget_reference": cr.budget_reference,
            "budget_approved_by": cr.budget_approved_by, "created_at": cr.created_at, "updated_at": cr.updated_at,
            "is_active": cr.is_active, "row_version": cr.row_version}


def list_change_requests(db: Session, project_id: int, *, status: str | None = None, origin: str | None = None,
                         against: int | None = None, include_retired: bool = False) -> list[dict]:
    """Newest first (spec §1 cr_register)."""
    q = select(ChangeRequest).where(ChangeRequest.project_id == project_id)
    if not include_retired:
        q = q.where(ChangeRequest.is_active)
    if status:
        q = q.where(ChangeRequest.status_code_row.has(code=status))
    if origin:
        q = q.where(ChangeRequest.origin_code_row.has(code=origin))
    if against is not None:
        q = q.where(ChangeRequest.against_baseline_id == against)
    rows = list(db.scalars(q.order_by(ChangeRequest.change_request_id.desc())).unique())
    decisions = {d.decision_id: d for d in db.scalars(select(Decision).where(
        Decision.decision_id.in_([r.decision_id for r in rows if r.decision_id]))).unique()}
    names = _names(db, [r.raised_by_user_id for r in rows] + [d.decided_by_user_id for d in decisions.values()])
    labels = dict(db.execute(select(Baseline.baseline_id, Baseline.version_label)
                             .where(Baseline.project_id == project_id)).all())
    numbers = dict(db.execute(select(ChangeRequest.change_request_id, ChangeRequest.cr_number)
                              .where(ChangeRequest.project_id == project_id)).all())
    return [cr_out(db, r, decisions, names, labels, numbers) for r in rows]


def _objects(db: Session, rows: list[CrImpact]) -> dict[tuple[str, int], object]:
    out = {}
    for col, (model, *_rest) in KINDS.items():
        ids = [getattr(r, col) for r in rows if getattr(r, col) is not None]
        if ids:
            pk = model.__mapper__.primary_key[0]
            out |= {(col, lifecycle.pk(o)): o for o in db.scalars(select(model).where(pk.in_(ids))).unique()}
    return out


def detail(db: Session, cr: ChangeRequest) -> dict:
    """The CR page: the CR, its seeds and trace by kind, the price, per-unit benefit lines, waves, dependency pairs,
    displacement candidates, what moved since pricing and the parts a switched-off component kept out."""
    out = cr_out(db, cr)
    rows = list(db.scalars(select(CrImpact).where(CrImpact.change_request_id == cr.change_request_id,
                                                  CrImpact.is_active).order_by(CrImpact.cr_impact_id)).unique())
    objs = _objects(db, rows)
    impacts = []
    for r in rows:
        col, oid = _key(r)
        model, num, name, kind, _ = KINDS[col]
        o = objs[(col, oid)]
        impacts.append({"cr_impact_id": r.cr_impact_id, "kind": kind, "object_id": oid, "number": getattr(o, num),
                        "name": getattr(o, name), "object_retired": not o.is_active, "is_seed": r.is_seed,
                        "impact_type_code": r.impact_type_code, "reached_via": r.reached_via,
                        "effort_delta_days": _s(r.effort_delta_days), "agreed_effort_days": _s(r.agreed_effort_days),
                        "live_effort_days": _s(o.effort_days) if kind == "FR" else None,
                        "value_unit": r.value_unit, "value_at_stake": _s(r.value_at_stake),
                        "value_change": _s(r.value_change)})
    impacts.sort(key=lambda i: (KIND_ORDER[i["kind"]], not i["is_seed"], i["number"]))
    on = components.enabled(db, cr.project_id)
    target = db.get(Baseline, cr.against_baseline_id)
    units: dict[str, dict] = {}
    for i in impacts:
        if i["kind"] != "BENEFIT" or i["value_unit"] is None:
            continue
        k = benefit_service.unit_key(i["value_unit"])
        u = units.setdefault(k, {"unit": i["value_unit"], "value_at_stake": ZERO, "value_change": ZERO,
                                 "benefits": []})
        u["value_at_stake"] += Decimal(i["value_at_stake"])
        u["value_change"] = None if i["value_change"] is None or u["value_change"] is None else (
            u["value_change"] + Decimal(i["value_change"]))
        u["benefits"].append(i["number"])
    out.update({
        "seeds": [i for i in impacts if i["is_seed"]], "impacts": [i for i in impacts if not i["is_seed"]],
        "value_by_unit": [{**u, "value_at_stake": _s(u["value_at_stake"]), "value_change": _s(u["value_change"])}
                          for _, u in sorted(units.items())],
        "value_measured": _measured(db, target),
        "skipped_parts": [c for c in TRACE_PARTS if c not in on],
        "waves": sorted(i["number"] for i in impacts if i["kind"] == "WAVE"),
        "dependencies": _dependencies(db, cr.project_id, {i["object_id"] for i in impacts if i["kind"] == "SOLUTION"}),
        "displacement_candidates": _displacement(db, cr.project_id, set(units)) if units else [],
        "moved_since_pricing": _moved(db, cr, target, rows, objs) if cr.priced_at and _state(cr) in UNDECIDED else [],
        "unagreed_edits": [e for e in unagreed_edits(db, cr.project_id) if e["cr_number"] == cr.cr_number],
    })
    return out


def _dependencies(db: Session, project_id: int, sols: set[int]) -> list[dict]:
    if not sols:
        return []
    rows = db.scalars(select(SolutionDependency).where(
        SolutionDependency.project_id == project_id, SolutionDependency.is_active,
        or_(SolutionDependency.solution_id.in_(sols), SolutionDependency.depends_on_solution_id.in_(sols)))).unique()
    out = [{"solution_number": d.solution_row.solution_number, "depends_on_number": d.prereq_row.solution_number,
            "both_impacted": d.solution_id in sols and d.depends_on_solution_id in sols} for d in rows]
    return sorted(out, key=lambda d: (d["solution_number"], d["depends_on_number"]))


def _displacement(db: Session, project_id: int, unit_keys: set[str]) -> list[dict]:
    """The value ranking's displacement candidates in each impacted unit (the bottom quartile, delivering nothing
    elsewhere) — offered beside an increase, never chosen for it."""
    out = []
    for u in benefit_service.value_ranking(db, project_id)["units"]:
        if u["unit_key"] in unit_keys:
            out += [{"unit": u["unit"], "solution_number": r["solution_number"], "solution_name": r["solution_name"],
                     "value": r["value"], "effort_days": r["effort_days"]}
                    for r in u["ranked"] if r["displacement_candidate"]]
    return out


def _moved(db: Session, cr: ChangeRequest, target: Baseline, rows: list[CrImpact], objs: dict) -> list[str]:
    """What changed since pricing (criterion 9). Only the seed figures block an approval; the rest is shown."""
    p = _Price(db, cr, target)
    out = []
    if p.delta != cr.effort_delta_days or len(p.unrated) != cr.unrated_fr_count or p.retired:
        out.append("PRICE")
    if set(p.reached) != {_key(r) for r in rows if not r.is_seed}:
        out.append("TRACE")
    if p.exposed != cr.effort_exposed_days:
        out.append("EXPOSURE")
    stored = {r.impacted_benefit_id: (r.value_at_stake, r.value_change) for r in rows if r.impacted_benefit_id}
    if any(stored.get(b) != (v[1], v[2]) for b, v in p.values.items()) or set(stored) - set(p.values):
        out.append("VALUE")
    edited = sorted(getattr(o, KINDS[k[0]][1]) for k, o in objs.items()
                    if o.updated_at is not None and o.updated_at > cr.priced_at)
    if edited:
        out.append("EDITED:" + ", ".join(edited))
    return out


# ---- unagreed edits (spec §1, CR-1) ----------------------------------------------------------------------------------
def unagreed_edits(db: Session, project_id: int) -> list[dict]:
    """Every seed of an undecided, rejected or retired-undecided change whose live row differs from the target's
    frozen row (content hash at the target's spec), or exists on one side only. The edit is the team's to undo."""
    crs = list(db.scalars(select(ChangeRequest).where(
        ChangeRequest.project_id == project_id, ChangeRequest.status_behaviour != APPROVED)).unique())
    if not crs:
        return []
    # sara M3: a seed that a later, live APPROVED change also names carries that approved edit — never warn to undo it
    approved_later: dict[tuple[str, int], int] = {}
    for cr_id, br_id, fr_id in db.execute(
            select(CrImpact.change_request_id, CrImpact.impacted_br_id, CrImpact.impacted_fr_id)
            .join(ChangeRequest, ChangeRequest.change_request_id == CrImpact.change_request_id)
            .where(ChangeRequest.project_id == project_id, ChangeRequest.is_active,
                   ChangeRequest.status_behaviour == APPROVED, CrImpact.is_seed, CrImpact.is_active)):
        key = ("impacted_br_id", br_id) if br_id is not None else ("impacted_fr_id", fr_id)
        approved_later[key] = max(cr_id, approved_later.get(key, 0))
    on = components.enabled(db, project_id)
    out = []
    for cr in sorted(crs, key=lambda c: c.cr_number):
        seeds = list(db.scalars(select(CrImpact).where(CrImpact.change_request_id == cr.change_request_id,
                                                       CrImpact.is_active, CrImpact.is_seed)).unique())
        if not seeds:
            continue
        target = db.get(Baseline, cr.against_baseline_id)
        for table, col in ((BR_TABLE, "impacted_br_id"), (FR_TABLE, "impacted_fr_id")):
            ids = [getattr(r, col) for r in seeds if getattr(r, col) is not None]
            if not ids:
                continue
            frozen = {i: r["content_hash"] for i, r in _shadow_rows(db, target, table, ids).items()}
            q = freeze_set.live_select(freeze_set.BY_TABLE[table], project_id, on, target.hash_spec_version)
            live = {}
            if q is not None:
                sub = q.order_by(None).subquery()
                live = dict(db.execute(select(sub.c.source_id, sub.c.content_hash).where(sub.c.source_id.in_(ids))).all())
            model, num = KINDS[col][0], KINDS[col][1]
            pk = model.__mapper__.primary_key[0]
            numbers = dict(db.execute(select(pk, getattr(model, num)).where(pk.in_(ids))).all())
            for r in seeds:
                i = getattr(r, col)
                if i is None or frozen.get(i) == live.get(i) or approved_later.get((col, i), 0) > cr.change_request_id:
                    continue
                out.append({"cr_number": cr.cr_number, "change_request_id": cr.change_request_id,
                            "status_code": cr.status_code, "status_behaviour": cr.status_behaviour,
                            "retired": not cr.is_active, "number": numbers[i], "impact_type_code": r.impact_type_code,
                            "against_label": target.version_label})
    return out


def warning_lines(db: Session, project_id: int) -> list[dict]:
    """The freeze preview's one warning (spec §5): CR-0003 was rejected; FR-0012 still carries its change."""
    return [{**e, "message": f"{e['cr_number']} is {e['status_code'].lower()}"
                             f"{' and retired' if e['retired'] else ''}; {e['number']} still carries its change"}
            for e in unagreed_edits(db, project_id)]


def summary(db: Session, project_id: int) -> dict:
    """The M2 tile (slice 12): open and decided counts, net approved effort."""
    rows = db.execute(select(ChangeRequest.status_behaviour, ChangeRequest.effort_delta_days).where(
        ChangeRequest.project_id == project_id, ChangeRequest.is_active)).all()
    return {"open": sum(1 for s, _ in rows if s in UNDECIDED),
            "approved": sum(1 for s, _ in rows if s == APPROVED),
            "rejected": sum(1 for s, _ in rows if s == REJECTED),
            "net_approved_days": _s(sum((d or ZERO for s, d in rows if s == APPROVED), ZERO))}
