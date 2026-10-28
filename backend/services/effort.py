"""Rate card and FR effort days (§4.8, §7.13, D-13, A-38, R2-D7). Spec: docs/slice6c_spec.md; schema:
docs/slice6c_schema.md.

`rate_for` is the only reader of a rate. Effort days are always copied from the card at the moment an FR
is rated, never typed; a card change never reprices a rated FR (A-38) — instead every cell carries a
standing count of the FRs not at its current rate, visible to reviewers (S6c-5, DR6c-P1)."""
import getpass
import logging
import socket
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import BrFunctionRequirement, CodeMaster, EffortRate, FunctionRequirement, Solution
from seeds.ftc_rate_card import FTC_DEFAULT_RATE_CARD
from services import audit, components, errors, lifecycle
from services.code_master import resolve, validate_required_code

log = logging.getLogger("vb")

MAX_DAYS = Decimal("99999.99")            # numeric(7,2) (DR6c-D3)
HIGH_DAYS = Decimal("60")                 # needs confirmation, flagged on the card (S6c-7)


def rate_for(db: Session, project_id: int, fr_type_code_id: int, complexity_code_id: int,
             lock: bool = True) -> EffortRate | None:
    q = select(EffortRate).where(EffortRate.project_id == project_id, EffortRate.fr_type_code_id == fr_type_code_id,
                                 EffortRate.complexity_code_id == complexity_code_id, EffortRate.is_active)
    if lock:
        q = q.with_for_update(read=True, of=EffortRate)
    return db.scalars(q).one_or_none()


def _no_cell(db: Session, type_code_id: int, complexity_code_id: int) -> HTTPException:
    t, c = db.get(CodeMaster, type_code_id), db.get(CodeMaster, complexity_code_id)
    return HTTPException(422, f"No rate card entry for {t.label} × {c.label}")          # criterion 104


# ---- seeding ------------------------------------------------------------------------------------
def seed_rate_card(db: Session, project_id: int, actor_id: int, only_missing: bool = False) -> dict:
    """One cell per resolved (type × complexity) in the FTC default. No commit (create_project owns it).
    A default key that does not resolve is logged and counted, never silently dropped (DR6c-D5)."""
    types = {c.code: c for c in resolve(db, project_id, "FR_TYPE")}
    cxs = {c.code: c for c in resolve(db, project_id, "FR_COMPLEXITY")}
    have = set()
    if only_missing:
        have = set(db.execute(select(EffortRate.fr_type_code_id, EffortRate.complexity_code_id).where(
            EffortRate.project_id == project_id)).all())
    seeded, unresolved = 0, []
    for (tcode, ccode), days in sorted(FTC_DEFAULT_RATE_CARD.items()):
        t, c = types.get(tcode), cxs.get(ccode)
        if t is None or c is None:
            unresolved.append(f"{tcode}×{ccode}")
            continue
        if (t.code_id, c.code_id) in have:
            continue
        db.add(EffortRate(project_id=project_id, fr_type_code_id=t.code_id, complexity_code_id=c.code_id,
                          standard_days=days, created_by=actor_id))
        seeded += 1
    if unresolved:
        log.error("rate card default keys did not resolve for project %s: %s", project_id, unresolved)
    db.flush()
    return {"rate_cells_seeded": seeded, "rate_cells_unresolved": unresolved}


def backfill(db: Session, actor_email: str) -> list[dict]:
    """CLI: fill missing cells in every project, one transaction and one audit event per project.
    The actor must be an active platform admin; the OS user and host are recorded (DR6c-S1)."""
    from models import AppUser, Project
    actor = db.scalars(select(AppUser).where(func.lower(AppUser.email) == actor_email.strip().lower())).one_or_none()
    if actor is None or not actor.is_active or not actor.is_platform_admin:
        raise SystemExit("--actor-email must be an active platform admin")
    out = []
    for p in db.scalars(select(Project).order_by(Project.project_id)).all():
        result = seed_rate_card(db, p.project_id, actor.app_user_id, only_missing=True)
        if result["rate_cells_seeded"] or result["rate_cells_unresolved"]:                  # sara L-6
            audit.record(db, "RATE_CARD_SEEDED", actor_id=actor.app_user_id, project_id=p.project_id,
                         detail={**result, "os_user": getpass.getuser(), "host": socket.gethostname()})
        db.commit()
        out.append({"project_id": p.project_id, **result})
    return out


