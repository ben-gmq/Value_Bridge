"""Start one chart from the other (D-47, slice7_schema §9.3(3), Q-24): a whole-tree copy into an EMPTY
set, preview then confirm, one transaction, one BFC_SET_COPIED audit event carrying the old → new id
map. No provenance column: a to-be process may merge or split as-is ones.

Copied: nodes (name, level, seq, is_process, purpose, description) with fresh ids and the same codes;
the performer; step I/O, external flows, trigger links and the process's RACI. To-be → as-is also carries
the supporting systems (as-is facts); as-is → to-be mints a new DRAFT BR per process (D-2) and never
copies systems (to-be systems come from solutions). BR CRUD, solutions and FRs are never copied.

RACI changes home with the chart (D-64, slice10d Q-4): an as-is process's roles are its step's, a to-be
process's are its BR's. So as-is → to-be copies step roles into the new BR's roles, and to-be → as-is copies
each live BR's roles onto the new as-is step. The preview key `step_roles` counts the rows copied."""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (ApplicationBfcNode, BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeOrgRole,
                    BfcNodeTrigger, BrOrgRole, BusinessRequirement)
from services import audit, bfc, business_requirement, components

MAX_PROCESSES = 2000                                   # A-35, synchronous
NODE_FIELDS = ("level_no", "seq_no", "hier_code", "node_name", "is_process", "purpose_desc",
               "data_processing_desc", "performer_kind", "performer_org_unit_id", "performer_org_role_id",
               "performer_application_id", "performer_label",
               # D-67 [Q-23]: the to-be starts as "same as today"; the consultant lowers what the change saves
               "runs_per_period", "volume_period_code", "transactions_per_run", "transaction_unit_code_id",
               "seconds_per_transaction")


def _live(db: Session, project_id: int, bfc_set: str) -> list[BfcNode]:
    return list(db.scalars(select(BfcNode).where(BfcNode.project_id == project_id, BfcNode.is_active,
                                                 BfcNode.bfc_set_code == bfc_set)
                           .order_by(BfcNode.level_no, BfcNode.hier_code)))


def _owned(db: Session, model, ids: list[int]) -> list:
    return list(db.scalars(select(model).where(model.bfc_node_id.in_(ids), model.is_active)
                           .order_by(model.__mapper__.primary_key[0]))) if ids else []


def _roles(db: Session, from_set: str, ids: list[int]) -> list[tuple[int, object]]:
    """(source step id, role row) for every live RACI row of the source chart's processes, from its home:
    the step's own rows on the as-is chart, the live BR's rows on the to-be chart (D-64)."""
    if from_set == "AS_IS":
        return [(r.bfc_node_id, r) for r in _owned(db, BfcNodeOrgRole, ids)]
    if not ids:
        return []
    return list(db.execute(select(BusinessRequirement.bfc_node_id, BrOrgRole)
                           .join(BusinessRequirement, BusinessRequirement.br_id == BrOrgRole.br_id)
                           .where(BusinessRequirement.bfc_node_id.in_(ids), BusinessRequirement.is_active,
                                  BrOrgRole.is_active)
                           .order_by(BrOrgRole.br_org_role_id)).tuples())


