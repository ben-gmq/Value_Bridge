"""Waves (D-18; docs/slice15_phasing_spec.md, slice15_phasing_schema.md; W-1…W-9).

Shown as "Wave" on every screen (W-1); the code keeps `phase`. This module is the one owner of waves, a solution's
split across them and solution dependencies.

consistency_check lines (spec R1, T6), each must be empty — the independent proof that the service rules hold:
`solution_phase_split_not_100`, `solution_dependency_cycle`, `solution_phase_under_inactive`,
`solution_dependency_under_inactive`."""
from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, aliased

from models import CodeMaster, Phase, Solution, SolutionDependency, SolutionPhase
from services import audit, effort, lifecycle
from services.code_master import validate_required_code


# ---- consistency_check proofs ----------------------------------------------------------------------------------------
def split_not_100(db: Session, project_id: int | None) -> list[dict]:
    """W-5: a live split totals exactly 100 or has no rows. Must be empty."""
    total = func.sum(SolutionPhase.portion_pct)
    q = (select(Solution.solution_id, Solution.solution_number, total)
         .join(Solution, Solution.solution_id == SolutionPhase.solution_id)
         .where(SolutionPhase.is_active)
         .group_by(Solution.solution_id, Solution.solution_number)
         .having(total != 100))
    if project_id is not None:
        q = q.where(SolutionPhase.project_id == project_id)
    return [{"solution_id": i, "solution_number": n, "total_pct": str(t)}
            for i, n, t in db.execute(q.order_by(Solution.solution_id)).all()]


_CYCLE = """
WITH RECURSIVE reach(start_id, at_id) AS (
    SELECT solution_id, depends_on_solution_id FROM solution_dependency WHERE is_active {where}
    UNION
    SELECT r.start_id, d.depends_on_solution_id
      FROM reach r JOIN solution_dependency d ON d.solution_id = r.at_id AND d.is_active
)
SELECT DISTINCT r.start_id, s.solution_number FROM reach r JOIN solution s ON s.solution_id = r.start_id
 WHERE r.at_id = r.start_id ORDER BY r.start_id
"""


def dependency_cycle(db: Session, project_id: int | None) -> list[dict]:
    """D-18: no live dependency path leads back to where it started. Must be empty. The walk keeps (start, reached)
    pairs under UNION, so it ends on any graph, cyclic or not, in O(starts × edges) — never one row per path (sara
    M1). Every solution on a cycle is listed."""
    where = "AND project_id = :p" if project_id is not None else ""
    rows = db.execute(text(_CYCLE.format(where=where)), {"p": project_id} if project_id is not None else {}).all()
    return [{"solution_id": i, "solution_number": n} for i, n in rows]


def split_under_inactive(db: Session, project_id: int | None) -> list[dict]:
    """R1: a live split row whose solution or wave is retired. Must be empty."""
    q = (select(SolutionPhase.solution_phase_id, Solution.solution_number, Phase.phase_code)
         .join(Solution, Solution.solution_id == SolutionPhase.solution_id)
         .join(Phase, Phase.phase_id == SolutionPhase.phase_id)
         .where(SolutionPhase.is_active, ~(Solution.is_active & Phase.is_active)))
    if project_id is not None:
        q = q.where(SolutionPhase.project_id == project_id)
    return [{"solution_phase_id": i, "solution_number": s, "phase_code": p}
            for i, s, p in db.execute(q.order_by(SolutionPhase.solution_phase_id)).all()]


def dependency_under_inactive(db: Session, project_id: int | None) -> list[dict]:
    """R1: a live dependency whose either solution is retired. Must be empty."""
    need, prereq = aliased(Solution), aliased(Solution)
    q = (select(SolutionDependency.solution_dependency_id, need.solution_number, prereq.solution_number)
         .join(need, need.solution_id == SolutionDependency.solution_id)
         .join(prereq, prereq.solution_id == SolutionDependency.depends_on_solution_id)
         .where(SolutionDependency.is_active, ~(need.is_active & prereq.is_active)))
    if project_id is not None:
        q = q.where(SolutionDependency.project_id == project_id)
    return [{"solution_dependency_id": i, "solution_number": a, "depends_on_solution_number": b}
            for i, a, b in db.execute(q.order_by(SolutionDependency.solution_dependency_id)).all()]


