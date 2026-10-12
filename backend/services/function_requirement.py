"""Function requirements (§7.5, D-7/D-27/D-28). Spec: docs/slice6a_spec.md; schema:
docs/slice6a_schema.md. fr_number is minted at save; the type's behaviour is copied from the
resolved code and verified by fk_fr_type_code (D-27).

An FR may have no Solution (D-28): it saves with a warning. A Solution is always fetched scoped
to the FR's project first, then locked FOR SHARE and checked live (DR6a-S1, DR6a-D1) — the
solution.link pattern — so an FR can neither cross projects nor land under a retired Solution.
D-52 (slice 10b): the BR ↔ FR mapping is stored in br_function_requirement; solution_id is the FR's
"tag" — the one solution its effort counts toward — and must answer at least one of the BRs the FR serves
(set_solution, Q-3). D-34's suggested_br_id is retired (never built)."""
import logging

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from models import BfcNode, BrFunctionRequirement, BrSolution, BusinessRequirement, FunctionRequirement, Solution
from services import audit, effort, interface, lifecycle, numbering
from services.code_master import resolve, validate_required_code

log = logging.getLogger("vb")

# DR6a, law 6: the only plain columns a request may set. Type, status and solution are handled
# on their own; never project_id, the number, complexity, effort or the audit set.
EDITABLE = ("fr_name", "description", "acceptance_note")
TECH_CATEGORIES = ("TECHNOLOGY", "DATA")          # §7.5: an FR elsewhere is a finding, not a block


def _name(value: str | None) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(422, "fr_name cannot be empty")
    return name


def _solution(db: Session, project_id: int, solution_id: int) -> Solution:
    """Scoped to the FR's project BEFORE any lock, liveness check or label: another project's
    solution, live or retired, is the same 404 as a missing one (DR6a-S1)."""
    sol = db.scalars(select(Solution).where(Solution.solution_id == solution_id,
                                            Solution.project_id == project_id)).one_or_none()
    if sol is None:
        raise HTTPException(404, "Not found")
    lifecycle.lock_for_share(db, sol)                      # a concurrent retire waits (DR6a-D1)
    if not sol.is_active:
        raise HTTPException(409, f"{lifecycle.label(sol)} is retired. Restore it first.")
    return sol


def _type(db: Session, project_id: int, fr_type_code: str):
    code = validate_required_code(db, project_id, "FR_TYPE", fr_type_code, "fr_type_code")
    if not code.behaviour_code:                            # seeded with one; the FK proves the copy
        log.error("FR_TYPE %s has no behaviour in project %s", code.code, project_id)
        raise HTTPException(500, "Something went wrong.")
    return code


def _warnings(db: Session, fr: FunctionRequirement, sol: Solution | None) -> list[str]:
    out = []
    if not _linked_br_ids(db, fr.fr_id):
        out.append("no_br")                                # D-28 re-based on the link (slice10b Q-17)
    if sol is not None:
        if sol.category_code not in TECH_CATEGORIES:
            out.append("non_technology_solution")
        if sol.status_code == "REJECTED":                  # S6a-5 (VB-005 sara L-1: behaviour later)
            out.append("rejected_solution")
    same = select(func.count()).select_from(FunctionRequirement).where(
        FunctionRequirement.project_id == fr.project_id, FunctionRequirement.is_active,
        FunctionRequirement.fr_id != fr.fr_id,
        func.lower(func.btrim(FunctionRequirement.fr_name)) == fr.fr_name.strip().lower(),
        (FunctionRequirement.solution_id == fr.solution_id) if fr.solution_id is not None
        else FunctionRequirement.solution_id.is_(None))
    if db.scalar(same):
        out.append("duplicate_name")                       # DR6a-P2, S6a-2
    return out


def _live_links():
    return select(BrFunctionRequirement.fr_id).join(
        BusinessRequirement, BusinessRequirement.br_id == BrFunctionRequirement.br_id).where(
        BrFunctionRequirement.is_active, BusinessRequirement.is_active)


