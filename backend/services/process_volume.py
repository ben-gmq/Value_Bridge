"""Process volume and FTE (D-67; docs/slice13_schema.md §3, VB_design `set_process_volume` / `derive_volume`).

One owner for the volume figures of a process and what they derive to. The figures are columns on `bfc_node`
(slice13_schema §3.1), written only by `set_volume`; hours and FTE are derived on every read by `derive`, never stored
and never accepted from a request body (VB law 6). All arithmetic is Decimal.

    annual_hours = runs × periods_per_year × transactions_per_run × seconds_per_transaction / 3600
    fte          = annual_hours / (working_days_per_year × hours_per_working_day)

DAY counts the project's working days (240 by default), not 365 [Q-27]; WEEK 52, MONTH 12, QUARTER 4, YEAR 1.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import BfcNode, Project
from services import area_match, audit, lifecycle
from services.code_master import resolve, validate_required_code

PERIODS = ("DAY", "WEEK", "MONTH", "QUARTER", "YEAR")                      # ck_bfc_volume_period
PERIODS_PER_YEAR = {"WEEK": 52, "MONTH": 12, "QUARTER": 4, "YEAR": 1}      # DAY: the project's working days
NUMBERS = ("runs_per_period", "transactions_per_run", "seconds_per_transaction")
# Service caps, not CHECKs, so they move without a migration; each type holds 1,000× more (§3.2, Q-21).
CAPS = {"runs_per_period": Decimal(1_000_000), "transactions_per_run": Decimal(100_000_000),
        "seconds_per_transaction": Decimal(86_400)}
SCALE = {"runs_per_period": 2, "transactions_per_run": 2, "seconds_per_transaction": 3}   # the columns' decimals
LABELS = {"runs_per_period": "How often it runs", "transactions_per_run": "Transactions per run",
          "seconds_per_transaction": "Time per transaction"}
FIELDS = ("runs_per_period", "volume_period_code", "transactions_per_run", "transaction_unit_code",
          "seconds_per_transaction")
NEEDED = ("runs_per_period", "volume_period_code", "transactions_per_run", "seconds_per_transaction")


def _number(name: str, v) -> Decimal | None:
    """A figure as stored: ≥ 0, under its cap, and with no more decimals than its column, so PostgreSQL never
    rounds what was typed (422 otherwise)."""
    if v is None:
        return None
    d = Decimal(str(v))
    if not d.is_finite():
        raise HTTPException(422, f"{LABELS[name]} must be a number")
    if d < 0:
        raise HTTPException(422, f"{LABELS[name]} cannot be negative")
    if d > CAPS[name]:
        raise HTTPException(422, f"{LABELS[name]} cannot be more than {CAPS[name]:,}")
    if d.as_tuple().exponent < -SCALE[name] and d != d.quantize(Decimal(1).scaleb(-SCALE[name])):
        raise HTTPException(422, f"{LABELS[name]} takes at most {SCALE[name]} decimals")
    return d.quantize(Decimal(1).scaleb(-SCALE[name]))


def figures(node: BfcNode) -> dict:
    """The stored figures, the unit as its code."""
    return {"runs_per_period": node.runs_per_period, "volume_period_code": node.volume_period_code,
            "transactions_per_run": node.transactions_per_run, "transaction_unit_code": node.transaction_unit_code,
            "seconds_per_transaction": node.seconds_per_transaction}


def _plain(f: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in f.items()}


def derive(f: dict, working_days_per_year: int, hours_per_working_day: Decimal) -> dict:
    """Hours and FTE from the figures and a basis (the project's, or a baseline header's — C6). A missing input
    gives both None and names it, never a guess (C3)."""
    missing = [k for k in NEEDED if f.get(k) is None]
    if missing:
        return {"annual_hours": None, "fte": None, "incomplete": missing}
    per_year = (Decimal(working_days_per_year) if f["volume_period_code"] == "DAY"
                else Decimal(PERIODS_PER_YEAR[f["volume_period_code"]]))
    hours = (Decimal(f["runs_per_period"]) * per_year * Decimal(f["transactions_per_run"])
             * Decimal(f["seconds_per_transaction"]) / Decimal(3600))
    fte = hours / (Decimal(working_days_per_year) * Decimal(hours_per_working_day))
    return {"annual_hours": hours, "fte": fte, "incomplete": []}


def read(db: Session, node: BfcNode) -> dict:
    """What the volume route returns: the figures, the unit's label in this project, the basis and the derivation."""
    project = db.get(Project, node.project_id)
    f = figures(node)
    unit_label = node.transaction_unit_row.label if node.transaction_unit_row is not None else None
    if f["transaction_unit_code"]:                       # a project override relabels the code (C8)
        for row in resolve(db, node.project_id, "TRANSACTION_UNIT"):
            if row.code == f["transaction_unit_code"]:
                unit_label = row.label
    return {"bfc_node_id": node.bfc_node_id, "row_version": node.row_version, "is_process": node.is_process,
            **f, "transaction_unit_label": unit_label,
            "working_days_per_year": project.working_days_per_year,
            "hours_per_working_day": project.hours_per_working_day,
            **derive(f, project.working_days_per_year, project.hours_per_working_day)}