# ---- shared ----------------------------------------------------------------------------------------------------------
# Two-key advisory locks (schema §4): never collide with bfc_set.py's single-key pg_advisory_xact_lock(project_id).
WAVE_ORDER_LOCK = 1501      # wave codes and order: create, edit, reorder, restore
DEPENDENCY_LOCK = 1502      # dependency writes: the no-cycle rule
CANCELLED, IN_DELIVERY = "CANCELLED", "IN_DELIVERY"     # R8: pinned (code_lists.PINNED), read by code here only
HUNDRED = Decimal("100")
CENT = Decimal("0.01")


def _xlock(db: Session, key: int, project_id: int) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:k, CAST(:p AS int4))"), {"k": key, "p": project_id})


def _status(db: Session, project_id: int, code: str | None) -> CodeMaster:
    """W-1 (sara L2): the refusal names a wave status, never the PHASE_STATUS category."""
    try:
        return validate_required_code(db, project_id, "PHASE_STATUS", code, "status_code")
    except HTTPException as e:
        raise HTTPException(e.status_code, "Choose a wave status from the list") from None


def _clean(value: str | None, field: str, limit: int) -> str:
    v = (value or "").strip()
    if not v:
        raise HTTPException(422, f"{field} cannot be empty")
    if len(v) > limit:
        raise HTTPException(422, f"{field} is longer than {limit} characters")
    return v


