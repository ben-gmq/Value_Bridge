"""Programs (§7.10a, D-32, D-71): a header, a set of reads and its members. It owns no business data, so it has no
SQL over business tables — roll-ups call the per-project reports. Its members reach every live project of the program
at their level (D-71); who can open what is still decided only by services/access."""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import AppUser, Client, Program, ProgramMember, Project
from services import access, audit
from services.lifecycle import check_version, soft_delete


def get_program(db: Session, program_id: int) -> Program:
    p = db.get(Program, program_id)
    if p is None:
        raise HTTPException(404, "Not found")
    return p


def list_visible_programs(db: Session, user: AppUser) -> list[Program]:
    ids = access.visible_program_ids(db, user)          # M8 — visibility has one owner
    q = select(Program).where(Program.is_active).order_by(Program.program_code)
    if ids is not None:
        if not ids:
            return []
        q = q.where(Program.program_id.in_(ids))
    return list(db.scalars(q))


def create_program(db: Session, actor: AppUser, client_id: int, program_code: str,
                   program_name: str, description: str | None) -> Program:
    client = db.get(Client, client_id)
    if client is None or not client.is_active:
        raise HTTPException(422, "Choose an active client")
    p = Program(client_id=client_id, program_code=program_code.strip().upper(),
                program_name=program_name.strip(), description=description,
                created_by=actor.app_user_id)
    db.add(p)
    db.flush()
    audit.record(db, "PROGRAM_CREATED", actor_id=actor.app_user_id, target_table="program",
                 target_id=p.program_id)
    db.commit()
    return p


PROGRAM_EDITABLE = ("program_code", "program_name", "client_id", "description")


def update_program(db: Session, actor: AppUser, program_id: int, row_version: int, changes: dict) -> Program:
    """Slice 1f §3.7 (function 134): a platform admin edits the program header. The row is locked before the checks,
    so a project moved in meanwhile is seen. A client change is refused while any project, live or retired, is in the
    program — a retired one's composite FK still binds the client (round 1 D7). Audited field by field; an edit that
    changes nothing writes nothing."""
    p = db.scalar(select(Program).where(Program.program_id == program_id).with_for_update())
    if p is None:
        raise HTTPException(404, "Not found")
    if not p.is_active:
        raise HTTPException(409, "This program is retired")
    check_version(p, row_version)
    changes = {f: v for f, v in changes.items() if f in PROGRAM_EDITABLE}
    for f in ("program_code", "program_name", "client_id"):
        if f in changes and (changes[f] is None or (isinstance(changes[f], str) and not changes[f].strip())):
            raise HTTPException(422, f"{f.replace('_', ' ').capitalize()} is required")
    if "program_code" in changes:
        changes["program_code"] = changes["program_code"].strip().upper()          # as at create
    if "program_name" in changes:
        changes["program_name"] = changes["program_name"].strip()
    diff = {f: [getattr(p, f), v] for f, v in changes.items() if getattr(p, f) != v}
    if not diff:
        return p
    client_id = changes.get("client_id", p.client_id)
    if "client_id" in diff:
        client = db.get(Client, client_id)
        if client is None or not client.is_active:
            raise HTTPException(422, "Choose an active client")
        held = db.scalars(select(Project.project_code).where(Project.program_id == p.program_id)
                          .order_by(Project.project_code)).all()
        if held:
            raise HTTPException(409, f"The program holds projects ({', '.join(held)}), so its client cannot change")
    code, name = changes.get("program_code", p.program_code), changes.get("program_name", p.program_name)
    others = select(Program.program_id).where(Program.client_id == client_id, Program.program_id != p.program_id)
    if db.scalar(others.where(Program.program_code == code)) is not None:
        raise HTTPException(409, f"Program code {code} is already used for this client")
    if db.scalar(others.where(Program.is_active, func.lower(Program.program_name) == name.lower())) is not None:
        raise HTTPException(409, f"A live program named {name} already exists for this client")
    for f, (_, v) in diff.items():
        setattr(p, f, v)
    p.updated_by = actor.app_user_id
    audit.record(db, "PROGRAM_UPDATED", actor_id=actor.app_user_id, target_table="program", target_id=p.program_id,
                 detail=diff)
    db.commit()
    return p


def program_projects(db: Session, user: AppUser, program_id: int) -> list[Project]:
    """The roll-up rule (R2-S2): only projects in visible_project_ids(user) ∩ program."""
    ids = access.visible_project_ids(db, user)
    q = select(Project).where(Project.program_id == program_id, Project.is_active)
    if ids is not None:
        q = q.where(Project.project_id.in_(ids or {-1}))
    return list(db.scalars(q.order_by(Project.project_code)))