# ---- reading the card ---------------------------------------------------------------------------
def _off_rate(db: Session, project_id: int) -> dict[tuple[int, int], tuple[int, Decimal]]:
    """Per cell: live rated FRs whose effort_days ≠ the cell's current rate (S6c-5)."""
    rows = db.execute(select(EffortRate.fr_type_code_id, EffortRate.complexity_code_id, func.count(),
                             func.coalesce(func.sum(FunctionRequirement.effort_days), 0)).join(
        FunctionRequirement, (FunctionRequirement.project_id == EffortRate.project_id)
        & (FunctionRequirement.fr_type_code_id == EffortRate.fr_type_code_id)
        & (FunctionRequirement.complexity_code_id == EffortRate.complexity_code_id)).where(
        EffortRate.project_id == project_id, EffortRate.is_active, FunctionRequirement.is_active,
        FunctionRequirement.effort_days != EffortRate.standard_days).group_by(
        EffortRate.fr_type_code_id, EffortRate.complexity_code_id)).all()
    return {(t, c): (n, d) for t, c, n, d in rows}


def read_card(db: Session, project_id: int) -> dict:
    types, cxs = resolve(db, project_id, "FR_TYPE"), resolve(db, project_id, "FR_COMPLEXITY")
    cells = {(r.fr_type_code_id, r.complexity_code_id): r for r in db.scalars(select(EffortRate).where(
        EffortRate.project_id == project_id, EffortRate.is_active))}
    off = _off_rate(db, project_id)
    out = []
    for t in types:
        for c in cxs:
            r = cells.get((t.code_id, c.code_id))
            n, d = off.get((t.code_id, c.code_id), (0, Decimal(0)))
            out.append({"fr_type_code": t.code, "fr_type_label": t.label, "complexity_code": c.code,
                        "complexity_label": c.label, "effort_rate_id": r.effort_rate_id if r else None,
                        "standard_days": r.standard_days if r else None, "row_version": r.row_version if r else None,
                        "change_rationale": r.change_rationale if r else None,
                        "updated_at": r.updated_at if r else None,
                        "unconfirmed_default": bool(r and r.row_version == 1 and r.change_rationale is None),
                        "high": bool(r and r.standard_days > HIGH_DAYS),
                        "not_at_current_rate": n, "not_at_current_rate_days": d})
    return {"complexities": [{"code": c.code, "label": c.label} for c in cxs],
            "types": [{"code": t.code, "label": t.label} for t in types], "cells": out}


# ---- changing the card --------------------------------------------------------------------------
def _days(value) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, "standard_days must be a number")
    if not d.is_finite() or d <= 0 or d > MAX_DAYS:                                       # DR6c-D3/D4
        raise HTTPException(422, "standard_days must be more than 0 and at most 99,999.99")
    if d != d.quantize(Decimal("0.01")):                                                    # "2.500" is fine (sara L-5)
        raise HTTPException(422, "standard_days has at most two decimals")                 # apple Q-6
    return d


