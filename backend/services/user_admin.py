"""User administration (§7.10). Platform admin only — enforced by the route guard."""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.security import hash_password
from config import get_settings
from models import AppUser, Program, ProgramMember, Project, ProjectMember
from services import access, audit
from services.lifecycle import soft_delete

MIN_PASSWORD = 10


def check_ftc_address(email: str) -> None:
    """D-11: every account is FTC staff. Client-side people are stakeholders, not users."""
    domain = email.strip().lower().rpartition("@")[2]
    if "@" not in email or domain not in get_settings().email_domains:
        raise HTTPException(422, "Value Bridge accounts are FTC staff only. Client-side people "
                                 "are recorded as stakeholders.")


def list_users(db: Session) -> list[AppUser]:
    return list(db.scalars(select(AppUser).order_by(AppUser.display_name)))


KINDS = ("USER", "VIEWER")


def _kind(user_kind: str) -> str:
    if user_kind not in KINDS:
        raise HTTPException(400, f"user_kind: '{user_kind}' is not one of USER, VIEWER")
    return user_kind


def create_user(db: Session, actor: AppUser, email: str, display_name: str,
                initial_password: str, user_kind: str) -> AppUser:
    """§7.10: every new account starts as a non-admin. Admin rights are a separate, audited
    act (set_platform_admin) — never a checkbox on creation (M7). D-40: the kind is required —
    USER edits and VIEWER reads every unrestricted project."""
    check_ftc_address(email)
    if len(initial_password) < MIN_PASSWORD:
        raise HTTPException(422, f"The password must be at least {MIN_PASSWORD} characters")
    user = AppUser(email=email.strip(), display_name=display_name.strip(),
                   password_hash=hash_password(initial_password), user_kind=_kind(user_kind),
                   is_platform_admin=False, created_by=actor.app_user_id)
    db.add(user)
    db.flush()
    audit.record(db, "USER_CREATED", actor_id=actor.app_user_id, target_table="app_user",
                 target_id=user.app_user_id,
                 detail={"email": user.email, "user_kind": user.user_kind})
    db.commit()
    return user   # the plaintext password is never persisted, logged or returned


def deactivate_user(db: Session, actor: AppUser, user_id: int) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(404, "Not found")
    if user.app_user_id == actor.app_user_id:
        raise HTTPException(422, "You cannot deactivate your own account")
    soft_delete(user, actor.app_user_id)                 # M12 — who and when, on the row
    audit.record(db, "USER_DEACTIVATED", actor_id=actor.app_user_id, target_table="app_user",
                 target_id=user_id)
    db.commit()
    return user   # effective on the target's next request — current_user re-reads the row


# ---- what a change of kind or admin flag brings back into force (D-71; design-auditor M1) ----
# A membership is unread while the user is a platform admin, and capped while they are a VIEWER. Changing either
# can lift what a stored membership grants — e.g. a demoted admin is again admin of every project they were admin of.
# The change is previewed (which memberships come back, at what level) and confirmed against a hash of exactly that.

def _comes_back(db: Session, user: AppUser, new_kind: str, new_admin: bool) -> list[dict]:
    if new_admin:
        return []                                    # a platform admin's memberships are unread
    # every live project the user reaches by a live project or program membership (sara 1g L9: program roles too)
    direct = {m.project_id: m.access_level for m in db.scalars(select(ProjectMember).where(
        ProjectMember.app_user_id == user.app_user_id, ProjectMember.is_active))}
    programs = {g.program_id: g.access_level for g in db.scalars(select(ProgramMember).join(
        Program, Program.program_id == ProgramMember.program_id).where(
        ProgramMember.app_user_id == user.app_user_id, ProgramMember.is_active, Program.is_active))}
    projects = db.scalars(select(Project).where(
        Project.is_active, Project.project_id.in_(direct or {-1}) | Project.program_id.in_(programs or {-1}))
        .order_by(Project.project_code, Project.project_id))
    out = []
    for p in projects:
        ml, gl = direct.get(p.project_id), programs.get(p.program_id)
        after = access.level_for(new_kind, p.is_restricted, ml, gl)[0]
        if user.is_platform_admin:
            before = None                            # unread until now
        else:
            got = access.level_for(user.user_kind, p.is_restricted, ml, gl)
            before = got[0] if got else None
        if before is None or access.LEVEL_RANK[after] > access.LEVEL_RANK[before]:
            stored = max((x for x in (ml, gl) if x), key=lambda x: access.LEVEL_RANK[x])
            out.append({"project_id": p.project_id, "project_code": p.project_code, "project_name": p.project_name,
                        "access_level": stored, "via": "MEMBER" if stored == ml else "PROGRAM",
                        "level_before": before, "level_after": after})
    # the program roles themselves — managing a program's members — even with no live project behind them (sara B M1)
    for g, prog in db.execute(select(ProgramMember, Program).join(Program, Program.program_id == ProgramMember.program_id)
                              .where(ProgramMember.app_user_id == user.app_user_id, ProgramMember.is_active,
                                     Program.is_active).order_by(Program.program_code, Program.program_id)).all():
        after = access._lower(access.KIND_CAP[new_kind], g.access_level)
        before = None if user.is_platform_admin else access._lower(access.KIND_CAP[user.user_kind], g.access_level)
        if before is None or access.LEVEL_RANK[after] > access.LEVEL_RANK[before]:
            out.append({"project_id": None, "project_code": prog.program_code, "project_name": prog.program_name,
                        "access_level": g.access_level, "via": "PROGRAM_ROLE",
                        "level_before": before, "level_after": after})
    return out


