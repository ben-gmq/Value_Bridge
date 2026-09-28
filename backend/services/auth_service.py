"""Login and first-run setup (§7.10, scaffold §1)."""
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth.security import create_token, hash_password, verify_password
from models import AppUser
from services import audit
from services.user_admin import check_ftc_address

BAD_LOGIN = "Incorrect email or password"


def login(db: Session, email: str, password: str, remember_me: bool,
          source_ip: str | None) -> tuple[str, AppUser]:
    user = db.scalars(select(AppUser).where(func.lower(AppUser.email) == email.strip().lower())
                      ).one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        # Same message either way — never distinguish "no such user" from "wrong password".
        audit.record(db, "LOGIN_FAILED", detail={"email": email.strip().lower()},
                     source_ip=source_ip)
        db.commit()
        raise HTTPException(401, BAD_LOGIN)
    user.last_login_at = datetime.now(UTC)
    audit.record(db, "LOGIN_OK", actor_id=user.app_user_id, source_ip=source_ip)
    db.commit()
    return create_token(user.app_user_id, remember_me), user


def setup_required(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(AppUser)) == 0


def first_run_setup(db: Session, email: str, display_name: str, password: str) -> AppUser:
    """Creates the first platform admin. Permanently disabled once any user exists.
    The table lock stops two concurrent first-run requests both succeeding."""
    db.execute(select(func.pg_advisory_xact_lock(4242)))
    if not setup_required(db):
        raise HTTPException(409, "Setup is already complete")
    check_ftc_address(email)
    user = AppUser(email=email.strip(), display_name=display_name.strip(),
                   password_hash=hash_password(password), is_platform_admin=True)
    db.add(user)
    db.flush()
    audit.record(db, "FIRST_ADMIN_CREATED", actor_id=user.app_user_id,
                 target_table="app_user", target_id=user.app_user_id)
    db.commit()
    return user
