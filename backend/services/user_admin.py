"""User administration (§7.10). Platform admin only — enforced by the route guard."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.security import hash_password
from config import get_settings
from models import AppUser
from services import audit

MIN_PASSWORD = 10


def check_ftc_address(email: str) -> None:
    """D-11: every account is FTC staff. Client-side people are stakeholders, not users."""
    domain = email.strip().lower().rpartition("@")[2]
    if "@" not in email or domain not in get_settings().email_domains:
        raise HTTPException(422, "Value Bridge accounts are FTC staff only. Client-side people "
                                 "are recorded as stakeholders.")


def list_users(db: Session) -> list[AppUser]:
    return list(db.scalars(select(AppUser).order_by(AppUser.display_name)))


def create_user(db: Session, actor: AppUser, email: str, display_name: str,
                initial_password: str, is_platform_admin: bool = False) -> AppUser:
    check_ftc_address(email)
    if len(initial_password) < MIN_PASSWORD:
        raise HTTPException(422, f"The password must be at least {MIN_PASSWORD} characters")
    user = AppUser(email=email.strip(), display_name=display_name.strip(),
                   password_hash=hash_password(initial_password),
                   is_platform_admin=is_platform_admin, created_by=actor.app_user_id)
    db.add(user)
    db.flush()
    audit.record(db, "USER_CREATED", actor_id=actor.app_user_id, target_table="app_user",
                 target_id=user.app_user_id,
                 detail={"email": user.email, "is_platform_admin": is_platform_admin})
    db.commit()
    return user   # the plaintext password is never persisted, logged or returned


def deactivate_user(db: Session, actor: AppUser, user_id: int) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(404, "Not found")
    if user.app_user_id == actor.app_user_id:
        raise HTTPException(422, "You cannot deactivate your own account")
    user.is_active = False
    audit.record(db, "USER_DEACTIVATED", actor_id=actor.app_user_id, target_table="app_user",
                 target_id=user_id)
    db.commit()
    return user   # effective on the target's next request — current_user re-reads the row
