"""Numbered requirement lines under a BR (D-59, docs/slice11_schema.md §1).

A line's number ("BR-0043.3") is minted here at save: max + 1 over ALL the BR's lines, retired ones included, so a
number is never reused and never taken from a request (law 6). The BR row is locked FOR UPDATE first, which
serialises two editors adding to one BR; the full UK (br_id, line_no) is the database's own guard behind it.
seq_no is display order only (a position column: reordering is MOVED in a diff, never a scope change).
The BR's priority is derived — the live line priority with the lowest sort_order — and never stored.
"""
import getpass
import socket

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import AppUser, AuditEvent, BfcNode, BrRequirementLine, BusinessRequirement, CodeMaster, Project
from services import audit, lifecycle
from services.code_master import resolve, validate_required_code

KIND, PRIORITY = "BR_LINE_KIND", "BR_PRIORITY"


def _live_br(db: Session, br: BusinessRequirement) -> None:
    lifecycle.lock_for_share(db, db.get(BfcNode, br.bfc_node_id))    # SR-5: the step first,
    lifecycle.lock(db, br)                                           # then the BR, FOR UPDATE (one minter)
    if not br.is_active:
        raise HTTPException(409, f"{br.br_number} is retired. Restore it first.")


def _code_id(db: Session, br: BusinessRequirement, category: str, code: str | None, field: str) -> int | None:
    return None if code is None else validate_required_code(db, br.project_id, category, code, field).code_id


def _next_seq(db: Session, br_id: int) -> int:
    return (db.scalar(select(func.max(BrRequirementLine.seq_no)).where(
        BrRequirementLine.br_id == br_id, BrRequirementLine.is_active)) or 0) + 1


def list_lines(db: Session, br: BusinessRequirement, include_retired: bool = False) -> list[BrRequirementLine]:
    q = select(BrRequirementLine).where(BrRequirementLine.br_id == br.br_id)
    if not include_retired:
        q = q.where(BrRequirementLine.is_active)
    rows = list(db.scalars(q))
    return sorted(rows, key=lambda r: (not r.is_active, r.seq_no if r.is_active else r.line_no))


def add_line(db: Session, actor_id: int, br: BusinessRequirement, line_kind_code: str, priority_code: str | None,
             line_text: str, commit: bool = True) -> BrRequirementLine:
    _live_br(db, br)
    if not (line_text or "").strip():
        raise HTTPException(422, "line_text is required")
    line_no = (db.scalar(select(func.max(BrRequirementLine.line_no)).where(
        BrRequirementLine.br_id == br.br_id)) or 0) + 1
    row = BrRequirementLine(project_id=br.project_id, br_id=br.br_id, line_no=line_no,
                            seq_no=_next_seq(db, br.br_id),
                            line_kind_code_id=_code_id(db, br, KIND, line_kind_code, "line_kind_code"),
                            priority_code_id=_code_id(db, br, PRIORITY, priority_code, "priority_code"),
                            line_text=line_text, created_by=actor_id)
    db.add(row)
    db.flush()
    if commit:
        db.commit()
        db.refresh(row)
    return row


def update_line(db: Session, actor_id: int, row: BrRequirementLine, row_version: int, fields: dict) -> BrRequirementLine:
    """`fields` holds only what the request sent: priority_code may be sent as null to clear it."""
    br = db.get(BusinessRequirement, row.br_id)
    _live_br(db, br)
    lifecycle.check_live(row, row_version)
    if "line_kind_code" in fields:
        row.line_kind_code_id = _code_id(db, br, KIND, fields["line_kind_code"], "line_kind_code")
    if "priority_code" in fields:
        row.priority_code_id = _code_id(db, br, PRIORITY, fields["priority_code"], "priority_code")
    if "line_text" in fields:
        if not (fields["line_text"] or "").strip():
            raise HTTPException(422, "line_text is required")
        row.line_text = fields["line_text"]
    row.updated_by = actor_id
    db.commit()
    db.refresh(row)
    return row