def _move_changes(db: Session, p: Project, target_program_id: int | None) -> dict:
    """Who gains, loses or changes level on the project when it moves (D-71; model §5): every active staff user whose
    level differs between the old and the new program's memberships. The preview hash covers it."""
    gains, loses, changes = [], [], []
    users = db.scalars(select(AppUser).where(AppUser.is_active, ~AppUser.is_platform_admin)
                       .order_by(AppUser.display_name))
    for u in users:
        old = access.live_program_member(db, p.program_id, u.app_user_id)
        new = access.live_program_member(db, target_program_id, u.app_user_id)
        if old is None and new is None:
            continue
        m = access.live_member(db, p.project_id, u.app_user_id)
        ml = m.access_level if m else None
        before = access.level_for(u.user_kind, p.is_restricted, ml, old.access_level if old else None)
        after = access.level_for(u.user_kind, p.is_restricted, ml, new.access_level if new else None)
        b, a = before[0] if before else None, after[0] if after else None
        if b == a:
            continue
        who = {"user_id": u.app_user_id, "display_name": u.display_name, "before": b, "after": a}
        (gains if b is None else loses if a is None else changes).append(who)
    return {"gains": gains, "loses": loses, "changes": changes}


def move_project_program(db: Session, actor: AppUser, project_id: int,
                         target_program_id: int | None, confirm_hash: str | None,
                         expected_from_program_id: int | None = None) -> dict:
    """Platform admin only (Q10, D-71 (6): a program admin moving a restricted project into their own program would
    grant themselves access). Step 1 (no hash) previews the move and writes nothing; step 2 locks both programs then
    the project (design-auditor M2), recomputes the preview and applies it only if unchanged (R2-S3). Since D-71 a move
    changes access: the preview names who gains, loses or changes level through the programs' members."""
    p = db.get(Project, project_id)
    if p is None or not p.is_active:
        raise HTTPException(404, "Not found")
    access.require_not_pending(db, project_id)              # slice 16 R17: a platform write the guard does not see
    if expected_from_program_id is not None and p.program_id != expected_from_program_id:
        raise HTTPException(404, "Not found")              # M1 — not in THIS program
    t = db.get(Program, target_program_id) if target_program_id else None
    if target_program_id and (t is None or not t.is_active):
        raise HTTPException(422, "Choose an active program")
    if t and t.client_id != p.client_id:
        raise HTTPException(422, "A program's projects belong to its client")
    if (p.program_id or None) == (target_program_id or None):
        raise HTTPException(422, "The project is already there")
    def plan() -> dict:
        return {"project": p.project_code, "from_program_id": p.program_id, "to_program_id": target_program_id,
                **_move_changes(db, p, target_program_id)}
    preview = plan()
    h = hashlib.sha256(json.dumps(preview, sort_keys=True).encode()).hexdigest()
    if confirm_hash is None:
        return {"preview": preview, "preview_hash": h, "applied": False}
    from services.project import lock_program
    seen_program = p.program_id
    lock_program(db, seen_program, target_program_id)
    db.refresh(p, with_for_update=True)
    if t is not None:
        db.refresh(t)
        if not t.is_active:                                   # sara B L5: retired while we waited
            raise HTTPException(422, "Choose an active program")
    if p.program_id != seen_program:
        raise HTTPException(409, "The project's program changed since the preview. Review it again.")
    preview = plan()
    h = hashlib.sha256(json.dumps(preview, sort_keys=True).encode()).hexdigest()
    if confirm_hash != h:
        raise HTTPException(409, "Who can open this project, or its program, changed since the preview. "
                                 "Review it again.")
    p.program_id = target_program_id
    p.updated_by = actor.app_user_id
    audit.record(db, "PROJECT_PROGRAM_CHANGED", actor_id=actor.app_user_id, project_id=project_id,
                 detail=preview)
    db.commit()
    return {"preview": preview, "preview_hash": h, "applied": True}


# ---- program members (D-71 (2), (5); D-73) — program ADMIN by route guard ----------------------------------------
def _program_share_lock(db: Session, program_id: int) -> None:
    """Member writes take the program row FOR SHARE; a restriction or move confirm takes it FOR UPDATE (design-auditor
    M2), so a member added mid-confirm waits and the recomputed preview sees them."""
    db.execute(select(Program.program_id).where(Program.program_id == program_id).with_for_update(read=True))


def _member_out(m: ProgramMember, u: AppUser) -> dict:
    level = "PLATFORM" if u.is_platform_admin else access._lower(access.KIND_CAP[u.user_kind], m.access_level)
    return {"program_member_id": m.program_member_id, "user_id": u.app_user_id, "display_name": u.display_name,
            "user_kind": u.user_kind, "user_is_active": u.is_active, "access_level": m.access_level,
            "effective_level": level, "member_note": m.member_note, "row_version": m.row_version}


