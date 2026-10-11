"""User administration (§7.10). Platform admin only — enforced by the route guard."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.security import hash_password
from config import get_settings
from models import AppUser
from services import audit
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


def set_user_kind(db: Session, actor: AppUser, user_id: int, user_kind: str, row_version: int) -> AppUser:
    """D-40 (§8.2): platform admin, audited, optimistic lock. Takes effect on the next request."""
    user = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(404, "Not found")
    if user.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if user.user_kind != _kind(user_kind):
        old, user.user_kind = user.user_kind, user_kind
        user.updated_by = actor.app_user_id
        audit.record(db, "USER_KIND_CHANGED", actor_id=actor.app_user_id, target_table="app_user",
                     target_id=user_id, detail={"from": old, "to": user_kind})
    db.commit()
    return user


def set_platform_admin(db: Session, actor: AppUser, user_id: int, value: bool, rationale: str,
                       row_version: int, user_kind: str | None = None) -> AppUser:
    """Grant or remove platform-admin rights (M7). Audited with a reason, because an admin
    sees every client's data. Removing them requires the kind the user falls back to, so a
    demoted admin never silently becomes an editor everywhere (DR7-S6)."""
    user = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(404, "Not found")
    if user.app_user_id == actor.app_user_id:
        raise HTTPException(422, "You cannot change your own administrator rights")
    if user.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if not rationale.strip():
        raise HTTPException(422, "Changing administrator rights needs a reason")
    if user.is_platform_admin == value:                       # sara 7b L6: no audited no-op
        raise HTTPException(409, f"{user.display_name} is {'already' if value else 'not'} an administrator")
    detail = {"rationale": rationale}
    if not value:
        if user_kind is None:
            raise HTTPException(422, "Say what the user becomes: user_kind USER or VIEWER")
        detail.update({"user_kind_from": user.user_kind, "user_kind": _kind(user_kind)})
        user.user_kind = user_kind
    user.is_platform_admin = value
    user.updated_by = actor.app_user_id
    audit.record(db, "PLATFORM_ADMIN_GRANTED" if value else "PLATFORM_ADMIN_REMOVED",
                 actor_id=actor.app_user_id, target_table="app_user", target_id=user_id,
                 detail=detail)
    db.commit()
    return user
