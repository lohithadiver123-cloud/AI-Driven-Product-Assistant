"""JWT and Cryptographic Token Service."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
import jwt
from bson import ObjectId

from app.config import get_settings
from app.database.collections import Collections
from app.database.connection import get_collection

logger = logging.getLogger("ai_product_assistant.tokens")


def hash_token(raw_token: str) -> str:
    """Hash a token using SHA-256 for secure database storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# JWT Access Tokens
# ----------------------------------------------------------------------
def create_access_token(
    user_id: str,
    email: str,
    role: str = "OWNER",
    workspace_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token containing safe user claims."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email.lower().strip(),
        "role": role,
        "workspace_id": str(workspace_id) if workspace_id else None,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT access token.
    
    Raises:
        jwt.ExpiredSignatureError: If token is expired.
        jwt.InvalidTokenError: If token is malformed or signature invalid.
    """
    settings = get_settings()
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Token type is not 'access'.")

    return payload


# ----------------------------------------------------------------------
# Refresh Tokens (Stored hashed in MongoDB)
# ----------------------------------------------------------------------
async def create_refresh_token(
    user_id: str,
    device_info: Optional[str] = "Browser Session",
) -> Tuple[str, datetime]:
    """
    Generate a cryptographic refresh token, store its hash in MongoDB, and return the raw token.
    """
    settings = get_settings()
    raw_token = secrets.token_urlsafe(48)
    token_hash_val = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    collection = get_collection(Collections.REFRESH_TOKENS)
    doc = {
        "user_id": str(user_id),
        "token_hash": token_hash_val,
        "device_info": device_info,
        "expires_at": expires_at,
        "revoked_at": None,
        "created_at": now,
    }
    await collection.insert_one(doc)
    return raw_token, expires_at


async def verify_and_rotate_refresh_token(raw_token: str) -> Optional[Tuple[str, str, datetime]]:
    """
    Validate an incoming refresh token, revoke it, and generate a new rotated refresh token.
    
    Returns:
        (user_id, new_raw_token, new_expires_at) or None if invalid/expired/revoked.
    """
    if not raw_token:
        return None

    token_hash_val = hash_token(raw_token)
    collection = get_collection(Collections.REFRESH_TOKENS)
    doc = await collection.find_one({"token_hash": token_hash_val})

    if not doc:
        return None

    now = datetime.now(timezone.utc)
    expires_at = doc.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    # Check expiration or prior revocation
    if doc.get("revoked_at") is not None or (expires_at and expires_at < now):
        return None

    # Revoke current token (single-use rotation)
    await collection.update_one(
        {"_id": doc["_id"]},
        {"$set": {"revoked_at": now}}
    )

    # Issue new rotated refresh token
    user_id = doc["user_id"]
    new_raw, new_exp = await create_refresh_token(user_id, doc.get("device_info"))
    return user_id, new_raw, new_exp


async def revoke_refresh_token(raw_token: str) -> bool:
    """Revoke a specific active refresh token (e.g. on logout)."""
    if not raw_token:
        return False
    token_hash_val = hash_token(raw_token)
    collection = get_collection(Collections.REFRESH_TOKENS)
    now = datetime.now(timezone.utc)
    result = await collection.update_one(
        {"token_hash": token_hash_val, "revoked_at": None},
        {"$set": {"revoked_at": now}}
    )
    return result.modified_count > 0


async def revoke_all_user_sessions(user_id: str) -> int:
    """Revoke all active refresh tokens for a user (e.g. on password reset)."""
    collection = get_collection(Collections.REFRESH_TOKENS)
    now = datetime.now(timezone.utc)
    result = await collection.update_many(
        {"user_id": str(user_id), "revoked_at": None},
        {"$set": {"revoked_at": now}}
    )
    return result.modified_count


# ----------------------------------------------------------------------
# Email Verification Tokens
# ----------------------------------------------------------------------
async def create_email_verification_token(user_id: str) -> str:
    """Generate and persist an email verification token."""
    settings = get_settings()
    raw_token = secrets.token_urlsafe(32)
    token_hash_val = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)

    collection = get_collection(Collections.EMAIL_VERIFICATION_TOKENS)
    # Invalidate previous unused verification tokens for this user
    await collection.update_many(
        {"user_id": str(user_id), "used_at": None},
        {"$set": {"used_at": now}}
    )

    doc = {
        "user_id": str(user_id),
        "token_hash": token_hash_val,
        "expires_at": expires_at,
        "used_at": None,
        "created_at": now,
    }
    await collection.insert_one(doc)
    return raw_token


async def verify_email_token(raw_token: str) -> Optional[str]:
    """
    Validate an email verification token and mark it used.
    
    Returns:
        user_id if valid, else None.
    """
    if not raw_token:
        return None
    token_hash_val = hash_token(raw_token)
    collection = get_collection(Collections.EMAIL_VERIFICATION_TOKENS)
    doc = await collection.find_one({"token_hash": token_hash_val})

    if not doc or doc.get("used_at") is not None:
        return None

    now = datetime.now(timezone.utc)
    expires_at = doc.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at < now:
        return None

    # Mark token used
    await collection.update_one(
        {"_id": doc["_id"]},
        {"$set": {"used_at": now}}
    )
    return doc["user_id"]


# ----------------------------------------------------------------------
# Password Reset Tokens
# ----------------------------------------------------------------------
async def create_password_reset_token(user_id: str) -> str:
    """Generate and persist a single-use password reset token."""
    settings = get_settings()
    raw_token = secrets.token_urlsafe(32)
    token_hash_val = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)

    collection = get_collection(Collections.PASSWORD_RESET_TOKENS)
    # Invalidate older pending reset tokens
    await collection.update_many(
        {"user_id": str(user_id), "used_at": None},
        {"$set": {"used_at": now}}
    )

    doc = {
        "user_id": str(user_id),
        "token_hash": token_hash_val,
        "expires_at": expires_at,
        "used_at": None,
        "created_at": now,
    }
    await collection.insert_one(doc)
    return raw_token


async def verify_password_reset_token(raw_token: str) -> Optional[str]:
    """
    Validate a password reset token and mark it as consumed.
    
    Returns:
        user_id if valid, else None.
    """
    if not raw_token:
        return None
    token_hash_val = hash_token(raw_token)
    collection = get_collection(Collections.PASSWORD_RESET_TOKENS)
    doc = await collection.find_one({"token_hash": token_hash_val})

    if not doc or doc.get("used_at") is not None:
        return None

    now = datetime.now(timezone.utc)
    expires_at = doc.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at < now:
        return None

    # Consume token
    await collection.update_one(
        {"_id": doc["_id"]},
        {"$set": {"used_at": now}}
    )
    return doc["user_id"]