def maintain_card(db: Session, actor_id: int, project_id: int, rationale: str | None, cells: list,
                  confirm_high: bool = False) -> dict:
    """One transaction; cells in (type code_id, complexity code_id) order (DR6c-P5); no FR repriced."""
    reason = (rationale or "").strip()
    if not reason:
        raise HTTPException(422, "Changing the rate card is a commercial decision and needs a reason")   # 125
    resolved = []
    for cell in cells:
        t = validate_required_code(db, project_id, "FR_TYPE", cell.fr_type_code, "fr_type_code")
        c = validate_required_code(db, project_id, "FR_COMPLEXITY", cell.complexity_code, "complexity_code")
        resolved.append((t, c, _days(cell.standard_days), cell.row_version))
    keys = [(t.code_id, c.code_id) for t, c, _, _ in resolved]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, "A cell is listed twice")
    if not confirm_high and any(d > HIGH_DAYS for _, _, d, _ in resolved):                  # S6c-7
        raise HTTPException(422, "A rate above 60 man-days needs confirming. Check it and confirm.")
    changes = []
    for t, c, days, rv in sorted(resolved, key=lambda x: (x[0].code_id, x[1].code_id)):
        row = db.scalars(select(EffortRate).where(
            EffortRate.project_id == project_id, EffortRate.fr_type_code_id == t.code_id,
            EffortRate.complexity_code_id == c.code_id).with_for_update(of=EffortRate)).one_or_none()
        if row is None:
            if rv is not None:
                raise HTTPException(409, errors.CONFLICT, headers=errors.STALE_HEADERS)
            row = EffortRate(project_id=project_id, fr_type_code_id=t.code_id, complexity_code_id=c.code_id,
                             standard_days=days, change_rationale=reason, created_by=actor_id)
            db.add(row)
            db.flush()
            changes.append((row, t, c, None, days))
            continue
        if rv is None or row.row_version != rv:
            raise HTTPException(409, errors.CONFLICT, headers=errors.STALE_HEADERS)
        if row.standard_days == days:
            continue                                                                         # unchanged: nothing
        old = row.standard_days
        row.standard_days, row.change_rationale, row.updated_by = days, reason, actor_id
        db.flush()
        changes.append((row, t, c, old, days))
    off = _off_rate(db, project_id)
    lines = [{"effort_rate_id": r.effort_rate_id, "fr_type_code": t.code, "complexity_code": c.code,
              "from": str(old) if old is not None else None, "to": str(new),
              "not_at_current_rate": off.get((t.code_id, c.code_id), (0, 0))[0]}
             for r, t, c, old, new in changes]
    if lines:
        audit.record(db, "RATE_CARD_CHANGED", actor_id=actor_id, project_id=project_id,
                     detail={"changes": lines, "change_rationale": reason})
    db.commit()
    return {"changes": lines}


# ---- rating an FR -------------------------------------------------------------------------------
def rate_fr(db: Session, actor_id: int, fr: FunctionRequirement, row_version: int, complexity_code: str | None,
            commit: bool = True) -> FunctionRequirement:
    components.require_on(db, fr.project_id, "EFFORT")          # S1: the screen and the import share the check
    lifecycle.lock(db, fr)                                      # lock, then check (DR6c-D2)
    lifecycle.check_live(fr, row_version)
    if not fr.fr_type_code_row.is_active:
        raise HTTPException(409, f"The FR type {fr.fr_type_code_row.label} is retired. Change the type first.")
    if complexity_code is None and fr.complexity_code_id is None:
        return fr                                                                           # nothing to change (sara L-3)
    before = {"previous_complexity_code": fr.complexity_code,
              "previous_effort_days": str(fr.effort_days) if fr.effort_days is not None else None}
    if complexity_code is None:
        fr.complexity_code_id, fr.effort_days = None, None                                   # apple Q-10
        rate = None
    else:
        cx = validate_required_code(db, fr.project_id, "FR_COMPLEXITY", complexity_code, "complexity_code")
        rate = rate_for(db, fr.project_id, fr.fr_type_code_id, cx.code_id)
        if rate is None:
            raise _no_cell(db, fr.fr_type_code_id, cx.code_id)
        if (fr.complexity_code_id, fr.effort_days) == (cx.code_id, rate.standard_days):
            return fr                                                                       # already at this rate (L-3)
        fr.complexity_code_id, fr.effort_days = cx.code_id, rate.standard_days                # together (D-13)
    fr.updated_by = actor_id
    audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=fr.project_id,
                 target_table="function_requirement", target_id=fr.fr_id,
                 detail={"label": lifecycle.label(fr), **before,
                         "effort_rate_id": rate.effort_rate_id if rate else None,
                         "rate_row_version": rate.row_version if rate else None})
    db.flush()
    if not commit:                                              # slice 1e: an import writes more in this transaction
        return fr
    db.commit()
    db.refresh(fr)
    return fr