def copy_set(db: Session, actor_id: int, project_id: int, to_set: str, from_set: str,
             confirm_hash: str | None) -> dict:
    bfc.check_set(to_set), bfc.check_set(from_set)
    if to_set == from_set:
        raise HTTPException(422, "Copy from the other chart")
    components.require_on(db, project_id, "AS_IS")                  # route guard too; serialises a switch-off
    src = _live(db, project_id, from_set)
    if not src:
        raise HTTPException(422, "The chart to copy from is empty")
    if _live(db, project_id, to_set):
        raise HTTPException(409, "The chart to copy into already has nodes. A copy starts an empty chart only")
    processes = [n for n in src if n.is_process]
    if len(processes) > MAX_PROCESSES:
        raise HTTPException(422, f"At most {MAX_PROCESSES} process steps are copied at once")
    ids = [n.bfc_node_id for n in src]
    io, ext, trg = (_owned(db, m, ids) for m in (BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeTrigger))
    roles = _roles(db, from_set, ids)
    apps = _owned(db, ApplicationBfcNode, ids) if to_set == "AS_IS" else []
    preview = {"from": from_set, "to": to_set, "nodes": len(src), "processes": len(processes),
               "step_data": len(io), "external_flows": len(ext), "triggers": len(trg), "step_roles": len(roles),
               "supporting_systems": len(apps), "new_requirements": len(processes) if to_set == "TO_BE" else 0}
    versions = sorted([r.__table__.name, r.__mapper__.primary_key_from_instance(r)[0], r.row_version]
                      for r in (*src, *io, *ext, *trg, *(r for _, r in roles), *apps))
    h = hashlib.sha256(json.dumps({"preview": preview, "rows": versions}, sort_keys=True).encode()).hexdigest()
    if confirm_hash is None:
        return {**preview, "confirm_hash": h, "applied": False}
    if confirm_hash != h:
        raise HTTPException(409, "The chart changed since the preview. Review it again")
    # sara 7c L2: one copy at a time per project; a second confirm waits, then finds the target non-empty.
    db.execute(select(func.pg_advisory_xact_lock(project_id)))
    if _live(db, project_id, to_set):
        raise HTTPException(409, "The chart to copy into already has nodes. A copy starts an empty chart only")
    # DR7-P2 (sara 7c M1): the rows this copy makes live must belong to components that are on.
    components.require_on(db, project_id, components.needed_for_rows([*src, *ext, *trg, *apps], to_set))

    id_map: dict[int, int] = {}
    new_brs: dict[int, int] = {}                      # new to-be step id → its new BR id
    for n in src:                                     # level order: a parent is always copied first
        new = BfcNode(project_id=project_id, bfc_set_code=to_set, created_by=actor_id,
                      parent_bfc_node_id=id_map.get(n.parent_bfc_node_id),
                      **{f: getattr(n, f) for f in NODE_FIELDS})
        db.add(new)
        db.flush()
        id_map[n.bfc_node_id] = new.bfc_node_id
        if new.is_process and to_set == "TO_BE":
            new_brs[new.bfc_node_id] = business_requirement.create_br(db, actor_id, new).br_id   # D-2
    for r in io:                                      # step I/O before the external flows it licenses
        db.add(BfcNodeDataEntity(project_id=project_id, bfc_node_id=id_map[r.bfc_node_id],
                                 data_entity_id=r.data_entity_id, direction=r.direction, note=r.note,
                                 created_by=actor_id))
    db.flush()
    for r in ext:
        db.add(BfcNodeExternalFlow(project_id=project_id, bfc_node_id=id_map[r.bfc_node_id],
                                   external_entity_id=r.external_entity_id, direction=r.direction,
                                   data_entity_id=r.data_entity_id, flow_label=r.flow_label, note=r.note,
                                   created_by=actor_id))
    for r in trg:
        db.add(BfcNodeTrigger(project_id=project_id, bfc_node_id=id_map[r.bfc_node_id],
                              process_trigger_id=r.process_trigger_id, note=r.note, created_by=actor_id))
    for node_id, r in roles:                          # D-64: the RACI moves to the target chart's home
        new_node = id_map[node_id]
        if to_set == "TO_BE":
            db.add(BrOrgRole(project_id=project_id, br_id=new_brs[new_node], org_role_id=r.org_role_id,
                             raci_code_id=r.raci_code_id, raci_behaviour=r.raci_behaviour, created_by=actor_id))
        else:
            db.add(BfcNodeOrgRole(project_id=project_id, bfc_node_id=new_node, org_role_id=r.org_role_id,
                                  raci_code_id=r.raci_code_id, raci_behaviour=r.raci_behaviour, created_by=actor_id))
    for r in apps:
        db.add(ApplicationBfcNode(project_id=project_id, bfc_node_id=id_map[r.bfc_node_id],
                                  application_id=r.application_id, support_note=r.support_note, created_by=actor_id))
    db.flush()
    audit.record(db, "BFC_SET_COPIED", actor_id=actor_id, project_id=project_id, target_table="bfc_node",
                 detail={**preview, "id_map": {str(k): v for k, v in id_map.items()}})
    db.commit()
    return {**preview, "confirm_hash": h, "applied": True}


def counts(db: Session, project_id: int) -> dict:
    """How many live nodes each chart holds — the screen's set switch."""
    rows = dict(db.execute(select(BfcNode.bfc_set_code, func.count()).where(
        BfcNode.project_id == project_id, BfcNode.is_active).group_by(BfcNode.bfc_set_code)).all())
    return {s: rows.get(s, 0) for s in bfc.SETS}
