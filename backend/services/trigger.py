"""Time and event triggers (D-49, slice7_schema §9.5): a project catalogue ("Month-end close") and the
links that say which processes it starts. The catalogue is shared by both charts and is writable while
either DFD component is on; a link belongs to its step's chart and retires and restores with the step
(step_retire.OWNED_BY_STEP)."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import BfcNode, BfcNodeTrigger, ProcessTrigger
from services import audit, components, lifecycle

KINDS = ("TIME", "EVENT")


def require_any_dfd(db: Session, project_id: int) -> None:
    """The catalogue serves both charts: either DFD component on (DR7-D1 any-of)."""
    on = components.enabled(db, project_id, lock=True)
    if not {"TO_BE_DFD", "AS_IS"} & on:
        components.require_on(db, project_id, "TO_BE_DFD")          # raises the standard 409


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


def _check(kind: str, schedule_note: str | None) -> None:
    if kind not in KINDS:
        raise HTTPException(400, f"trigger_kind: '{kind}' is not one of TIME, EVENT")
    if schedule_note and kind != "TIME":
        raise HTTPException(422, "Only a time trigger has a schedule")


def _name_free(db: Session, project_id: int, name: str, except_id: int | None = None) -> None:
    clash = db.scalars(select(ProcessTrigger).where(
        ProcessTrigger.project_id == project_id, ProcessTrigger.is_active,
        func.lower(func.btrim(ProcessTrigger.trigger_name)) == name.strip().lower())).first()
    if clash is not None and clash.process_trigger_id != except_id:
        raise HTTPException(409, f"A trigger called '{clash.trigger_name}' already exists")


def list_triggers(db: Session, project_id: int, include_retired: bool = False) -> list[ProcessTrigger]:
    q = select(ProcessTrigger).where(ProcessTrigger.project_id == project_id)
    if not include_retired:
        q = q.where(ProcessTrigger.is_active)
    return list(db.scalars(q.order_by(func.lower(ProcessTrigger.trigger_name))))


def create_trigger(db: Session, actor_id: int, project_id: int, name: str, kind: str,
                   schedule_note: str | None, description: str | None, commit: bool = True) -> ProcessTrigger:
    """`commit=False` (slice 1e-b): the flow import's form — flush only, the pipeline owns the transaction."""
    require_any_dfd(db, project_id)
    name = (name or "").strip()
    if not name:
        raise HTTPException(422, "Name the trigger")
    _check(kind, _clean(schedule_note))
    _name_free(db, project_id, name)
    row = ProcessTrigger(project_id=project_id, trigger_name=name, trigger_kind=kind,
                         schedule_note=_clean(schedule_note), description=_clean(description), created_by=actor_id)
    db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()
    return row


def update_trigger(db: Session, actor_id: int, row: ProcessTrigger, row_version: int, fields: dict) -> ProcessTrigger:
    require_any_dfd(db, row.project_id)
    lifecycle.check_live(row, row_version)
    if "trigger_name" in fields:
        name = (fields["trigger_name"] or "").strip()
        if not name:
            raise HTTPException(422, "Name the trigger")
        _name_free(db, row.project_id, name, except_id=row.process_trigger_id)
        row.trigger_name = name
    kind = fields.get("trigger_kind", row.trigger_kind)
    note = _clean(fields["schedule_note"]) if "schedule_note" in fields else row.schedule_note
    if kind == "EVENT" and "schedule_note" not in fields:
        note = None                                   # turning a time trigger into an event drops its schedule
    _check(kind, note)
    row.trigger_kind, row.schedule_note = kind, note
    if "description" in fields:
        row.description = _clean(fields["description"])
    row.updated_by = actor_id
    db.commit()
    return row


def retire_trigger(db: Session, actor_id: int, row: ProcessTrigger, row_version: int) -> None:
    """Refused while a live step names it (R2-D2): unlink it from those steps first."""
    require_any_dfd(db, row.project_id)
    lifecycle.retire(db, actor_id, row, row_version)


def restore_trigger(db: Session, actor_id: int, row: ProcessTrigger) -> ProcessTrigger:
    """sara 7c L6: refused with a clear 409 when a live trigger now holds its name."""
    require_any_dfd(db, row.project_id)
    lifecycle.restore(db, actor_id, row, before_activate=lambda r: _name_free(db, r.project_id, r.trigger_name,
                                                                                except_id=r.process_trigger_id))
    return row


def list_links(db: Session, node: BfcNode) -> list[BfcNodeTrigger]:
    return list(db.scalars(select(BfcNodeTrigger).where(BfcNodeTrigger.bfc_node_id == node.bfc_node_id,
                                                        BfcNodeTrigger.is_active)
                           .order_by(BfcNodeTrigger.bfc_node_trigger_id)))


def link(db: Session, actor_id: int, node: BfcNode, process_trigger_id: int, note: str | None,
         commit: bool = True) -> BfcNodeTrigger:
    """Re-linking restores the same row (full grain UK, S1-7). Serialised with a step retire (SR-5).
    `commit=False` (slice 1e-b): the flow import's form — flush only."""
    lifecycle.lock_for_share(db, node)
    if not (node.is_active and node.is_process):
        raise HTTPException(422, "A trigger starts a process step only")
    trig = db.get(ProcessTrigger, process_trigger_id)
    if trig is None or trig.project_id != node.project_id or not trig.is_active:
        raise HTTPException(422, "Choose an active trigger in this project")
    row = db.scalars(select(BfcNodeTrigger).where(BfcNodeTrigger.bfc_node_id == node.bfc_node_id,
                                                  BfcNodeTrigger.process_trigger_id == process_trigger_id)).one_or_none()
    if row is None:
        row = BfcNodeTrigger(project_id=node.project_id, bfc_node_id=node.bfc_node_id,
                             process_trigger_id=process_trigger_id, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"'{trig.trigger_name}' already starts this step")
    else:
        lifecycle.relink(db, actor_id, row)
    row.note = _clean(note)
    db.flush()
    audit.record(db, "STEP_TRIGGER_LINKED", actor_id=actor_id, project_id=node.project_id,
                 target_table="bfc_node_trigger", target_id=row.bfc_node_trigger_id,
                 detail={"bfc_node_id": node.bfc_node_id, "process_trigger_id": process_trigger_id})
    if commit:
        db.commit()
        db.refresh(row)
    return row


def unlink(db: Session, actor_id: int, row: BfcNodeTrigger, row_version: int, commit: bool = True) -> None:
    """`commit=False` (slice 1e-b piece b): the flow import's replace mode — flush only."""
    lifecycle.unlink(db, actor_id, row, row_version, commit=commit)
    if not commit:
        db.flush()
