"""Password hashing and JWT. The token carries the SUBJECT ONLY (finding S4): no role, no
admin flag — both are re-read from the database on every request."""
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from config import get_settings

ALGORITHM = "HS256"


def _pw(password: str) -> bytes:
    # bcrypt reads at most 72 bytes; truncate explicitly rather than reject (FTC-PC landmine 7).
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pw(password), password_hash.encode())
    except ValueError:
        return False


def create_token(user_id: int, remember_me: bool) -> str:
    s = get_settings()
    days = s.token_days_remember if remember_me else s.token_days_default
    exp = datetime.now(UTC) + timedelta(days=days)
    return jwt.encode({"sub": str(user_id), "exp": exp}, s.jwt_secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret_key, algorithms=[ALGORITHM],
                            options={"require": ["sub", "exp"]})
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
