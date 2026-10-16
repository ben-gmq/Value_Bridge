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

from models import (ApplicationBfcNode, AuditEvent, BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow,
                    BfcNodeOrgRole, BfcNodeTrigger, BrDataEntity, BrDataField, BrFunctionRequirement, BrOrgRole, BrRequirementLine,
                    BrSolution, BrSystemFlow,
                    BusinessRequirement,
                    DataEntity, ExternalEntity, OrgRole, ProcessTrigger, Solution)
from services import audit, bfc, components, lifecycle

RETIRED = "STEP_RETIRED_WITH_DEPENDENTS"
RESTORED = "STEP_RESTORED_WITH_DEPENDENTS"

# A-SR-1 / SR-4: exactly these, and a future FK-declared table blocks until it is added here.
# BfcNodeFlow left with D-38 (0045: retired, SELECT-only); BfcNodeTrigger joined with D-49.
OWNED_BY_STEP = (BusinessRequirement, BfcNodeDataEntity, BfcNodeOrgRole, BfcNodeExternalFlow,
                 ApplicationBfcNode, BfcNodeTrigger)       # ApplicationBfcNode: S6b-1 (Ben, 2026-10-11)
# Tables an older retire event may list that a restore must skip: their rows can never be live again.
RETIRED_TABLES = frozenset({"bfc_node_flow"})
# …and, by chart rather than by table (D-64, slice10d §3): step roles of a to-be step. 0052 moved them onto the
# BR (same-stamp copies for a step retired with its BR), and fk_bnor_node_as_is refuses them live.
AS_IS_ONLY_TABLES = frozenset({"bfc_node_org_role"})
OWNED_BY_BR = (BrDataEntity, BrOrgRole, BrSolution,          # BrSolution: S5-1 (Ben, 2026-10-09)
               BrFunctionRequirement,                         # D-52, slice10b Q-12: the FR itself survives
               BrRequirementLine,                             # D-59, slice11_schema §4
               BrDataField,                                   # D-60b: retires before its licence, restores after
               BrSystemFlow)                                  # D-61

# Retire order; restore runs it reversed. The D-24 licence FKs (fk_brde_io_licence,
# fk_bnef_io_licence) are immediate, so a licensee always goes before its licence.
TIERS = (
    (BrDataField,),                                           # D-60b: licensed by br_data_entity (fk_brdf_licence)
    (BrDataEntity, BfcNodeExternalFlow),
    (BfcNodeDataEntity, BrOrgRole, BrSolution, BrFunctionRequirement, BrRequirementLine, BrSystemFlow, BfcNodeOrgRole,
     ApplicationBfcNode, BfcNodeTrigger),
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
    for model in (BfcNodeDataEntity, BfcNodeOrgRole, BfcNodeExternalFlow, ApplicationBfcNode, BfcNodeTrigger):
        found[model] = list(db.scalars(select(model).where(model.bfc_node_id == sid, model.is_active)))
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
    if isinstance(row, ApplicationBfcNode):
        app = row.application_row
        return f"{app.application_code} {app.application_name}"
    if isinstance(row, BrSolution):
        sol = db.get(Solution, row.solution_id)
        return f"{sol.solution_number} {sol.solution_name}"
    if isinstance(row, BrFunctionRequirement):
        f = row.fr_row
        return f"{f.fr_number} {f.fr_name}"
    if isinstance(row, BfcNodeExternalFlow):
        ext = db.get(ExternalEntity, row.external_entity_id)
        return f"{ext.ext_number} {ext.ext_name} ({row.direction})"
    if isinstance(row, BfcNodeTrigger):
        return f"Trigger: {db.get(ProcessTrigger, row.process_trigger_id).trigger_name}"
    if isinstance(row, BrSystemFlow):
        return f"{row.entity_row.de_number} {row.source_row.application_code} → {row.target_row.application_code}"
    if isinstance(row, BrDataField):
        return f"{row.field_row.field_name} ({row.crud_code})"
    if isinstance(row, BrRequirementLine):
        return f"{row.line_label} {row.line_text[:60]}"
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
            "blockers": [_ref(b) for b in blockers], "confirm_hash": h, "tag_drift": _tag_drift(db, owned)}


