"""current_user — the per-request dependency. Re-reads the user every request (finding S4),
so deactivating someone takes effect on their very next call."""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from auth.security import decode_token
from database import get_db
from models import AppUser

_bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> AppUser:
    user_id = decode_token(creds.credentials) if creds else None
    user = db.get(AppUser, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(401, "Not authenticated")
    return user