def reorder(db: Session, actor_id: int, br: BusinessRequirement, order: list[tuple[int, int]]) -> list[BrRequirementLine]:
    """`order`: (line id, row_version) for EVERY live line, in the new order. Anything else is 422; a stale version 409.
    Two passes, because uq_brl_seq_live is checked row by row: park every line on a negative seq, then place it."""
    _live_br(db, br)
    live = {r.br_requirement_line_id: r for r in list_lines(db, br)}
    ids = [i for i, _ in order]
    if sorted(ids) != sorted(live) or len(set(ids)) != len(ids):
        raise HTTPException(422, "Send every live line of this requirement exactly once")
    for line_id, version in order:
        lifecycle.check_version(live[line_id], version)
    for n, line_id in enumerate(ids, 1):
        live[line_id].seq_no = -n
    db.flush()
    for n, line_id in enumerate(ids, 1):
        live[line_id].seq_no = n
        live[line_id].updated_by = actor_id
    db.flush()
    audit.record(db, "BR_LINES_REORDERED", actor_id=actor_id, project_id=br.project_id,
                 target_table="business_requirement", target_id=br.br_id, detail={"order": ids})
    db.commit()
    return list_lines(db, br)


def restore_line(db: Session, actor_id: int, row: BrRequirementLine) -> BrRequirementLine:
    """A restored line goes to the end of the live order; its number is the one it always had. The step and the BR
    are locked first, as for every other line write (sara L1), so a step retire or a second restore waits."""
    _live_br(db, db.get(BusinessRequirement, row.br_id))

    def to_end(r):
        r.seq_no = _next_seq(db, r.br_id)
    lifecycle.restore(db, actor_id, row, before_activate=to_end)
    db.refresh(row)
    return row


BACKFILLED = "BR_LINES_BACKFILLED"


def backfill(db: Session, actor_email: str) -> list[dict]:
    """CLI, one-off for the slice 11 deploy (slice11_schema §1.2). Per project, unless it already has a
    BR_LINES_BACKFILLED event (the marker, written even when nothing was copied): each live BR's non-blank
    business_logic becomes one RULE line and its output_expectation one OUTPUT line, verbatim, priority none, numbered
    after any line a person already added. The legacy columns are never cleared. Picking RULE / OUTPUT by code is a
    lookup, as a request body sends codes — not a branch on a code (law 5). The marker outlives a downgrade of 0055
    (audit is append-only), so after a downgrade and re-upgrade the copy does not run again (sara L2); the legacy
    text stays visible as "Earlier free text"."""
    actor = db.scalars(select(AppUser).where(func.lower(AppUser.email) == actor_email.strip().lower())).one_or_none()
    if actor is None or not actor.is_active or not actor.is_platform_admin:
        raise SystemExit("--actor-email must be an active platform admin")
    out = []
    for p in db.scalars(select(Project).order_by(Project.project_id)).all():
        if db.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.project_id == p.project_id, AuditEvent.event_type == BACKFILLED)):
            out.append({"project_id": p.project_id, "count": None})
            continue
        kinds = {c.code: c.code_id for c in resolve(db, p.project_id, KIND)}
        if not {"RULE", "OUTPUT"} <= kinds.keys():
            raise SystemExit("Run seeds.seed_code_master first: BR_LINE_KIND RULE / OUTPUT missing")
        ids = []
        for br in db.scalars(select(BusinessRequirement).where(BusinessRequirement.project_id == p.project_id,
                                                               BusinessRequirement.is_active)
                             .order_by(BusinessRequirement.br_id)).all():
            for text, kind in ((br.business_logic, "RULE"), (br.output_expectation, "OUTPUT")):
                if not (text or "").strip():
                    continue
                line_no = (db.scalar(select(func.max(BrRequirementLine.line_no)).where(
                    BrRequirementLine.br_id == br.br_id)) or 0) + 1
                row = BrRequirementLine(project_id=br.project_id, br_id=br.br_id, line_no=line_no,
                                        seq_no=_next_seq(db, br.br_id), line_kind_code_id=kinds[kind],
                                        line_text=text, created_by=br.updated_by or br.created_by)
                db.add(row)
                db.flush()
                ids.append(row.br_requirement_line_id)
        audit.record(db, BACKFILLED, actor_id=actor.app_user_id, project_id=p.project_id,
                     detail={"count": len(ids), "line_ids": ids, "os_user": getpass.getuser(),
                             "host": socket.gethostname()})
        db.commit()
        out.append({"project_id": p.project_id, "count": len(ids)})
    return out


def br_priority(db: Session, br_id: int) -> str | None:
    """The BR's priority, derived (§1.1): the live line priority with the lowest sort_order, else None."""
    return db.scalar(select(CodeMaster.code).join(BrRequirementLine, BrRequirementLine.priority_code_id == CodeMaster.code_id)
                     .where(BrRequirementLine.br_id == br_id, BrRequirementLine.is_active)
                     .order_by(CodeMaster.sort_order, CodeMaster.code).limit(1))
