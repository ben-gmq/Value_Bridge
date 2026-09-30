"""Retire a process step together with the rows that exist only because of it, and undo it in
one action (docs/step_retire_spec.md; design §1a S3-SR, which revises Q4 / R2-D2 for process
steps only). This module is the one owner of the owned-set rule.

Retire and restore each run in ONE transaction and commit exactly once, at the end: every write
before that is a flush, so any failure rolls the whole action back. Every row one retire touches
carries the same deleted_at, and the summary audit event that lists them is the undo key.
"""
import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (AuditEvent, BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeFlow,
                    BfcNodeOrgRole, BrDataEntity, BrOrgRole, BusinessRequirement, DataEntity,
                    ExternalEntity, OrgRole)
from services import audit, bfc, lifecycle

RETIRED = "STEP_RETIRED_WITH_DEPENDENTS"
RESTORED = "STEP_RESTORED_WITH_DEPENDENTS"

# A-SR-1 / SR-4: exactly these, and a future FK-declared table blocks until it is added here.
OWNED_BY_STEP = (BusinessRequirement, BfcNodeDataEntity, BfcNodeOrgRole, BfcNodeExternalFlow,
                 BfcNodeFlow)
OWNED_BY_BR = (BrDataEntity, BrOrgRole)

# Retire order; restore runs it reversed. The D-24 licence FKs (fk_brde_io_licence,
# fk_bnef_io_licence) are immediate, so a licensee always goes before its licence.
TIERS = (
    (BrDataEntity, BfcNodeExternalFlow),
    (BfcNodeDataEntity, BrOrgRole, BfcNodeOrgRole, BfcNodeFlow),
    (BusinessRequirement,),
    (BfcNode,),
)

# The 409s the node panel answers by offering the other restore (SR-1), or a list to restore.
USE_DEPENDENTS = {"X-VB-Error": "USE_RESTORE_WITH_DEPENDENTS"}
USE_PLAIN = {"X-VB-Error": "USE_PLAIN_RESTORE"}
RESTORE_FIRST = {"X-VB-Error": "RESTORE_FIRST"}


def _key(row) -> tuple[str, int]:
    return row.__table__.name, lifecycle.pk(row)


def _require_step(node: BfcNode) -> None:
    if not node.is_process:
        raise HTTPException(422, "Only a process step retires with its requirement and flows. "
                                 "A summary node is retired on its own once it is empty")


def _owned(db: Session, step: BfcNode) -> list:
    """The step's active owned rows, in retire (tier) order, each once."""
    sid = step.bfc_node_id
    br = db.scalars(select(BusinessRequirement).where(BusinessRequirement.bfc_node_id == sid,
                                                      BusinessRequirement.is_active)).first()
    found = {BusinessRequirement: [br] if br else []}
    for model in (BfcNodeDataEntity, BfcNodeOrgRole, BfcNodeExternalFlow):
        found[model] = list(db.scalars(select(model).where(model.bfc_node_id == sid, model.is_active)))
    # One OR query returns a self-loop once.
    found[BfcNodeFlow] = list(db.scalars(select(BfcNodeFlow).where(
        (BfcNodeFlow.from_bfc_node_id == sid) | (BfcNodeFlow.to_bfc_node_id == sid),
        BfcNodeFlow.is_active)))
    for model in OWNED_BY_BR:
        found[model] = [] if br is None else list(db.scalars(select(model).where(
            model.br_id == br.br_id, model.is_active)))
    return [r for tier in TIERS[:-1] for model in tier for r in sorted(found[model], key=lifecycle.pk)]


def _load(db: Session, key: tuple[str, int]):
    return db.get(lifecycle.mapper_for(key[0]), key[1])


def _node_ref(db: Session, node_id: int | None, end: str) -> str:
    if node_id is None:
        return end
    n = db.get(BfcNode, node_id)
    return f"{n.hier_code} {n.node_name}"


def describe(db: Session, row) -> str:
    """How an owned row reads in the preview list (spec §4, 'confirm on screen')."""
    if isinstance(row, BusinessRequirement):
        return row.br_number
    if isinstance(row, (BrDataEntity, BfcNodeDataEntity)):
        de = db.get(DataEntity, row.data_entity_id)
        tag = row.crud_code if isinstance(row, BrDataEntity) else row.direction
        return f"{de.de_number} {de.de_name} ({tag})"
    if isinstance(row, (BrOrgRole, BfcNodeOrgRole)):
        return f"{db.get(OrgRole, row.org_role_id).org_role_code} ({row.raci_code})"
    if isinstance(row, BfcNodeExternalFlow):
        ext = db.get(ExternalEntity, row.external_entity_id)
        return f"{ext.ext_number} {ext.ext_name} ({row.direction})"
    if isinstance(row, BfcNodeFlow):
        label = f" [{row.condition_label}]" if row.condition_label else ""
        return (f"{_node_ref(db, row.from_bfc_node_id, 'start')} → "
                f"{_node_ref(db, row.to_bfc_node_id, 'end')}{label}")
    return lifecycle.label(row)


def _ref(row, text: str | None = None) -> dict:
    table, pk = _key(row)
    return {"table": table, "id": pk, "label": text if text is not None else lifecycle.label(row)}


def _confirm_hash(step: BfcNode, owned: list) -> str:
    body = {"step": [step.bfc_node_id, step.row_version],
            "rows": sorted([*_key(r), r.row_version] for r in owned)}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _assess(db: Session, step: BfcNode) -> tuple[list, list, str]:
    """(owned rows, blocker rows, confirm hash). Blockers are the active dependents of the step
    and of every owned row, minus the owned set itself (spec §4)."""
    owned = _owned(db, step)
    mine = {_key(step)} | {_key(r) for r in owned}
    deps: set[tuple[str, int]] = set()
    for row in (step, *owned):
        deps |= lifecycle.active_dependent_ids(db, row)
    blockers = [_load(db, k) for k in sorted(deps - mine)]
    return owned, blockers, _confirm_hash(step, owned)


