"""
Password hashing and JWT helpers.

Passwords are hashed with bcrypt (via passlib) -- never stored or logged in
plaintext. JWTs are signed with HS256 using SECRET_KEY (env-configurable,
never hardcoded -- see .env.example). This module has no FastAPI
dependencies of its own; app/core/deps.py wires it into request handling.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.time import utc_now

settings = get_settings()
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    """Create a signed JWT whose `sub` claim is the user's id (as a string)."""
    expire = utc_now() + dt.timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Return the `sub` claim (user id as string) if `token` is valid, else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