def list_members(db: Session, program: Program) -> list[dict]:
    """Live memberships, switched-off users included and marked, so they can be removed (design-auditor L1)."""
    rows = db.execute(select(ProgramMember, AppUser).join(AppUser, AppUser.app_user_id == ProgramMember.app_user_id)
                      .where(ProgramMember.program_id == program.program_id, ProgramMember.is_active)
                      .order_by(ProgramMember.program_member_id)).all()
    return [_member_out(m, u) for m, u in rows]


def member_row(db: Session, m: ProgramMember) -> dict:
    return _member_out(m, db.get(AppUser, m.app_user_id))


def member_candidates(db: Session, program: Program) -> list[dict]:
    """Who a program admin may add: active staff, not platform admins, not yet live members (/users stays FTC-only)."""
    taken = set(db.scalars(select(ProgramMember.app_user_id).where(ProgramMember.program_id == program.program_id,
                                                                   ProgramMember.is_active)))
    return [{"user_id": u.app_user_id, "display_name": u.display_name, "user_kind": u.user_kind}
            for u in db.scalars(select(AppUser).where(AppUser.is_active, ~AppUser.is_platform_admin)
                                .order_by(AppUser.display_name)) if u.app_user_id not in taken]


def _check_level(target: AppUser, access_level: str) -> None:
    """D-71 (7): a VIEWER-kind user is refused above VIEW, never quietly capped."""
    if not access.rank_ok(access.KIND_CAP[target.user_kind], access_level):
        raise HTTPException(422, f"{target.display_name} is a viewer and can only be added as a viewer")


def add_member(db: Session, actor: AppUser, program: Program, user_id: int, access_level: str,
               member_note: str | None) -> ProgramMember:
    from services.project import _user_share_lock
    _program_share_lock(db, program.program_id)
    _user_share_lock(db, user_id)
    target = db.get(AppUser, user_id)
    if target is None or not target.is_active:
        raise HTTPException(422, "Choose an active user")
    if target.is_platform_admin:
        raise HTTPException(422, "A platform admin sees every project and needs no membership")
    _check_level(target, access_level)
    if access.live_program_member(db, program.program_id, user_id) is not None:
        raise HTTPException(409, f"{target.display_name} is already a member of this program")
    m = ProgramMember(program_id=program.program_id, app_user_id=user_id, access_level=access_level,
                      member_note=(member_note or "").strip() or None, created_by=actor.app_user_id)
    db.add(m)
    db.flush()                    # uq_prgm_live is the backstop against a concurrent add (→ 409)
    audit.record(db, "PROGRAM_MEMBER_ADDED", actor_id=actor.app_user_id, target_table="program_member",
                 target_id=m.program_member_id,
                 detail={"program_id": program.program_id, "user_id": user_id, "access_level": access_level})
    db.commit()
    return m


def change_member_level(db: Session, actor: AppUser, m: ProgramMember, access_level: str,
                        row_version: int) -> ProgramMember:
    """Any program admin may change any member, another admin included (D-73)."""
    from services.project import _user_share_lock
    _program_share_lock(db, m.program_id)
    _user_share_lock(db, m.app_user_id)
    if not m.is_active:
        raise HTTPException(409, "That membership was already removed")
    if m.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    _check_level(db.get(AppUser, m.app_user_id), access_level)
    if m.access_level != access_level:
        old, m.access_level = m.access_level, access_level
        m.updated_by = actor.app_user_id
        audit.record(db, "PROGRAM_MEMBER_LEVEL_CHANGED", actor_id=actor.app_user_id, target_table="program_member",
                     target_id=m.program_member_id,
                     detail={"program_id": m.program_id, "user_id": m.app_user_id, "from": old, "to": access_level})
    db.commit()
    return m


def remove_member(db: Session, actor: AppUser, m: ProgramMember, row_version: int) -> None:
    """Soft-remove (law 1); never restored — access returns only through add. The project admins this member
    appointed keep their roles: a role belongs to the project (D-73)."""
    _program_share_lock(db, m.program_id)
    if not m.is_active:
        raise HTTPException(409, "That membership was already removed")
    if m.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    soft_delete(m, actor.app_user_id)
    m.updated_by = actor.app_user_id
    audit.record(db, "PROGRAM_MEMBER_REMOVED", actor_id=actor.app_user_id, target_table="program_member",
                 target_id=m.program_member_id, detail={"program_id": m.program_id, "user_id": m.app_user_id})
    db.commit()