def list_frs(db: Session, project_id: int, include_retired: bool = False, unlinked: bool = False,
             unassigned: bool = False) -> list[FunctionRequirement]:
    """slice10b §6.10 [Q-17]: `unlinked` = no live BR link (untraced); `unassigned` = no solution tag. Each FR
    carries `br_count`, its live BR links."""
    q = select(FunctionRequirement).where(FunctionRequirement.project_id == project_id)
    if not include_retired:
        q = q.where(FunctionRequirement.is_active)
    if unlinked:
        q = q.where(FunctionRequirement.fr_id.not_in(_live_links().where(
            BrFunctionRequirement.project_id == project_id)))
    if unassigned:
        q = q.where(FunctionRequirement.solution_id.is_(None))
    frs = list(db.scalars(q.order_by(FunctionRequirement.fr_number)))
    counts = br_counts(db, project_id)
    for f in frs:
        f.br_count = counts.get(f.fr_id, 0)
    return frs


def br_counts(db: Session, project_id: int) -> dict[int, int]:
    return dict(db.execute(select(BrFunctionRequirement.fr_id, func.count())
                           .join(BusinessRequirement, BusinessRequirement.br_id == BrFunctionRequirement.br_id)
                           .where(BrFunctionRequirement.project_id == project_id, BrFunctionRequirement.is_active,
                                  BusinessRequirement.is_active)
                           .group_by(BrFunctionRequirement.fr_id)).all())


def with_br_count(db: Session, fr: FunctionRequirement) -> FunctionRequirement:
    fr.br_count = len(_linked_br_ids(db, fr.fr_id))
    return fr


def frs_of_solution(db: Session, sol: Solution) -> list[FunctionRequirement]:
    return list(db.scalars(select(FunctionRequirement).where(
        FunctionRequirement.solution_id == sol.solution_id, FunctionRequirement.is_active)
        .order_by(FunctionRequirement.fr_number)))


_BR_FR_ROWS = """
        SELECT v.br_function_requirement_id, l.row_version, v.coverage_note, v.br_id,
               v.fr_id, v.fr_number, fr.fr_name, ft.code AS fr_type_code, fr.fr_type_behaviour,
               fr.row_version AS fr_row_version,
               v.solution_id, s.solution_number, s.solution_name, v.tag_answers_br AS tag_answers_this_br
        FROM   v_br_function_requirement v
        JOIN   br_function_requirement l ON l.br_function_requirement_id = v.br_function_requirement_id
        JOIN   function_requirement fr   ON fr.fr_id = v.fr_id
        JOIN   code_master ft            ON ft.code_id = fr.fr_type_code_id
        LEFT JOIN solution s             ON s.solution_id = v.solution_id
        WHERE  v.br_id = :br AND v.project_id = :p"""


def frs_of_br(db: Session, br: BusinessRequirement) -> list[dict]:
    """slice10b §6.2: one row per live link (D-52), the FR's solution tag nullable, and whether that tag is a
    live solution of THIS BR."""
    rows = db.execute(text(_BR_FR_ROWS + " ORDER BY v.fr_number"),
                      {"br": br.br_id, "p": br.project_id}).mappings().all()
    return [dict(r) for r in rows]


def br_fr_row(db: Session, link: BrFunctionRequirement) -> dict:
    """One link as frs_of_br shows it — the shape the BR screen's POST / PATCH / PUT return."""
    r = db.execute(text(_BR_FR_ROWS + " AND v.br_function_requirement_id = :l"),
                   {"br": link.br_id, "p": link.project_id, "l": link.br_function_requirement_id}).mappings().one()
    return dict(r)


def brs_of_fr(db: Session, fr: FunctionRequirement) -> list[dict]:
    """The FR's live BR links (the FR page's traceability), with whether its tag answers each BR."""
    rows = db.execute(text("""
        SELECT v.br_function_requirement_id, l.row_version, v.coverage_note, v.br_id, br.br_number,
               n.hier_code, n.node_name, v.tag_answers_br
        FROM   v_br_function_requirement v
        JOIN   br_function_requirement l ON l.br_function_requirement_id = v.br_function_requirement_id
        JOIN   business_requirement br   ON br.br_id = v.br_id
        JOIN   bfc_node n                ON n.bfc_node_id = br.bfc_node_id
        WHERE  v.fr_id = :f AND v.project_id = :p
        ORDER  BY br.br_number"""), {"f": fr.fr_id, "p": fr.project_id}).mappings().all()
    return [dict(r) for r in rows]


