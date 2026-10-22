"""
backend/api/auth.py
Stateless HMAC-signed session tokens and API authorization dependencies (E4).
Supports multi-worker server deployment, role-based access control, and scoped demo access.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Literal, Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from backend.config import settings


def create_session_token(role: str, user_id: str = "recruiter") -> str:
    """Generate a tamper-proof HMAC-SHA256 signed session token."""
    payload = {
        "role": role,
        "user_id": user_id,
        "exp": int(time.time()) + 43200,  # 12 hours
        "nonce": secrets.token_hex(8),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_session_token(token: str) -> Optional[dict]:
    """Verify HMAC signature and expiration of a session token."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(
            settings.auth_secret_key.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not secrets.compare_digest(signature, expected_sig):
            return None

        # Pad base64 if needed
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        if payload.get("exp", 0) < time.time():
            return None  # Expired
        return payload
    except Exception:
        return None


async def get_current_user(
    request: Request,
    atos_workspace: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> dict:
    """
    Authenticate caller via Cookie or Authorization header.
    Enforces authorization at API boundaries according to configuration.
    """
    token = atos_workspace
    if not token and authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()

    if token:
        user = verify_session_token(token)
        if user:
            return user

    # If auth is strictly required and no valid token is provided
    if settings.auth_required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # In test / dev mode when auth_required is False
    return {"role": "admin", "user_id": "default_dev", "dev": True}


def require_role(min_role: Literal["admin", "user"]):
    """Dependency that enforces minimum role requirement (admin > user)."""
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role")
        if min_role == "admin" and role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin role required.",
            )
        return user
    return role_checker
