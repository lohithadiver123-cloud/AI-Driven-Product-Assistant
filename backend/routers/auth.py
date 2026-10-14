"""
Authentication router.
Handles user registration and login with JWT token generation.
Falls back to JSON database if MongoDB is unavailable.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from jose import JWTError, jwt
import database
from fallback_db import (
    find_user_by_email as fb_find_user_by_email,
    find_user_by_id as fb_find_user_by_id,
    create_user as fb_create_user,
)
from models.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    UserInDB,
)
from config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


async def get_authorization_header(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """Return a validated Bearer header value for protected endpoints."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    return f"{credentials.scheme} {credentials.credentials}"

# Password hashing context for legacy bcrypt hashes.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
PBKDF2_ITERATIONS = 600_000


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a stored password hash."""
    if hashed_password.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, expected_hash = hashed_password.split("$", 3)
            derived = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                base64.b64decode(salt.encode("ascii")),
                int(iterations),
            )
            actual_hash = base64.b64encode(derived).decode("ascii")
            return hmac.compare_digest(actual_hash, expected_hash)
        except (ValueError, TypeError):
            return False

    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate a PBKDF2-SHA256 hash for a plain password."""
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(derived).decode('ascii')}"
    )


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Create a JWT access token.
    Encodes the data payload with an expiration time.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    Returns the payload or raises an HTTPException on invalid/expired token.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no subject",
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


import time
_user_token_cache: dict = {}  # token -> (user_dict, expiry)


async def get_current_user(token: str) -> dict:
    """
    Dependency: extract and return the current user from a JWT token.
    Uses in-memory 60s cache to avoid redundant database roundtrips on rapid tab switches.
    """
    now = time.time()
    cached_entry = _user_token_cache.get(token)
    if cached_entry and cached_entry[1] > now:
        return cached_entry[0]

    payload = decode_token(token)
    user_id = payload["sub"]

    user = None
    
    # Try MongoDB first
    if database._mongodb_available:
        try:
            from bson import ObjectId
            user = await database.db.users.find_one({"_id": ObjectId(user_id)})
            if user:
                user["_id"] = str(user["_id"])
        except:
            pass
    
    # Fall back to JSON database
    if user is None:
        user = await fb_find_user_by_id(user_id)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Cache for 60 seconds
    if len(_user_token_cache) > 500:
        _user_token_cache.clear()
    _user_token_cache[token] = (user, now + 60.0)

    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """
    Register a new user.
    Checks for duplicate email, hashes password, stores user, and returns user data.
    Falls back to JSON database if MongoDB is unavailable.
    """
    email_clean = user_data.email.strip().lower()
    
    # Check if email is already registered
    existing = None
    
    if database._mongodb_available:
        try:
            existing = await database.db.users.find_one({"email": email_clean})
        except:
            pass
    
    if existing is None:
        existing = await fb_find_user_by_email(email_clean)
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Hash the password
    password_hash = get_password_hash(user_data.password)

    # Prepare user data
    user_data_dict = {
        "name": user_data.name.strip(),
        "email": email_clean,
        "password_hash": password_hash,
    }

    # Try MongoDB first
    if database._mongodb_available:
        try:
            user_doc = UserInDB(**user_data_dict)
            result = await database.db.users.insert_one(user_doc.model_dump(by_alias=False, exclude_none=True))
            created_user = await database.db.users.find_one({"_id": result.inserted_id})
            created_user["_id"] = str(created_user["_id"])
            return created_user
        except:
            pass
    
    # Fall back to JSON database
    created_user = await fb_create_user(user_data_dict)
    return created_user


@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    """
    Authenticate a user and return a JWT token.
    Verifies credentials and returns an access token with user data.
    Falls back to JSON database if MongoDB is unavailable.
    """
    email_clean = user_data.email.strip().lower()
    
    # Find user by email
    user = None
    
    if database._mongodb_available:
        try:
            user = await database.db.users.find_one({"email": email_clean})
            if user:
                user["_id"] = str(user["_id"])
        except:
            pass
    
    if user is None:
        user = await fb_find_user_by_email(email_clean)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify password
    if not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Create JWT token
    token_data = {"sub": str(user["_id"])}
    access_token = create_access_token(token_data)

    # Prepare user response data
    user_response = user.copy()
    user_response.pop("password_hash", None)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_response,
    }
