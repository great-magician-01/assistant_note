"""JWT token utilities, password hashing, and FastAPI auth dependency."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.user import User
from backend.apps.utils.config import settings
from backend.apps.utils.database import get_db


# Password hashing — using bcrypt directly (passlib has compat issues with bcrypt 5.x)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


# JWT token

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.ACCESS_JWT_SECRET, algorithm="HS256")


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.REFRESH_JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate an access token. Returns payload or None."""
    try:
        payload = jwt.decode(
            token, settings.ACCESS_JWT_SECRET, algorithms=["HS256"]
        )
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode and validate a refresh token. Returns payload or None."""
    try:
        payload = jwt.decode(
            token, settings.REFRESH_JWT_SECRET, algorithms=["HS256"]
        )
        if payload.get("type") != "refresh":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    FastAPI dependency: extract user from Authorization header.
    On success, also issues a fresh access token via X-Access-Token response header
    (sliding refresh — every valid request resets the 2h window).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = auth_header[7:]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if user is None or user.is_active != 1:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Sliding refresh: issue a new access token on every valid request
    new_access_token = create_access_token(user.user_id)

    # Attach the new token so the API layer can add it to response headers
    request.state.new_access_token = new_access_token

    return user
