"""System-to-system data flows on a BR (D-61, docs/slice11_schema.md §3; S11-3, S11-5).

A flow is a business statement — "what data entity we copy from which system to which system" — on a to-be BR. Both
ends come from the Applications master list and differ. Coverage by a function requirement is DERIVED, never stored:
a flow is covered when the same BR links a live interface-behaviour FR (an Interface or a Data migration FR alike,
S11-5 — branched on behaviour, law 5) whose interface has the same source and target and carries the entity.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (Application, BfcNode, BrDataEntity, BrFunctionRequirement, BrSystemFlow, BusinessRequirement,
                    DataEntity, FrInterface, FrInterfaceDataEntity, FunctionRequirement)
from services import audit, function_requirement as fr_service, interface, lifecycle
from services.application import is_as_is_only


def _lock_live_br(db: Session, br: BusinessRequirement) -> None:
    lifecycle.lock_for_share(db, db.get(BfcNode, br.bfc_node_id))    # SR-5: the step first, then the BR
    lifecycle.lock_for_share(db, br)
    if not br.is_active:
        raise HTTPException(409, f"{br.br_number} is retired. Restore it first.")


def _live_in_project(db: Session, model, row_id: int, project_id: int):
    row = db.get(model, row_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(422, f"No such {model.__tablename__.replace('_', ' ')} in this project")
    lifecycle.lock_for_share(db, row)                                # a retire waits for this write (SR-5)
    if not row.is_active:
        raise HTTPException(409, f"{lifecycle.label(row)} is retired. Restore it first.")
    return row


def list_flows(db: Session, br: BusinessRequirement) -> list[BrSystemFlow]:
    return list(db.scalars(select(BrSystemFlow).where(BrSystemFlow.br_id == br.br_id, BrSystemFlow.is_active)
                           .order_by(BrSystemFlow.br_system_flow_id)))


def coverage(db: Session, br: BusinessRequirement) -> dict[int, list[str]]:
    """flow id → the FR numbers that cover it (empty: "no interface yet"). Derived on every read (§3.1)."""
    flows = list_flows(db, br)
    if not flows:
        return {}
    rows = db.execute(
        select(FunctionRequirement.fr_number, FrInterface.source_application_id, FrInterface.target_application_id,
               FrInterfaceDataEntity.data_entity_id)
        .join(BrFunctionRequirement, BrFunctionRequirement.fr_id == FunctionRequirement.fr_id)
        .join(FrInterface, FrInterface.fr_id == FunctionRequirement.fr_id)
        .join(FrInterfaceDataEntity, FrInterfaceDataEntity.fr_id == FunctionRequirement.fr_id)
        .where(BrFunctionRequirement.br_id == br.br_id, BrFunctionRequirement.is_active,
               FunctionRequirement.is_active, FunctionRequirement.fr_type_behaviour == interface.INTERFACE,
               FrInterface.is_active, FrInterfaceDataEntity.is_active)).all()
    by_key: dict[tuple, list[str]] = {}
    for number, src, tgt, de in rows:
        by_key.setdefault((de, src, tgt), []).append(number)
    return {f.br_system_flow_id: sorted(by_key.get((f.data_entity_id, f.source_application_id,
                                                    f.target_application_id), [])) for f in flows}


def info(db: Session, br: BusinessRequirement, flow: BrSystemFlow) -> list[str]:
    """Information only, never a warning or a block: a flow of an entity the BR does not otherwise use (Q-12), and a
    flow to or from an application that exists in the as-is landscape only (§3.2)."""
    out = []
    if db.scalar(select(BrDataEntity.br_data_entity_id).where(
            BrDataEntity.br_id == br.br_id, BrDataEntity.data_entity_id == flow.data_entity_id,
            BrDataEntity.is_active).limit(1)) is None:
        out.append("flow_entity_not_used_by_br")
    if any(is_as_is_only(app) for app in (flow.source_row, flow.target_row)):
        out.append("flow_touches_as_is_only_application")
    return out


def add_flow(db: Session, actor_id: int, br: BusinessRequirement, data_entity_id: int, source_application_id: int,
             target_application_id: int, flow_note: str | None) -> BrSystemFlow:
    _lock_live_br(db, br)
    if source_application_id == target_application_id:
        raise HTTPException(422, "From and to must be different systems")
    for model, row_id in sorted(((DataEntity, data_entity_id), (Application, source_application_id),
                                 (Application, target_application_id)), key=lambda x: (x[0].__tablename__, x[1])):
        _live_in_project(db, model, row_id, br.project_id)
    row = db.scalars(select(BrSystemFlow).where(
        BrSystemFlow.br_id == br.br_id, BrSystemFlow.data_entity_id == data_entity_id,
        BrSystemFlow.source_application_id == source_application_id,
        BrSystemFlow.target_application_id == target_application_id)).one_or_none()
    if row is None:
        row = BrSystemFlow(project_id=br.project_id, br_id=br.br_id, data_entity_id=data_entity_id,
                           source_application_id=source_application_id, target_application_id=target_application_id,
                           flow_note=flow_note, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{br.br_number} already states that flow")
    else:                                                     # re-stating restores the same row (S1-7)
        lifecycle.relink(db, actor_id, row)
        if flow_note is not None:
            row.flow_note = flow_note
    db.commit()
    db.refresh(row)
    return row


def update_note(db: Session, actor_id: int, row: BrSystemFlow, row_version: int, flow_note: str | None) -> BrSystemFlow:
    lifecycle.check_live(row, row_version)
    if row.flow_note != flow_note:                            # sara L4: audited like the other link-note edits
        audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=row.project_id, target_table="br_system_flow",
                     target_id=row.br_system_flow_id,
                     detail={"label": lifecycle.label(row), "previous_flow_note": row.flow_note})
    row.flow_note, row.updated_by = flow_note, actor_id
    db.commit()
    db.refresh(row)
    return row


def seed_interface_fr(db: Session, actor_id: int, br: BusinessRequirement, flow_ids: list[int], fr_type_code: str,
                      fr_name: str) -> tuple[FunctionRequirement, list]:
    """"Create interface FR from these flows" (§3.1): one or more of the BR's live flows with ONE (source, target)
    pair, else 422. One transaction: the FR (an interface-behaviour type — Interface or Data migration, S11-5), its
    interface (source, target), one carried entity per flow entity, and the BR ↔ FR link; numbers minted at save."""
    _lock_live_br(db, br)
    if not flow_ids or len(set(flow_ids)) != len(flow_ids):
        raise HTTPException(422, "Pick one or more flows, each once")
    flows = []
    for fid in sorted(flow_ids):
        f = db.get(BrSystemFlow, fid)
        if f is None or f.br_id != br.br_id or not f.is_active:
            raise HTTPException(404, "Not found")
        flows.append(f)
    pairs = {(f.source_application_id, f.target_application_id) for f in flows}
    if len(pairs) != 1:
        raise HTTPException(422, "The flows must share one from and one to system")
    (src, tgt), = pairs
    for model, row_id in sorted([(Application, src), (Application, tgt)] +
                                [(DataEntity, f.data_entity_id) for f in flows],
                                key=lambda x: (x[0].__tablename__, x[1])):
        _live_in_project(db, model, row_id, br.project_id)
    ftype = fr_service.fr_type(db, br.project_id, fr_type_code)
    if ftype.behaviour_code != interface.INTERFACE:
        raise HTTPException(422, "Pick an interface-behaviour type (Interface or Data migration)")
    fr, warnings = fr_service.create_fr(db, actor_id, br.project_id, fr_name, fr_type_code, None, {},
                                        br_id=br.br_id, commit=False)
    interface.create_detail(db, actor_id, fr, src, tgt, {f.data_entity_id: f.flow_note for f in flows})
    db.commit()
    db.refresh(fr)
    return fr, warnings                                       # sara L6: e.g. a duplicate name, as on the FR screen