def create_fr(db: Session, actor_id: int, project_id: int, name: str, fr_type_code: str,
              solution_id: int | None, fields: dict,
              br_id: int | None = None) -> tuple[FunctionRequirement, list]:
    """`br_id` (slice10b Q-20, DR10b-P3): create the FR and link it to that BR in one transaction, through the
    same link_fr (scoped 404, step → BR → FR locks). With a solution too, the BR-row rule applies: the solution
    must be a live solution of that BR (422)."""
    name = _name(name)
    ftype = _type(db, project_id, fr_type_code)
    br = None
    if br_id is not None:                                  # DR1-S1: scoped first, so another project's BR is 404
        br = db.scalars(select(BusinessRequirement).where(BusinessRequirement.br_id == br_id,
                                                          BusinessRequirement.project_id == project_id)).one_or_none()
        if br is None:
            raise HTTPException(404, "Not found")
    sol = _solution(db, project_id, solution_id) if solution_id is not None else None
    specified = next((c for c in resolve(db, project_id, "FR_FULFILMENT_STATUS") if c.code == "SPECIFIED"), None)
    if specified is None:                                  # L6: detail in the log only
        log.error("FR_FULFILMENT_STATUS/SPECIFIED missing for project %s", project_id)
        raise HTTPException(500, "Something went wrong.")
    fr = FunctionRequirement(project_id=project_id, fr_number=numbering.next_number(db, project_id, "FR"),
                             fr_name=name, solution_id=sol.solution_id if sol else None,
                             fr_type_code_id=ftype.code_id, fr_type_behaviour=ftype.behaviour_code,
                             fulfilment_status_code_id=specified.code_id, created_by=actor_id,
                             **{k: fields[k] for k in EDITABLE if k in fields and k != "fr_name"})
    db.add(fr)
    db.flush()
    drift = []
    if br is not None:
        _, drift = link_fr(db, actor_id, br, fr.fr_id, None, commit=False)
        if sol is not None:
            _require_answers_br(db, br, sol)
    warnings = [*_warnings(db, fr, sol), *drift]
    db.commit()
    db.refresh(fr)
    return with_br_count(db, fr), warnings


_UNSET = object()


def update_fr(db: Session, actor_id: int, fr: FunctionRequirement, row_version: int, fields: dict,
              fr_type_code: str | None, status_code: str | None,
              solution_id=_UNSET) -> tuple[FunctionRequirement, list[str]]:
    """`solution_id` is _UNSET when not sent, None to unlink, an id to (re)link."""
    lifecycle.lock(db, fr)                  # FOR UPDATE: a type change serialises with an interface PUT (sara 6b-2 L1)
    lifecycle.check_live(fr, row_version)
    before = {"previous_solution_number": fr.solution_row.solution_number if fr.solution_row else None,
              "previous_fr_type_code": fr.fr_type_code,
              "previous_effort_days": str(fr.effort_days) if fr.effort_days is not None else None}
    moved_days = None
    sol = fr.solution_row
    if solution_id is not _UNSET:
        sol = _solution(db, fr.project_id, solution_id) if solution_id is not None else None
    if "fr_name" in fields:
        fields["fr_name"] = _name(fields["fr_name"])
    for k in EDITABLE:
        if k in fields:
            setattr(fr, k, fields[k])
    moved = solution_id is not _UNSET and (sol.solution_id if sol else None) != fr.solution_id
    if moved and sol is not None:
        _require_answers_some_br(db, fr, sol)              # slice10b Q-3: the register's "at least one" rule
    retyped = False
    if moved:
        fr.solution_id = sol.solution_id if sol else None
    if fr_type_code is not None and fr_type_code != fr.fr_type_code:
        ftype = _type(db, fr.project_id, fr_type_code)
        if (fr.fr_type_behaviour == "INTERFACE" and ftype.behaviour_code != "INTERFACE"   # behaviour, not code
                and interface.live_detail_exists(db, fr.fr_id)):                         # criterion 102
            raise HTTPException(409, "This FR has interface detail. Remove it first, or keep an interface type")
        moved_days = effort.rederive_on_type_change(db, fr, ftype.code_id)                  # D-13; 422 if no cell
        fr.fr_type_code_id, fr.fr_type_behaviour = ftype.code_id, ftype.behaviour_code
        retyped = True
    if status_code is not None:
        fr.fulfilment_status_code_id = validate_required_code(
            db, fr.project_id, "FR_FULFILMENT_STATUS", status_code, "fulfilment_status_code").code_id
    fr.updated_by = actor_id
    if moved or retyped:                                   # DR6a-S2: who moved it, and from where
        audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=fr.project_id,
                     target_table="function_requirement", target_id=fr.fr_id,
                     detail={"label": lifecycle.label(fr), **before})
    db.flush()
    warnings = _warnings(db, fr, sol)
    if moved_days:                                         # DR6c-P2: a type change that moved the days says so
        warnings.append("effort_changed")
    db.commit()
    db.refresh(fr)
    fr.effort_change = {"previous_days": moved_days[0], "new_days": moved_days[1]} if moved_days else None
    return with_br_count(db, fr), warnings


