"""Function requirements (§7.5, D-7/D-27/D-28). Spec: docs/slice6a_spec.md; schema:
docs/slice6a_schema.md. fr_number is minted at save; the type's behaviour is copied from the
resolved code and verified by fk_fr_type_code (D-27).

An FR may have no Solution (D-28): it saves with a warning. A Solution is always fetched scoped
to the FR's project first, then locked FOR SHARE and checked live (DR6a-S1, DR6a-D1) — the
solution.link pattern — so an FR can neither cross projects nor land under a retired Solution.
suggested_br_id (D-34) waits for the FR import (S6a-1). Complexity and effort wait for 6c (S6a-3)."""
import logging

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from models import BusinessRequirement, FunctionRequirement, Solution
from services import audit, interface, lifecycle, numbering
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
    if sol is None:
        out.append("no_solution")                          # D-28
    else:
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


def list_frs(db: Session, project_id: int, include_retired: bool = False,
             unlinked: bool = False) -> list[FunctionRequirement]:
    q = select(FunctionRequirement).where(FunctionRequirement.project_id == project_id)
    if not include_retired:
        q = q.where(FunctionRequirement.is_active)
    if unlinked:
        q = q.where(FunctionRequirement.solution_id.is_(None))
    return list(db.scalars(q.order_by(FunctionRequirement.fr_number)))


def frs_of_solution(db: Session, sol: Solution) -> list[FunctionRequirement]:
    return list(db.scalars(select(FunctionRequirement).where(
        FunctionRequirement.solution_id == sol.solution_id, FunctionRequirement.is_active)
        .order_by(FunctionRequirement.fr_number)))


def frs_of_br(db: Session, br: BusinessRequirement) -> list[dict]:
    """Derived through v_br_function_requirement, never stored (D-7). One row per (FR, solution)."""
    rows = db.execute(text("""
        SELECT v.fr_id, v.fr_number, fr.fr_name, ft.code AS fr_type_code, fr.fr_type_behaviour,
               v.solution_id, s.solution_number, s.solution_name
        FROM   v_br_function_requirement v
        JOIN   function_requirement fr ON fr.fr_id = v.fr_id
        JOIN   code_master ft          ON ft.code_id = fr.fr_type_code_id
        JOIN   solution s              ON s.solution_id = v.solution_id
        WHERE  v.br_id = :br AND v.project_id = :p
        ORDER  BY v.fr_number"""), {"br": br.br_id, "p": br.project_id}).mappings().all()
    return [dict(r) for r in rows]


def create_fr(db: Session, actor_id: int, project_id: int, name: str, fr_type_code: str,
              solution_id: int | None, fields: dict) -> tuple[FunctionRequirement, list[str]]:
    name = _name(name)
    ftype = _type(db, project_id, fr_type_code)
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
    warnings = _warnings(db, fr, sol)
    db.commit()
    db.refresh(fr)
    return fr, warnings


_UNSET = object()


def update_fr(db: Session, actor_id: int, fr: FunctionRequirement, row_version: int, fields: dict,
              fr_type_code: str | None, status_code: str | None,
              solution_id=_UNSET) -> tuple[FunctionRequirement, list[str]]:
    """`solution_id` is _UNSET when not sent, None to unlink, an id to (re)link."""
    lifecycle.lock(db, fr)                  # FOR UPDATE: a type change serialises with an interface PUT (sara 6b-2 L1)
    lifecycle.check_live(fr, row_version)
    before = {"previous_solution_number": fr.solution_row.solution_number if fr.solution_row else None,
              "previous_fr_type_code": fr.fr_type_code}
    sol = fr.solution_row
    if solution_id is not _UNSET:
        sol = _solution(db, fr.project_id, solution_id) if solution_id is not None else None
    if "fr_name" in fields:
        fields["fr_name"] = _name(fields["fr_name"])
    for k in EDITABLE:
        if k in fields:
            setattr(fr, k, fields[k])
    moved = solution_id is not _UNSET and (sol.solution_id if sol else None) != fr.solution_id
    retyped = False
    if moved:
        fr.solution_id = sol.solution_id if sol else None
    if fr_type_code is not None and fr_type_code != fr.fr_type_code:
        ftype = _type(db, fr.project_id, fr_type_code)
        if (fr.fr_type_behaviour == "INTERFACE" and ftype.behaviour_code != "INTERFACE"   # behaviour, not code
                and interface.live_detail_exists(db, fr.fr_id)):                         # criterion 102
            raise HTTPException(409, "This FR has interface detail. Remove it first, or keep an interface type")
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
    db.commit()
    db.refresh(fr)
    return fr, warnings


def fr_under_inactive_solution(db: Session, project_id: int | None) -> list[dict]:
    """consistency_check line (DR6a-D1): live FRs whose Solution is retired. Must be empty."""
    q = (select(FunctionRequirement.fr_id, FunctionRequirement.fr_number, Solution.solution_number)
         .join(Solution, Solution.solution_id == FunctionRequirement.solution_id)
         .where(FunctionRequirement.is_active, ~Solution.is_active))
    if project_id is not None:
        q = q.where(FunctionRequirement.project_id == project_id)
    return [{"fr_id": i, "fr_number": n, "solution_number": s}
            for i, n, s in db.execute(q.order_by(FunctionRequirement.fr_number)).all()]

