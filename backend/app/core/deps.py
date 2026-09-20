"""
FastAPI dependencies for authentication.

`get_current_user` is used by endpoints that require a logged-in user
(projects, analysis history). `get_current_user_optional` is used by
POST /api/analyze, which stays usable anonymously (Phase 1/2 behavior is
preserved) but persists results when a valid token *is* provided.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.user import User

# tokenUrl is documentation-only (drives the Swagger "Authorize" button);
# the actual route is registered in app/api/auth.py.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _resolve_user(token: Optional[str], db: Session) -> Optional[User]:
    if not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    return db.get(User, int(user_id))


def get_current_user(
    token: Optional[str] = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = _resolve_user(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_optional(
    token: Optional[str] = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Anonymous access is allowed (no token at all), but a *provided*
    token must be valid -- an expired/malformed token fails loudly instead
    of silently downgrading to "anonymous", which would hide the real
    problem from the caller.
    """
    if token is None:
        return None
    user = _resolve_user(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