def fr_under_inactive_solution(db: Session, project_id: int | None) -> list[dict]:
    """consistency_check line (DR6a-D1): live FRs whose Solution is retired. Must be empty."""
    q = (select(FunctionRequirement.fr_id, FunctionRequirement.fr_number, Solution.solution_number)
         .join(Solution, Solution.solution_id == FunctionRequirement.solution_id)
         .where(FunctionRequirement.is_active, ~Solution.is_active))
    if project_id is not None:
        q = q.where(FunctionRequirement.project_id == project_id)
    return [{"fr_id": i, "fr_number": n, "solution_number": s}
            for i, n, s in db.execute(q.order_by(FunctionRequirement.fr_number)).all()]



# ---- BR ↔ FR links and the solution tag (D-52; docs/slice10b_schema.md §1.2, §2) -----------------------------
def _linked_br_ids(db: Session, fr_id: int) -> list[int]:
    return list(db.scalars(select(BrFunctionRequirement.br_id)
                           .join(BusinessRequirement, BusinessRequirement.br_id == BrFunctionRequirement.br_id)
                           .where(BrFunctionRequirement.fr_id == fr_id, BrFunctionRequirement.is_active,
                                  BusinessRequirement.is_active)
                           .order_by(BrFunctionRequirement.br_id)))


def _require_answers_br(db: Session, br: BusinessRequirement, sol: Solution) -> None:
    """The BR-row rule (Q-3, Q-5): the tag must be a live solution of THIS BR. The pairing row is held FOR SHARE,
    so a concurrent BR_SOLUTION unlink waits (§2.3). The server never creates the pairing (Q-5)."""
    row = db.scalars(select(BrSolution).where(BrSolution.br_id == br.br_id, BrSolution.solution_id == sol.solution_id)
                     .with_for_update(read=True, of=BrSolution)).one_or_none()
    if row is None or not row.is_active:
        raise HTTPException(422, f"{sol.solution_number} does not answer {br.br_number}. "
                                 "Add it to this requirement's solutions first.")


def _require_answers_some_br(db: Session, fr: FunctionRequirement, sol: Solution) -> None:
    """The register rule (Q-3): with live BR links, the tag must be a live solution of at least one of those BRs
    (that pairing held FOR SHARE, DR10b-S2). With none, any live solution of the project — `no_br` warns."""
    br_ids = _linked_br_ids(db, fr.fr_id)
    if not br_ids:
        return
    row = db.scalars(select(BrSolution).where(BrSolution.br_id.in_(br_ids), BrSolution.solution_id == sol.solution_id,
                                              BrSolution.is_active)
                     .order_by(BrSolution.br_solution_id).limit(1)
                     .with_for_update(read=True, of=BrSolution)).one_or_none()
    if row is None:
        numbers = ", ".join(db.scalars(select(BusinessRequirement.br_number)
                                       .where(BusinessRequirement.br_id.in_(br_ids))
                                       .order_by(BusinessRequirement.br_number)))
        raise HTTPException(422, f"{sol.solution_number} answers none of the requirements {fr.fr_number} serves "
                                 f"({numbers}). Add it to one of them first.")