def rederive_on_type_change(db: Session, fr: FunctionRequirement, new_type_code_id: int) -> tuple | None:
    """Inside update_fr: a rated FR takes the new type's current rate; no cell → 422 (whole PATCH).
    Returns (old_days, new_days) when the days moved, so the caller can say so (DR6c-P2)."""
    if fr.complexity_code_id is None:
        return None
    rate = rate_for(db, fr.project_id, new_type_code_id, fr.complexity_code_id)
    if rate is None:
        raise _no_cell(db, new_type_code_id, fr.complexity_code_id)
    old = fr.effort_days
    fr.effort_days = rate.standard_days
    return (old, rate.standard_days) if old != rate.standard_days else None


# ---- the summary --------------------------------------------------------------------------------
def summary(db: Session, project_id: int) -> dict:
    """Live FRs. Headline excludes FRs under REJECTED solutions (S6c-8); types grouped by code_id with the
    label from the code row, so a retired type still shows (DR6c-D5)."""
    rejected = select(Solution.solution_id).join(CodeMaster, CodeMaster.code_id == Solution.status_code_id).where(
        Solution.project_id == project_id, CodeMaster.code == "REJECTED")
    base = select(FunctionRequirement).where(FunctionRequirement.project_id == project_id, FunctionRequirement.is_active)
    frs = list(db.scalars(base))
    rej_ids = set(db.scalars(rejected))
    sols = {s.solution_id: s for s in db.scalars(select(Solution).where(Solution.project_id == project_id))}
    unconfirmed = {(r.fr_type_code_id, r.complexity_code_id) for r in db.scalars(select(EffortRate).where(
        EffortRate.project_id == project_id, EffortRate.is_active, EffortRate.row_version == 1,
        EffortRate.change_rationale.is_(None)))}
    head = [f for f in frs if f.solution_id not in rej_ids]
    current = {(r.fr_type_code_id, r.complexity_code_id): r.standard_days for r in db.scalars(select(EffortRate).where(
        EffortRate.project_id == project_id, EffortRate.is_active))}
    off_head = [f for f in head if f.effort_days is not None
                and current.get((f.fr_type_code_id, f.complexity_code_id), f.effort_days) != f.effort_days]
    rej = [f for f in frs if f.solution_id in rej_ids]
    # slice10b §6.4 [Q-18]: information only — every live FR with no live BR link. Never added
    # into a total, and effort is never summed by BR (an FR serving three BRs would count three times).
    traced = set(db.scalars(select(BrFunctionRequirement.fr_id).where(
        BrFunctionRequirement.project_id == project_id, BrFunctionRequirement.is_active)))
    untraced = [f for f in frs if f.fr_id not in traced]

    def total(rows):
        return sum((f.effort_days for f in rows if f.effort_days is not None), Decimal(0))
    by_type: dict = {}
    by_sol: dict = {}
    for f in head:
        if f.effort_days is None:
            continue
        k = f.fr_type_code_id
        e = by_type.setdefault(k, {"fr_type_code": f.fr_type_code_row.code, "fr_type_label": f.fr_type_code_row.label,
                                   "count": 0, "days": Decimal(0)})
        e["count"] += 1
        e["days"] += f.effort_days
        s = sols.get(f.solution_id)
        e2 = by_sol.setdefault(f.solution_id, {"solution_id": f.solution_id,
                                               "solution_number": s.solution_number if s else None,
                                               "solution_name": s.solution_name if s else None, "count": 0, "days": Decimal(0)})
        e2["count"] += 1
        e2["days"] += f.effort_days
    return {
        "total_days": total(head), "rated_count": sum(1 for f in head if f.effort_days is not None),
        "unrated_count": sum(1 for f in head if f.effort_days is None),
        "by_type": sorted(by_type.values(), key=lambda e: e["fr_type_code"]),
        "by_solution": sorted(by_sol.values(), key=lambda e: (e["solution_number"] is None, e["solution_number"] or "")),
        "rejected": {"count": len(rej), "days": total(rej)},
        "on_unconfirmed_default": sum(1 for f in head if f.effort_days is not None
                                      and (f.fr_type_code_id, f.complexity_code_id) in unconfirmed),
        # Same basis as the headline total (sara L-1): FRs under rejected solutions are reported apart.
        "not_at_current_rate": {"count": len(off_head), "days": sum((f.effort_days for f in off_head), Decimal(0))},
        "untraced": {"count": len(untraced), "days": total(untraced)},
    }