def _digest(user_id: int, new_kind: str, new_admin: bool, rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps({"user": user_id, "kind": new_kind, "admin": new_admin, "rows": rows},
                                     sort_keys=True).encode()).hexdigest()


def access_change_preview(db: Session, user_id: int, user_kind: str, is_platform_admin: bool) -> dict:
    user = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(404, "Not found")
    rows = _comes_back(db, user, _kind(user_kind), is_platform_admin)
    return {"comes_back": rows, "confirm_hash": _digest(user_id, user_kind, is_platform_admin, rows)}


def _require_confirm(db: Session, user: AppUser, new_kind: str, new_admin: bool, confirm_hash: str | None) -> list:
    """Under a lock on the user row — member writes take it FOR SHARE — recompute what comes back; anything at all
    needs the hash of exactly that list, so a membership added after the preview is never revived unseen."""
    db.refresh(user, with_for_update={"key_share": True})   # FOR NO KEY UPDATE: blocks member writes, not FK inserts (sara L8)
    rows = _comes_back(db, user, new_kind, new_admin)
    if rows and confirm_hash != _digest(user.app_user_id, new_kind, new_admin, rows):
        raise HTTPException(409, "This change gives back project access that has not been reviewed. "
                                 "Review it again.")
    return rows


def set_user_kind(db: Session, actor: AppUser, user_id: int, user_kind: str, row_version: int,
                  confirm_hash: str | None = None) -> AppUser:
    """D-40 (§8.2): platform admin, audited, optimistic lock. Takes effect on the next request. A change that lifts a
    stored membership needs the preview's hash (D-71)."""
    user = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(404, "Not found")
    new_kind = _kind(user_kind)
    back = _require_confirm(db, user, new_kind, user.is_platform_admin, confirm_hash)
    if user.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if user.user_kind != new_kind:
        old, user.user_kind = user.user_kind, new_kind
        user.updated_by = actor.app_user_id
        audit.record(db, "USER_KIND_CHANGED", actor_id=actor.app_user_id, target_table="app_user",
                     target_id=user_id, detail={"from": old, "to": new_kind,
                                                "comes_back": [r["project_id"] for r in back]})
    db.commit()
    return user


def set_platform_admin(db: Session, actor: AppUser, user_id: int, value: bool, rationale: str,
                       row_version: int, user_kind: str | None = None, confirm_hash: str | None = None) -> AppUser:
    """Grant or remove platform-admin rights (M7). Audited with a reason, because an admin
    sees every client's data. Removing them requires the kind the user falls back to, so a
    demoted admin never silently becomes an editor everywhere (DR7-S6), and the preview's hash when their stored
    memberships come back into force (D-71)."""
    user = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(404, "Not found")
    if value:                                       # slice 17 (AR-13): granting is a request a second admin approves
        raise HTTPException(422, "Make someone an admin through a request a second admin approves")
    if user.app_user_id == actor.app_user_id:
        raise HTTPException(422, "You cannot change your own administrator rights")
    if not rationale.strip():
        raise HTTPException(422, "Changing administrator rights needs a reason")
    if not value and user_kind is None:
        raise HTTPException(422, "Say what the user becomes: user_kind USER or VIEWER")
    new_kind = _kind(user_kind) if not value else user.user_kind
    no_op = f"{user.display_name} is {'already' if value else 'not'} an administrator"
    if user.is_platform_admin == value:                       # sara 7b L6: no audited no-op — said before any confirm
        raise HTTPException(409, no_op)
    back = _require_confirm(db, user, new_kind, value, confirm_hash)
    if user.is_platform_admin == value:                       # re-read under the lock
        raise HTTPException(409, no_op)
    if user.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    detail = {"rationale": rationale}
    if not value:
        detail.update({"user_kind_from": user.user_kind, "user_kind": new_kind,
                       "comes_back": [r["project_id"] for r in back]})
        user.user_kind = new_kind
    user.is_platform_admin = value
    user.updated_by = actor.app_user_id
    audit.record(db, "PLATFORM_ADMIN_GRANTED" if value else "PLATFORM_ADMIN_REMOVED",
                 actor_id=actor.app_user_id, target_table="app_user", target_id=user_id,
                 detail=detail)
    db.commit()
    return user