def set_volume(db: Session, actor_id: int, node: BfcNode, row_version: int, sent: dict) -> BfcNode:
    """Set the figures named in `sent` (a key sent as null clears it); the others keep their value. Process nodes
    only, either chart (the route's guard asks AS_IS for an as-is node). Audited PROCESS_VOLUME_SET {from, to}."""
    lifecycle.lock_for_share(db, node)                      # serialised with a step retire, as set_performer
    lifecycle.check_live(node, row_version)
    if not node.is_process:
        raise HTTPException(422, "Only a process step has volume figures")
    before = figures(node)
    after = dict(before)
    for k in NUMBERS:
        if k in sent:
            after[k] = _number(k, sent[k])
    if "volume_period_code" in sent:
        p = sent["volume_period_code"]
        if p is not None and p not in PERIODS:
            raise HTTPException(422, f"volume_period_code: '{p}' is not one of {', '.join(PERIODS)}")
        after["volume_period_code"] = p
    unit_id = node.transaction_unit_code_id
    if "transaction_unit_code" in sent:
        code = sent["transaction_unit_code"]
        unit_id = (validate_required_code(db, node.project_id, "TRANSACTION_UNIT", code, "transaction_unit_code").code_id
                   if code else None)
        after["transaction_unit_code"] = code or None
    if (after["runs_per_period"] is None) != (after["volume_period_code"] is None):
        raise HTTPException(422, "How often it runs needs both a number and a period (for example 3 a week)")
    if unit_id is not None and after["transactions_per_run"] is None:
        raise HTTPException(422, "A unit needs the number of transactions per run")
    node.runs_per_period, node.volume_period_code = after["runs_per_period"], after["volume_period_code"]
    node.transactions_per_run, node.transaction_unit_code_id = after["transactions_per_run"], unit_id
    node.seconds_per_transaction = after["seconds_per_transaction"]
    node.updated_by = actor_id
    db.flush()
    audit.record(db, "PROCESS_VOLUME_SET", actor_id=actor_id, project_id=node.project_id, target_table="bfc_node",
                 target_id=node.bfc_node_id, detail={"from": _plain(before), "to": _plain(after)})
    db.commit()
    db.refresh(node)
    return node


# ---- the project's FTE basis (set_fte_basis, Q-7) ------------------------------------------------------------