def fr_solution_outside_its_brs(db: Session, project_id: int | None, fr_ids=None) -> list[dict]:
    """consistency_check WARNING line (slice10b §2.2, Q-4): live FRs with at least one live BR link whose solution
    tag is a live solution of none of those BRs. Shown, never freeze-blocking, never auto-cleared."""
    sql = """
        SELECT fr.fr_id, fr.fr_number, s.solution_number
        FROM   function_requirement fr
        JOIN   solution s ON s.solution_id = fr.solution_id
        WHERE  fr.is_active
          AND  EXISTS (SELECT 1 FROM br_function_requirement l JOIN business_requirement br ON br.br_id = l.br_id
                       WHERE l.fr_id = fr.fr_id AND l.is_active AND br.is_active)
          AND  NOT EXISTS (SELECT 1 FROM br_function_requirement l
                           JOIN business_requirement br ON br.br_id = l.br_id AND br.is_active
                           JOIN br_solution bs ON bs.br_id = l.br_id AND bs.solution_id = fr.solution_id
                                              AND bs.is_active
                           WHERE l.fr_id = fr.fr_id AND l.is_active)"""
    params: dict = {}
    if project_id is not None:
        sql += " AND fr.project_id = :p"
        params["p"] = project_id
    if fr_ids is not None:
        if not fr_ids:
            return []
        sql += " AND fr.fr_id = ANY(:ids)"
        params["ids"] = list(fr_ids)
    return [dict(r) for r in db.execute(text(sql + " ORDER BY fr.fr_number"), params).mappings()]


def brfr_under_inactive(db: Session, project_id: int | None) -> list[dict]:
    """consistency_check line (slice10b §2.3): live links whose BR or FR is retired. Must be empty — the proof that
    link_fr's lock order and FK_LIVENESS hold; it refuses the freeze like brsol_under_inactive."""
    q = (select(BrFunctionRequirement.br_function_requirement_id, BusinessRequirement.br_number,
                FunctionRequirement.fr_number)
         .join(BusinessRequirement, BusinessRequirement.br_id == BrFunctionRequirement.br_id)
         .join(FunctionRequirement, FunctionRequirement.fr_id == BrFunctionRequirement.fr_id)
         .where(BrFunctionRequirement.is_active, ~(BusinessRequirement.is_active & FunctionRequirement.is_active)))
    if project_id is not None:
        q = q.where(BrFunctionRequirement.project_id == project_id)
    return [{"br_function_requirement_id": i, "br_number": b, "fr_number": f}
            for i, b, f in db.execute(q.order_by(BrFunctionRequirement.br_function_requirement_id)).all()]


def drift_warnings(db: Session, fr_ids, include_no_br: bool = False) -> list[dict]:
    """The response warnings of §2.2: `[{"code": …, "frs": ["FR-0007"]}]`, naming the FRs an action affected.
    Computed after the action's flush, so they describe the state it leaves."""
    fr_ids = sorted(set(fr_ids))
    out = []
    outside = [r["fr_number"] for r in fr_solution_outside_its_brs(db, None, fr_ids)]
    if outside:
        out.append({"code": "fr_solution_outside_its_brs", "frs": outside})
    if include_no_br and fr_ids:
        loose = list(db.scalars(select(FunctionRequirement.fr_number).where(
            FunctionRequirement.fr_id.in_(fr_ids), FunctionRequirement.is_active,
            FunctionRequirement.fr_id.not_in(_live_links())).order_by(FunctionRequirement.fr_number)))
        if loose:
            out.append({"code": "no_br", "frs": loose})
    return out


def link_fr(db: Session, actor_id: int, br: BusinessRequirement, fr_id: int, coverage_note: str | None,
            commit: bool = True) -> tuple[BrFunctionRequirement, list[dict]]:
    """Link an FR to a BR (slice10b §1.2). Lock order (SR-5 extended): step → BR → FR, all FOR SHARE, then the
    liveness checks, then the pair's row FOR UPDATE through the full grain. A dead row is relinked (S1-7)."""
    fr = db.scalars(select(FunctionRequirement).where(FunctionRequirement.fr_id == fr_id,
                                                      FunctionRequirement.project_id == br.project_id)).one_or_none()
    if fr is None:                                         # DR1-S1: another project's FR is the same 404
        raise HTTPException(404, "Not found")
    lifecycle.lock_for_share(db, db.get(BfcNode, br.bfc_node_id))
    lifecycle.lock_for_share(db, br)
    lifecycle.lock_for_share(db, fr)
    for end in (br, fr):
        if not end.is_active:
            raise HTTPException(409, f"{lifecycle.label(end)} is retired. Restore it first.")
    row = db.scalars(select(BrFunctionRequirement).where(BrFunctionRequirement.br_id == br.br_id,
                                                         BrFunctionRequirement.fr_id == fr.fr_id)
                     .with_for_update(of=BrFunctionRequirement)).one_or_none()
    if row is None:
        row = BrFunctionRequirement(project_id=br.project_id, br_id=br.br_id, fr_id=fr.fr_id,
                                    coverage_note=coverage_note, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{br.br_number} is already linked to {fr.fr_number}")
    else:
        lifecycle.relink(db, actor_id, row, detail={"previous_coverage_note": row.coverage_note})
        row.coverage_note = coverage_note
    db.flush()
    warnings = drift_warnings(db, [fr.fr_id])              # Q-6: allowed, and the response says so
    if commit:
        db.commit()
        db.refresh(row)
    return row, warnings


def edit_link_note(db: Session, actor_id: int, row: BrFunctionRequirement, row_version: int,
                   coverage_note: str | None) -> BrFunctionRequirement:
    """S5-3: the note is corrected in place; the one it replaces stays in the audit trail."""
    lifecycle.lock(db, row)
    lifecycle.check_live(row, row_version)
    if coverage_note == row.coverage_note:
        return row
    previous = row.coverage_note
    row.coverage_note = coverage_note
    row.updated_by = actor_id
    audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=row.project_id,
                 target_table=row.__table__.name, target_id=row.br_function_requirement_id,
                 detail={"label": lifecycle.label(row), "previous_coverage_note": previous})
    db.commit()
    db.refresh(row)
    return row