def _dates(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise HTTPException(422, "The end date cannot be before the start date")


def _code_free(db: Session, project_id: int, code: str, phase_id: int | None = None) -> None:
    """uq_phase_code_live normalises as lower(btrim()); this names the clash, the index decides a race."""
    q = select(Phase.phase_id).where(Phase.project_id == project_id, Phase.is_active,
                                     func.lower(func.btrim(Phase.phase_code)) == code.strip().lower())
    if phase_id is not None:
        q = q.where(Phase.phase_id != phase_id)
    if db.scalar(q.limit(1)) is not None:
        raise HTTPException(409, f"A live wave already uses the code {code}")


def _live_phases(db: Session, project_id: int) -> list[Phase]:
    return list(db.scalars(select(Phase).where(Phase.project_id == project_id, Phase.is_active)
                           .order_by(Phase.seq_no)).unique())


def _next_seq(db: Session, project_id: int) -> int:
    top = db.scalar(select(func.max(Phase.seq_no)).where(Phase.project_id == project_id, Phase.is_active)) or 0
    if top >= 99:
        raise HTTPException(422, "A project can have at most 99 waves")
    return top + 1


def _live_solution(solution: Solution) -> None:
    if not solution.is_active:
        raise HTTPException(409, f"{lifecycle.label(solution)} is retired. Restore it first.")


# ---- waves (§3: add / edit / reorder / retire / restore) -------------------------------------------------------------
def list_phases(db: Session, project_id: int, include_retired: bool = False) -> list[Phase]:
    q = select(Phase).where(Phase.project_id == project_id)
    if not include_retired:
        q = q.where(Phase.is_active)
    return list(db.scalars(q.order_by(Phase.is_active.desc(), Phase.seq_no, Phase.phase_id)).unique())


def create_phase(db: Session, actor_id: int, project_id: int, fields: dict) -> Phase:
    """The new wave goes to the end of the order. Codes are typed (no series) and unique among live waves."""
    _xlock(db, WAVE_ORDER_LOCK, project_id)
    code = _clean(fields.get("phase_code"), "Wave code", 20)
    name = _clean(fields.get("phase_name"), "Wave name", 200)
    _dates(fields.get("start_date"), fields.get("end_date"))
    status = _status(db, project_id, fields.get("status_code"))
    _code_free(db, project_id, code)
    row = Phase(project_id=project_id, phase_code=code, phase_name=name, seq_no=_next_seq(db, project_id),
                start_date=fields.get("start_date"), end_date=fields.get("end_date"), status_code_id=status.code_id,
                created_by=actor_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_phase(db: Session, actor_id: int, row: Phase, row_version: int, fields: dict) -> Phase:
    """A status change is free (Q-57); a CANCELLED wave keeps its splits as its own plan line (Q-64)."""
    _xlock(db, WAVE_ORDER_LOCK, row.project_id)
    lifecycle.lock(db, row)
    lifecycle.check_live(row, row_version)
    if "phase_code" in fields:
        row.phase_code = _clean(fields["phase_code"], "Wave code", 20)
        _code_free(db, row.project_id, row.phase_code, row.phase_id)
    if "phase_name" in fields:
        row.phase_name = _clean(fields["phase_name"], "Wave name", 200)
    if "start_date" in fields:
        row.start_date = fields["start_date"]
    if "end_date" in fields:
        row.end_date = fields["end_date"]
    _dates(row.start_date, row.end_date)
    if "status_code" in fields:
        row.status_code_id = _status(db, row.project_id, fields["status_code"]).code_id
    row.updated_by = actor_id
    db.commit()
    db.refresh(row)
    return row


def reorder_phases(db: Session, actor_id: int, project_id: int, order: list[tuple[int, int]]) -> list[Phase]:
    """`order`: (phase id, row_version) for EVERY live wave, in the new order (the br_lines.reorder pattern). Two
    passes, because uq_phase_seq_live is checked row by row: park every wave on a negative seq, then place it."""
    _xlock(db, WAVE_ORDER_LOCK, project_id)
    live = {p.phase_id: p for p in _live_phases(db, project_id)}
    ids = [i for i, _ in order]
    if sorted(ids) != sorted(live) or len(set(ids)) != len(ids):
        raise HTTPException(422, "Send every live wave of this project exactly once")
    for phase_id, version in order:
        lifecycle.check_version(live[phase_id], version)
    for n, phase_id in enumerate(ids, 1):
        live[phase_id].seq_no = -n
    db.flush()
    for n, phase_id in enumerate(ids, 1):
        live[phase_id].seq_no = n
        live[phase_id].updated_by = actor_id
    db.flush()
    audit.record(db, "PHASES_REORDERED", actor_id=actor_id, project_id=project_id, target_table="phase",
                 target_id=ids[0] if ids else None, detail={"order": ids})
    db.commit()
    return _live_phases(db, project_id)


def restore_phase(db: Session, actor_id: int, row: Phase) -> Phase:
    """409 while a live wave holds its code. A restored wave goes to the end of the order (its old position may be
    taken), as a restored requirement line does."""
    _xlock(db, WAVE_ORDER_LOCK, row.project_id)
    lifecycle.lock(db, row)
    if row.is_active:
        raise HTTPException(409, f"{lifecycle.label(row)} is not retired")
    _code_free(db, row.project_id, row.phase_code, row.phase_id)

    def to_end(r: Phase) -> None:
        r.seq_no = _next_seq(db, r.project_id)
    lifecycle.restore(db, actor_id, row, before_activate=to_end)
    db.refresh(row)
    return row


# ---- a solution's split across waves (§3, W-5; spec §10 T1–T4, R1, R2, R7) -----------------------------------------
def _pct(value) -> Decimal:
    """T3: exact Decimal, at most two decimals, never a float sum; 0 % refused (a row means a share)."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, "A share must be a number") from None
    if not d.is_finite() or d.as_tuple().exponent < -2:
        raise HTTPException(422, "A share takes at most two decimals")
    if d <= 0 or d > HUNDRED:
        raise HTTPException(422, "Each wave's share must be more than 0 % and at most 100 %")
    return d


def split_rows(db: Session, solution_id: int) -> list[tuple[SolutionPhase, Phase]]:
    q = (select(SolutionPhase, Phase).join(Phase, Phase.phase_id == SolutionPhase.phase_id)
         .where(SolutionPhase.solution_id == solution_id, SolutionPhase.is_active)
         .order_by(Phase.seq_no, Phase.phase_id))
    return [(sp, ph) for sp, ph in db.execute(q).unique().all()]


def split_out(db: Session, solution: Solution) -> dict:
    return {"solution_id": solution.solution_id,
            "rows": [{"solution_phase_id": sp.solution_phase_id, "phase_id": ph.phase_id, "phase_code": ph.phase_code,
                      "phase_name": ph.phase_name, "phase_status_code": ph.status_code, "seq_no": ph.seq_no,
                      "portion_pct": sp.portion_pct, "row_version": sp.row_version}
                     for sp, ph in split_rows(db, solution.solution_id)]}


def save_split(db: Session, actor_id: int, solution: Solution, based_on: list[tuple[int, int]],
               rows: list[tuple[int, object]]) -> dict:
    """The whole split at once (Q-63, T1). `based_on` must be exactly the live set (else 409, the lost-update guard);
    `rows` is the new split, one per wave, exactly 100 % or empty. Live rows whose wave is left out retire, a retired
    row of a named wave restores (S1-7), the rest insert. Locks (R1): the solution FOR NO KEY UPDATE (two splits of
    one solution serialise), then each wave FOR SHARE (a wave retire waits)."""
    db.execute(select(Solution.solution_id).where(Solution.solution_id == solution.solution_id)
               .with_for_update(key_share=True))
    db.refresh(solution)
    _live_solution(solution)
    mine = {r.solution_phase_id: r for r in db.scalars(select(SolutionPhase).where(
        SolutionPhase.solution_id == solution.solution_id))}
    basis_ids = [i for i, _ in based_on]
    if any(i not in mine for i in basis_ids):                               # T2: never another solution's row
        raise HTTPException(404, "Not found")
    live = {i: r for i, r in mine.items() if r.is_active}
    if sorted(basis_ids) != sorted(live) or len(set(basis_ids)) != len(basis_ids):
        raise HTTPException(409, "This split changed since you opened it. Reload and try again.")
    for i, version in based_on:
        lifecycle.check_version(live[i], version)
    wanted: dict[int, Decimal] = {}
    for phase_id, pct in rows:
        if phase_id in wanted:
            raise HTTPException(422, "Name each wave once")
        wanted[phase_id] = _pct(pct)
    if wanted and sum(wanted.values(), Decimal(0)) != HUNDRED:
        raise HTTPException(422, "The shares must total exactly 100 %, or leave the solution in no wave")
    phases: dict[int, Phase] = {}
    for phase_id in sorted(wanted):                                         # R7, then FOR SHARE in id order (R1)
        ph = db.scalars(select(Phase).where(Phase.phase_id == phase_id,
                                            Phase.project_id == solution.project_id)).unique().one_or_none()
        if ph is None:
            raise HTTPException(404, "Not found")
        lifecycle.lock_for_share(db, ph)
        if not ph.is_active:
            raise HTTPException(404, "Not found")
        phases[phase_id] = ph
    by_phase = {r.phase_id: r for r in mine.values()}
    for phase_id, pct in wanted.items():                                    # T4: no new effort into a cancelled wave
        if phases[phase_id].status_code == CANCELLED:
            kept = by_phase.get(phase_id)
            if kept is None or not kept.is_active or pct > kept.portion_pct:
                raise HTTPException(422, f"Wave {phases[phase_id].phase_code} is cancelled: its share can be kept "
                                         "or lowered, not added or raised")
    for r in live.values():
        if r.phase_id not in wanted:
            lifecycle.retire_row(db, actor_id, r)
    for phase_id, pct in wanted.items():
        r = by_phase.get(phase_id)
        if r is None:
            db.add(SolutionPhase(project_id=solution.project_id, solution_id=solution.solution_id, phase_id=phase_id,
                                 portion_pct=pct, created_by=actor_id))
        elif not r.is_active:
            r.portion_pct = pct
            lifecycle.relink(db, actor_id, r)
        elif r.portion_pct != pct:
            r.portion_pct = pct
            r.updated_by = actor_id
    db.flush()
    audit.record(db, "SOLUTION_PHASE_SPLIT_SAVED", actor_id=actor_id, project_id=solution.project_id,
                 target_table="solution", target_id=solution.solution_id,
                 detail={"rows": [{"phase_id": k, "portion_pct": str(v)} for k, v in sorted(wanted.items())]})
    db.commit()
    return split_out(db, solution)


# ---- dependencies (§3, schema §4; R1, R5) -----------------------------------------------------------------------------
_REACH = """
WITH RECURSIVE reach(s) AS (
    SELECT CAST(:b AS bigint)
    UNION
    SELECT d.depends_on_solution_id FROM solution_dependency d JOIN reach r ON d.solution_id = r.s WHERE d.is_active
)
SELECT 1 FROM reach WHERE s = :a LIMIT 1
"""


def _path(db: Session, project_id: int, start: int, goal: int) -> list[int]:
    """One live path start → … → goal, by breadth-first search over the project's live edges. Called only after
    _REACH found goal reachable, so the cost of naming the cycle is paid only when refusing (sara M1)."""
    edges: dict[int, list[int]] = {}
    for a, b in db.execute(select(SolutionDependency.solution_id, SolutionDependency.depends_on_solution_id).where(
            SolutionDependency.project_id == project_id, SolutionDependency.is_active)
            .order_by(SolutionDependency.solution_dependency_id)).all():
        edges.setdefault(a, []).append(b)
    before, todo = {start: None}, [start]
    while todo and goal not in before:
        nxt = []
        for n in todo:
            for m in edges.get(n, ()):
                if m not in before:
                    before[m] = n
                    nxt.append(m)
        todo = nxt
    out, n = [], goal
    while n is not None:
        out.append(n)
        n = before[n]
    return out[::-1]


def _dep_out(row: SolutionDependency) -> dict:
    return {"solution_dependency_id": row.solution_dependency_id, "solution_id": row.solution_id,
            "solution_number": row.solution_row.solution_number,
            "depends_on_solution_id": row.depends_on_solution_id,
            "depends_on_solution_number": row.prereq_row.solution_number,
            "depends_on_solution_name": row.prereq_row.solution_name, "note": row.note,
            "is_active": row.is_active, "row_version": row.row_version}


def dependencies_of(db: Session, solution: Solution) -> dict:
    def rows(col):
        return [_dep_out(r) for r in db.scalars(select(SolutionDependency).where(
            col == solution.solution_id, SolutionDependency.is_active)
            .order_by(SolutionDependency.solution_dependency_id))]
    return {"depends_on": rows(SolutionDependency.solution_id),
            "needed_by": rows(SolutionDependency.depends_on_solution_id)}


def link_solution_dependency(db: Session, actor_id: int, solution: Solution, depends_on_id: int,
                             note: str | None) -> dict:
    """The only writer of live edges, a re-link (restore) included (schema §4). The per-project advisory lock comes
    before any read of the graph; under READ COMMITTED the walk after it is a new snapshot, so two concurrent links
    that would close a cycle serialise and the second is refused (criterion 3)."""
    _xlock(db, DEPENDENCY_LOCK, solution.project_id)
    if db.scalar(text("SHOW transaction_isolation")) != "read committed":       # R5: the lock is the guarantee
        raise RuntimeError("a dependency link needs READ COMMITTED (schema §4)")   # logged, 500 (sara L4)
    prereq = db.scalars(select(Solution).where(Solution.solution_id == depends_on_id,
                                               Solution.project_id == solution.project_id)).unique().one_or_none()
    if prereq is None:
        raise HTTPException(422, "Choose a solution of this project")
    if prereq.solution_id == solution.solution_id:
        raise HTTPException(422, "A solution cannot depend on itself")
    for end in sorted((solution, prereq), key=lambda s: s.solution_id):     # R1: FOR SHARE, then the live check
        lifecycle.lock_for_share(db, end)
    for end in (solution, prereq):
        _live_solution(end)
    if db.scalar(text(_REACH), {"a": solution.solution_id, "b": prereq.solution_id}) is not None:
        path = _path(db, solution.project_id, prereq.solution_id, solution.solution_id)
        numbers = dict(db.execute(select(Solution.solution_id, Solution.solution_number)
                                  .where(Solution.solution_id.in_(path))).all())
        chain = " → ".join([solution.solution_number, *(numbers[i] for i in path)])
        raise HTTPException(422, f"Dependency cycle: {chain}")
    text_note = (note or "").strip() or None
    row = db.scalars(select(SolutionDependency).where(
        SolutionDependency.solution_id == solution.solution_id,
        SolutionDependency.depends_on_solution_id == prereq.solution_id).with_for_update(of=SolutionDependency)
    ).one_or_none()
    if row is None:
        row = SolutionDependency(project_id=solution.project_id, solution_id=solution.solution_id,
                                 depends_on_solution_id=prereq.solution_id, note=text_note, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{solution.solution_number} already depends on {prereq.solution_number}")
    else:                                                                   # re-link restores the same row (S1-7)
        previous, row.note = row.note, text_note
        lifecycle.relink(db, actor_id, row, detail={"previous_note": previous})   # sara L3, as DR1-D2
    db.commit()
    db.refresh(row)
    return _dep_out(row)


def unlink_solution_dependency(db: Session, actor_id: int, row: SolutionDependency, row_version: int) -> None:
    """Removing an edge cannot close a cycle, so no lock (schema §4). The caller fetched it under its solution."""
    lifecycle.unlink(db, actor_id, row, row_version)


# ---- the wave plan (§3; spec R3, R6, Q-61, Q-64, Q-65, Q-66: live only) ----------------------------------------------
def _largest_remainder(values: list[Decimal], target: Decimal) -> list[Decimal]:
    """R6: round each value to cents so the displayed figures add up to `target` (already in cents): floor every
    value, then give the cents left over to the largest remainders (ties by position)."""
    floors = [(v / CENT).to_integral_value(ROUND_FLOOR) for v in values]
    left = int((target / CENT) - sum(floors, Decimal(0)))
    order = sorted(range(len(values)), key=lambda i: (-(values[i] / CENT - floors[i]), i))
    for i in order[:max(0, min(left, len(values)))]:
        floors[i] += 1
    return [f * CENT for f in floors]


def plan(db: Session, project_id: int) -> dict:
    """Effort per wave from current FR effort × each solution's share (W-2: through the solution only), plus UNPHASED
    (solutions in no wave) and UNASSIGNED (rated FRs with no solution), adding up to the effort headline exactly
    (R3: built from effort.summary's by_solution, the headline's own basis). Displayed figures are rounded so they
    add up too (R6): the lines to the headline, each line's solutions to the line."""
    summ = effort.summary(db, project_id)
    headline = summ["total_days"]
    days_of = {e["solution_id"]: e["days"] for e in summ["by_solution"]}
    phases = _live_phases(db, project_id)
    sols = {s.solution_id: s for s in db.scalars(select(Solution).where(Solution.project_id == project_id,
                                                                       Solution.is_active)).unique()}
    rejected = {i for i, s in sols.items() if s.status_code == "REJECTED"}  # pinned, as effort.summary reads it
    splits: dict[int, list[SolutionPhase]] = {}
    for sp in db.scalars(select(SolutionPhase).join(Phase, Phase.phase_id == SolutionPhase.phase_id).where(
            SolutionPhase.project_id == project_id, SolutionPhase.is_active, Phase.is_active)):
        splits.setdefault(sp.solution_id, []).append(sp)

    per_wave: dict[int, list[tuple[Solution, Decimal, Decimal]]] = {p.phase_id: [] for p in phases}
    unphased: list[tuple[Solution, Decimal]] = []
    for sid, s in sorted(sols.items(), key=lambda kv: kv[1].solution_number):
        if sid in rejected:
            continue                                                       # S6c-8: outside the headline
        days = days_of.get(sid, Decimal(0))
        if sid in splits:
            for sp in splits[sid]:
                per_wave[sp.phase_id].append((s, sp.portion_pct, days * sp.portion_pct / HUNDRED))
        else:
            unphased.append((s, days))
    unassigned = days_of.get(None, Decimal(0))

    exact = [sum((d for _, _, d in per_wave[p.phase_id]), Decimal(0)) for p in phases]
    exact.append(sum((d for _, d in unphased), Decimal(0)))
    exact.append(unassigned)
    shown = _largest_remainder(exact, headline.quantize(CENT, ROUND_HALF_UP))

    lines = []
    for p, line_total in zip(phases, shown):
        items = per_wave[p.phase_id]
        rounded = _largest_remainder([d for *_, d in items], line_total)
        lines.append({"kind": "WAVE", "phase_id": p.phase_id, "phase_code": p.phase_code, "phase_name": p.phase_name,
                      "seq_no": p.seq_no, "status_code": p.status_code, "cancelled": p.status_code == CANCELLED,
                      "start_date": p.start_date, "end_date": p.end_date, "days": line_total,
                      "solutions": [{"solution_id": s.solution_id, "solution_number": s.solution_number,
                                     "solution_name": s.solution_name, "portion_pct": pct, "days": r}
                                    for (s, pct, _), r in zip(items, rounded)]})
    rounded = _largest_remainder([d for _, d in unphased], shown[-2])
    lines.append({"kind": "UNPHASED", "days": shown[-2],
                  "solutions": [{"solution_id": s.solution_id, "solution_number": s.solution_number,
                                 "solution_name": s.solution_name, "portion_pct": None, "days": r}
                                for (s, _), r in zip(unphased, rounded)]})
    lines.append({"kind": "UNASSIGNED", "days": shown[-1], "solutions": []})

    seqs = {p.phase_id: p.seq_no for p in phases}
    waves_of = {sid: [seqs[sp.phase_id] for sp in rows] for sid, rows in splits.items()}
    warnings = []
    for d in db.scalars(select(SolutionDependency).where(SolutionDependency.project_id == project_id,
                                                         SolutionDependency.is_active)
                        .order_by(SolutionDependency.solution_dependency_id)):
        need, pre = sols.get(d.solution_id), sols.get(d.depends_on_solution_id)
        if need is None or pre is None or not waves_of.get(need.solution_id):
            continue
        first_need = min(waves_of[need.solution_id])
        pre_waves = waves_of.get(pre.solution_id)
        kind = ("PREREQ_UNSCHEDULED" if not pre_waves else "PREREQ_LATER" if max(pre_waves) > first_need
                else "PREREQ_SAME_WAVE" if max(pre_waves) == first_need else None)          # Q-61
        if kind:
            warnings.append({"kind": kind, "solution_number": need.solution_number,
                             "depends_on_solution_number": pre.solution_number})
    for sid in sorted(rejected & set(splits), key=lambda i: sols[i].solution_number):          # Q-65
        warnings.append({"kind": "REJECTED_WITH_SPLIT", "solution_number": sols[sid].solution_number,
                         "depends_on_solution_number": None})
    current = next((p.phase_id for p in phases if p.status_code == IN_DELIVERY), None)          # Q-57
    return {"total_days": headline, "total_shown": headline.quantize(CENT, ROUND_HALF_UP),
            "unrated_count": summ["unrated_count"], "current_phase_id": current, "lines": lines,
            "warnings": warnings}
