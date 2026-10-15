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
from services import audit, lifecycle
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