def unlink_fr(db: Session, actor_id: int, row: BrFunctionRequirement, row_version: int) -> list[dict]:
    """Soft-unlink (law 1). The row is locked FOR UPDATE first (DR10b-S1); the FR is never locked here. The tag is
    never cleared (Q-4): the response names the FR if it now answers none of its BRs, or has no BR left."""
    lifecycle.lock(db, row)
    lifecycle.unlink(db, actor_id, row, row_version, commit=False)
    db.flush()
    warnings = drift_warnings(db, [row.fr_id], include_no_br=True)
    db.commit()
    return warnings


def _tag_warnings(fr: FunctionRequirement, sol: Solution | None) -> list[dict]:
    out = []
    if sol is not None and sol.category_code not in TECH_CATEGORIES:
        out.append({"code": "non_technology_solution", "frs": [fr.fr_number]})
    if sol is not None and sol.status_code == "REJECTED":
        out.append({"code": "rejected_solution", "frs": [fr.fr_number]})
    return out


def set_solution_from_br(db: Session, actor_id: int, br: BusinessRequirement, link: BrFunctionRequirement,
                         solution_id: int | None, fr_row_version: int) -> tuple[dict, list[dict]]:
    """PUT …/{link_id}/solution (slice10b §1.2, §2.1): set the FR's tag from this BR's row. Lock order: step → BR
    (FOR SHARE) → FR FOR UPDATE → the link FOR SHARE (live and on this FR, else 409, DR10b-S1) → solution FOR
    SHARE → the BR_SOLUTION pairing FOR SHARE. A solution that is not a live solution of THIS BR is 422."""
    fr = db.get(FunctionRequirement, link.fr_id)
    lifecycle.lock_for_share(db, db.get(BfcNode, br.bfc_node_id))
    lifecycle.lock_for_share(db, br)
    lifecycle.lock(db, fr)
    lifecycle.check_live(fr, fr_row_version)
    if not br.is_active:
        raise HTTPException(409, f"{lifecycle.label(br)} is retired. Restore it first.")
    lifecycle.lock_for_share(db, link)
    if not link.is_active or link.fr_id != fr.fr_id:
        raise HTTPException(409, f"{fr.fr_number} is no longer linked to {br.br_number}. Reload.")
    sol = _solution(db, fr.project_id, solution_id) if solution_id is not None else None
    if sol is not None:
        _require_answers_br(db, br, sol)
    previous = fr.solution_row.solution_number if fr.solution_row else None
    new_id = sol.solution_id if sol else None
    if new_id != fr.solution_id:
        fr.solution_id = new_id
        fr.updated_by = actor_id
        audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=fr.project_id,
                     target_table="function_requirement", target_id=fr.fr_id,
                     detail={"label": lifecycle.label(fr), "previous_solution_number": previous,
                             "from_br": br.br_number})
    db.flush()
    warnings = [*_tag_warnings(fr, sol), *drift_warnings(db, [fr.fr_id])]
    db.commit()
    return br_fr_row(db, link), warnings