def set_basis(db: Session, actor_id: int, project: Project, row_version: int, working_days_per_year: int,
              hours_per_working_day: Decimal) -> Project:
    """A project ADMIN setting (the route's guard), audited PROJECT_FTE_BASIS_CHANGED {from, to}. No process row
    changes: every FTE re-derives on its next read (C4). Ranges are the CHECKs' (422 before the database)."""
    if project.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if not 1 <= working_days_per_year <= 366:
        raise HTTPException(422, "Working days per year must be between 1 and 366")
    h = Decimal(str(hours_per_working_day))
    if not Decimal("0.25") <= h <= Decimal(24) or h != h.quantize(Decimal("0.01")):
        raise HTTPException(422, "Hours per working day must be between 0.25 and 24, to two decimals")
    before = {"working_days_per_year": project.working_days_per_year,
              "hours_per_working_day": str(project.hours_per_working_day)}
    after = {"working_days_per_year": working_days_per_year, "hours_per_working_day": str(h.quantize(Decimal("0.01")))}
    if before != after:
        project.working_days_per_year, project.hours_per_working_day = working_days_per_year, h
        project.updated_by = actor_id
        db.flush()
        audit.record(db, "PROJECT_FTE_BASIS_CHANGED", actor_id=actor_id, project_id=project.project_id,
                     target_table="project", target_id=project.project_id, detail={"from": before, "to": after})
    db.commit()
    db.refresh(project)
    return project


# ---- as-is beside to-be (volume_summary, Q-9, Q-28; slice13_schema §3.8) -----------------------------------

SETS = area_match.SETS


def _totals(processes: list[BfcNode], days: int, hpd: Decimal) -> dict:
    hours = Decimal(0)
    complete, incomplete = 0, []
    for p in processes:
        d = derive(figures(p), days, hpd)
        if d["annual_hours"] is None:
            incomplete.append({"bfc_node_id": p.bfc_node_id, "hier_code": p.hier_code, "node_name": p.node_name,
                               "missing": d["incomplete"]})
        else:
            hours += d["annual_hours"]
            complete += 1
    return {"processes": len(processes), "complete": complete, "incomplete": incomplete,
            "annual_hours": hours, "fte": hours / (Decimal(days) * hpd)}


def summary(db: Session, project: Project) -> dict:
    """Per chart, annual hours and FTE per L1 and L2 area, summed over the processes below each area that have
    complete figures; the rest are counted and listed, never guessed (C7). As-is and to-be areas are paired only
    when level, chart code AND normalised name agree; anything else is listed unmatched with its reason and is
    never summed against the other side (Q-28, C9)."""
    from sqlalchemy import select
    days, hpd = project.working_days_per_year, project.hours_per_working_day
    nodes = db.scalars(select(BfcNode).where(BfcNode.project_id == project.project_id, BfcNode.is_active)).all()
    by_set = {s: [n for n in nodes if n.bfc_set_code == s] for s in SETS}
    areas = {}                                         # (set, level) → {hier_code: (area node, totals)}
    for s, ns in by_set.items():
        procs = [n for n in ns if n.is_process]
        for level in (1, 2):
            areas[(s, level)] = {
                a.hier_code: (a, _totals([p for p in procs if p.hier_code.startswith(a.hier_code + ".")], days, hpd))
                for a in ns if a.level_no == level and not a.is_process}
    out_levels = []
    for level in (1, 2):
        side = {s: areas[(s, level)] for s in SETS}
        pairs, loose = area_match.pair_areas({s: {code: a for code, (a, _) in side[s].items()} for s in SETS})
        matched = [{"hier_code": code, "as_is_name": a.node_name, "to_be_name": b.node_name,
                    "as_is": side["AS_IS"][code][1], "to_be": side["TO_BE"][code][1],
                    "saved_hours": side["AS_IS"][code][1]["annual_hours"] - side["TO_BE"][code][1]["annual_hours"],
                    "saved_fte": side["AS_IS"][code][1]["fte"] - side["TO_BE"][code][1]["fte"]}
                   for code, a, b in pairs]
        unmatched = [{**u, "totals": side[u["chart"]][u["hier_code"]][1]} for u in loose]
        out_levels.append({"level": level, "matched": matched, "unmatched": unmatched})
    return {"working_days_per_year": days, "hours_per_working_day": hpd, "levels": out_levels,
            "has_as_is": bool(by_set["AS_IS"])}