def _tag_drift(db: Session, owned: list) -> list[str]:
    """slice10b §2.2 case 4, §4.2: the FRs whose tag answers none of the BRs they will still serve once this
    step's BR, its pairings and its links are retired. Information beside the preview, outside confirm_hash."""
    links = [r for r in owned if isinstance(r, BrFunctionRequirement)]
    if not links:
        return []
    br_id = links[0].br_id
    out = []
    for link in links:
        fr = link.fr_row
        if fr.solution_id is None:
            continue
        others = list(db.scalars(select(BrFunctionRequirement.br_id)
                                 .join(BusinessRequirement, BusinessRequirement.br_id == BrFunctionRequirement.br_id)
                                 .where(BrFunctionRequirement.fr_id == fr.fr_id, BrFunctionRequirement.is_active,
                                        BrFunctionRequirement.br_id != br_id, BusinessRequirement.is_active)))
        if not others:
            continue
        answered = db.scalar(select(BrSolution.br_solution_id).where(
            BrSolution.br_id.in_(others), BrSolution.solution_id == fr.solution_id, BrSolution.is_active).limit(1))
        if answered is None:
            out.append(fr.fr_number)
    return sorted(out)


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
        names = [lifecycle.label(b) for b in blockers[:10]]
        more = f" (+{len(blockers) - 10} more)" if len(blockers) > 10 else ""        # sara L4
        raise HTTPException(409, "Retire these first: " + "; ".join(names) + more)
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


# Rows a migration wrote for an older step retire without listing them in its event; they carry its stamp.
SAME_STAMP_BR_ROWS = (BrFunctionRequirement,       # slice10b §3.2 [Q-8], 0051
                      BrOrgRole)                   # slice10d Q-3, 0052: the to-be step roles moved to the BR


def _same_stamp_links(db: Session, rows: list, at: datetime) -> list:
    """The retired rows of the event's BR (SAME_STAMP_BR_ROWS) that carry the event's stamp and are not already
    listed. For a retire made after 10b / 10d they are in the event already, so this finds nothing new."""
    listed = {_key(r) for r in rows}
    br_ids = [r.br_id for r in rows if isinstance(r, BusinessRequirement)]
    if not br_ids:
        return []
    out = []
    for model in SAME_STAMP_BR_ROWS:
        found = db.scalars(select(model).where(model.br_id.in_(br_ids), ~model.is_active, model.deleted_at == at)
                           .order_by(model.__mapper__.primary_key[0]))
        out += [r for r in found if _key(r) not in listed]
    return out


def restore_plain(db: Session, actor_id: int, node: BfcNode) -> BfcNode:
    """PATCH /bfc-nodes/{id}/restore. Refused for a step whose latest retire took its
    dependents with it, so the undo key is never thrown away (spec §4, SR-1)."""
    # sara 7c L1: a step coming back live needs its chart on (DR7-P2); its performer needs nothing more (S10c-2).
    components.require_on(db, node.project_id, components.needed_for_rows([node], node.bfc_set_code))
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
    skip = RETIRED_TABLES | (AS_IS_ONLY_TABLES if step.bfc_set_code != "AS_IS" else frozenset())
    rows = [r for r in (_load(db, (t, i)) for t, i in event["rows"] if t not in skip)
            if r is not None and not r.is_active and r.deleted_at == at]          # §9.6: arrows stay retired
    # slice10b §3.2 [Q-8]: links backfilled for a pre-10b step retire are not in its event; they carry its stamp.
    # Merged BEFORE the parent and component checks, so they are held to the same all-or-nothing rule.
    rows += _same_stamp_links(db, rows, at)
    keys = {_key(r) for r in rows}
    if _key(step) not in keys:                                 # SR-1, belt and braces
        raise HTTPException(409, "This step was retired on its own. Use Restore.", headers=USE_PLAIN)
    first: dict[tuple[str, int], object] = {}
    for r in rows:
        for parent in lifecycle.inactive_parents(db, r):
            if _key(parent) not in keys:
                first.setdefault(_key(parent), parent)
    if first:
        names = [lifecycle.label(p) + ("" if getattr(p, "is_process", True) or not p.is_active
                                       else " (make it a process step again)")
                 for _, p in sorted(first.items())]
        raise HTTPException(409, "Restore these first: " + "; ".join(names), headers=RESTORE_FIRST)
    # DR7-P2: rows coming back live must belong to components that are on (D-37).
    components.require_on(db, step.project_id, components.needed_for_rows(rows, step.bfc_set_code))
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