def preview(db: Session, step: BfcNode) -> dict:
    _require_step(step)
    if not step.is_active:
        raise HTTPException(409, f"{lifecycle.label(step)} is already retired")
    owned, blockers, h = _assess(db, step)
    return {"owned": [_ref(r, describe(db, r)) for r in owned],
            "blockers": [_ref(b) for b in blockers], "confirm_hash": h}


def retire_row(db: Session, actor_id: int, row, at: datetime, action_id: str) -> None:
    """One owned row. A module function so criterion 7's test can fail the last one."""
    lifecycle.retire_row(db, actor_id, row, at=at, detail={"action_id": action_id})


def restore_row(db: Session, actor_id: int, row, action_id: str) -> None:
    detail = {"action_id": action_id}
    if isinstance(row, BfcNode):
        bfc.restore_node_row(db, actor_id, row, detail=detail)       # name check + _free (SR-2)
    else:
        lifecycle.restore_row(db, actor_id, row, detail=detail)


def retire(db: Session, actor_id: int, step: BfcNode, confirm_hash: str) -> None:
    lifecycle.lock(db, step)            # serialises the child writers (SR-5)
    _require_step(step)
    if not step.is_active:
        raise HTTPException(409, f"{lifecycle.label(step)} is already retired")
    owned, blockers, h = _assess(db, step)
    if blockers:
        raise HTTPException(409, "Retire these first: " + "; ".join(lifecycle.label(b) for b in blockers))
    if confirm_hash != h:
        raise HTTPException(409, "The step changed since the preview. Review it again.")
    at, action_id = datetime.now(UTC), str(uuid.uuid4())
    by_model: dict[type, list] = {}
    for r in (*owned, step):
        by_model.setdefault(type(r), []).append(r)
    done = []
    for tier in TIERS:
        for model in tier:
            for r in by_model.get(model, []):
                retire_row(db, actor_id, r, at, action_id)
                done.append(list(_key(r)))
        db.flush()
    audit.record(db, RETIRED, actor_id=actor_id, project_id=step.project_id,
                 target_table="bfc_node", target_id=step.bfc_node_id,
                 detail={"action_id": action_id, "rows": done, "confirm_hash": h,
                         "deleted_at": at.isoformat()})
    db.commit()


def _retired_with_dependents(db: Session, step: BfcNode) -> dict | None:
    """SR-1: the latest summary event, if the step's own deleted_at is still that event's."""
    if step.is_active or step.deleted_at is None:
        return None
    ev = db.scalars(select(AuditEvent).where(
        AuditEvent.event_type == RETIRED, AuditEvent.target_table == "bfc_node",
        AuditEvent.target_id == step.bfc_node_id).order_by(AuditEvent.audit_event_id.desc())
        .limit(1)).first()
    if ev is None or datetime.fromisoformat(ev.detail["deleted_at"]) != step.deleted_at:
        return None
    return ev.detail


def restore_plain(db: Session, actor_id: int, node: BfcNode) -> BfcNode:
    """PATCH /bfc-nodes/{id}/restore. Refused for a step whose latest retire took its
    dependents with it, so the undo key is never thrown away (spec §4, SR-1)."""
    if _retired_with_dependents(db, node) is not None:
        raise HTTPException(409, "This step was retired with its requirement and flows. "
                                 "Use Restore with its requirement and flows.", headers=USE_DEPENDENTS)
    return bfc.restore_node(db, actor_id, node)


def restore(db: Session, actor_id: int, step: BfcNode) -> dict:
    """All or nothing (A-SR-5): the rows the latest summary event lists that are still retired
    with its stamp come back, in reverse tiers, or none do."""
    lifecycle.lock(db, step)
    _require_step(step)
    if step.is_active:
        raise HTTPException(409, f"{lifecycle.label(step)} is not retired")
    event = _retired_with_dependents(db, step)                 # read before any write
    if event is None:
        raise HTTPException(409, "This step was retired on its own. Use Restore.", headers=USE_PLAIN)
    at = datetime.fromisoformat(event["deleted_at"])
    rows = [r for r in (_load(db, (t, i)) for t, i in event["rows"])
            if r is not None and not r.is_active and r.deleted_at == at]
    keys = {_key(r) for r in rows}
    if _key(step) not in keys:                                 # SR-1, belt and braces
        raise HTTPException(409, "This step was retired on its own. Use Restore.", headers=USE_PLAIN)
    first: dict[tuple[str, int], object] = {}
    for r in rows:
        for parent in lifecycle.inactive_parents(db, r):
            if _key(parent) not in keys:
                first.setdefault(_key(parent), parent)
    if first:
        raise HTTPException(409, "Restore these first: "
                            + "; ".join(lifecycle.label(p) for _, p in sorted(first.items())),
                            headers=RESTORE_FIRST)
    action_id = str(uuid.uuid4())
    by_model: dict[type, list] = {}
    for r in rows:
        by_model.setdefault(type(r), []).append(r)
    done = []
    for tier in reversed(TIERS):
        for model in tier:
            for r in by_model.get(model, []):
                restore_row(db, actor_id, r, action_id)
                done.append(list(_key(r)))
        db.flush()
    audit.record(db, RESTORED, actor_id=actor_id, project_id=step.project_id,
                 target_table="bfc_node", target_id=step.bfc_node_id,
                 detail={"action_id": action_id, "retire_action_id": event["action_id"], "rows": done})
    db.commit()
    return {"restored": len(done)}
