"""Authentication API router: Register, Login, Refresh, Logout, Email Verification & Password Recovery."""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_settings
from app.database.collections import Collections
from app.database.connection import get_collection
from app.dependencies.auth import get_current_user, get_user_workspace_context
from app.schemas.auth import (
    ForgotPasswordRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
    ResendVerificationRequest,
)
from app.schemas.user import (
    ChangePasswordRequest,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
)
from app.services.email_service import email_service
from app.services.password_service import (
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.services.token_service import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    revoke_all_user_sessions,
    revoke_refresh_token,
    verify_and_rotate_refresh_token,
    verify_email_token,
    verify_password_reset_token,
)

logger = logging.getLogger("ai_product_assistant.api.auth")

router = APIRouter(prefix="/auth", tags=["Authentication & User Management"])


def _build_user_profile_response(user_doc: Dict[str, Any], workspace_doc: Optional[Dict[str, Any]] = None) -> UserProfileResponse:
    """Helper to safely format a user profile response."""
    ws_id = user_doc.get("current_workspace_id")
    ws_name = workspace_doc.get("name") if workspace_doc else None
    
    return UserProfileResponse(
        id=str(user_doc["_id"]),
        name=user_doc["name"],
        email=user_doc["email"],
        role=user_doc.get("role", "OWNER"),
        email_verified=user_doc.get("email_verified", False),
        workspace_ids=[str(w) for w in user_doc.get("workspace_ids", [])],
        current_workspace_id=str(ws_id) if ws_id else None,
        workspace_name=ws_name,
        is_active=user_doc.get("is_active", True),
        created_at=user_doc.get("created_at", datetime.now(timezone.utc)),
        last_login_at=user_doc.get("last_login_at"),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user & workspace",
    description="Registers a new user, provisions a default workspace, issues email verification token, and returns authenticated session.",
)
async def register(req: UserRegisterRequest):
    settings = get_settings()
    email_clean = req.email.lower().strip()

    # 1. Validation
    if req.password != req.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    is_valid_pw, pw_err = validate_password_strength(req.password)
    if not is_valid_pw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_err)

    users_collection = get_collection(Collections.USERS)
    existing_user = await users_collection.find_one({"email": email_clean})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists. Please sign in instead.",
        )

    now = datetime.now(timezone.utc)
    hashed_pw = hash_password(req.password)

    # 2. Insert User placeholder to obtain ID
    user_doc = {
        "name": req.name.strip(),
        "email": email_clean,
        "password_hash": hashed_pw,
        "role": "OWNER",
        "email_verified": False,
        "workspace_ids": [],
        "current_workspace_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "last_login_at": now,
    }
    user_res = await users_collection.insert_one(user_doc)
    user_id_str = str(user_res.inserted_id)

    # 3. Create Default Workspace
    ws_name = req.workspace_name.strip() if req.workspace_name and req.workspace_name.strip() else f"{req.name.strip()}'s Workspace"
    workspaces_collection = get_collection(Collections.WORKSPACES)
    workspace_doc = {
        "name": ws_name,
        "owner_id": user_id_str,
        "members": [{
            "user_id": user_id_str,
            "name": req.name.strip(),
            "email": email_clean,
            "role": "OWNER",
            "joined_at": now,
        }],
        "created_at": now,
        "updated_at": now,
    }
    ws_res = await workspaces_collection.insert_one(workspace_doc)
    ws_id_str = str(ws_res.inserted_id)

    # 4. Link Workspace to User
    await users_collection.update_one(
        {"_id": user_res.inserted_id},
        {
            "$set": {
                "workspace_ids": [ws_id_str],
                "current_workspace_id": ws_id_str,
            }
        }
    )
    user_doc["_id"] = user_id_str
    user_doc["workspace_ids"] = [ws_id_str]
    user_doc["current_workspace_id"] = ws_id_str
    workspace_doc["_id"] = ws_id_str

    # 5. Link Existing Sample Data to this initial workspace for seamless UX
    try:
        feedback_collection = get_collection(Collections.FEEDBACK)
        await feedback_collection.update_many(
            {"workspace_id": None},
            {"$set": {"workspace_id": ws_id_str}}
        )
        tickets_collection = get_collection(Collections.SUPPORT_TICKETS)
        await tickets_collection.update_many(
            {"workspace_id": None},
            {"$set": {"workspace_id": ws_id_str}}
        )
    except Exception as exc:
        logger.warning("Could not auto-link legacy sample data: %s", exc)

    # 6. Issue Verification Email
    try:
        verify_token = await create_email_verification_token(user_id_str)
        await email_service.send_verification_email(email_clean, req.name, verify_token)
    except Exception as exc:
        logger.error("Error creating/sending verification email: %s", exc)

    # 7. Issue Tokens
    access_token = create_access_token(
        user_id=user_id_str,
        email=email_clean,
        role="OWNER",
        workspace_id=ws_id_str,
    )
    raw_refresh_token, _ = await create_refresh_token(user_id_str, "Registration Session")

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_build_user_profile_response(user_doc, workspace_doc),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in with email and password",
    description="Authenticates user credentials, verifies account status, and returns access and refresh tokens.",
)
async def login(req: UserLoginRequest):
    settings = get_settings()
    email_clean = req.email.lower().strip()

    users_collection = get_collection(Collections.USERS)
    user = await users_collection.find_one({"email": email_clean})

    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact support.",
        )

    if settings.REQUIRE_EMAIL_VERIFICATION and not user.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before signing in. Check your inbox for the verification link.",
        )

    now = datetime.now(timezone.utc)
    user_id_str = str(user["_id"])

    # Update last login timestamp
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login_at": now}}
    )
    user["last_login_at"] = now
    user["_id"] = user_id_str

    # Fetch active workspace info
    workspaces_collection = get_collection(Collections.WORKSPACES)
    workspace = None
    ws_id = user.get("current_workspace_id")
    if ws_id and ObjectId.is_valid(ws_id):
        workspace = await workspaces_collection.find_one({"_id": ObjectId(ws_id)})
    if not workspace:
        workspace = await workspaces_collection.find_one({
            "$or": [{"owner_id": user_id_str}, {"members.user_id": user_id_str}]
        })
        if workspace:
            ws_id = str(workspace["_id"])
            await users_collection.update_one(
                {"_id": ObjectId(user_id_str)},
                {"$set": {"current_workspace_id": ws_id}}
            )
            user["current_workspace_id"] = ws_id

    role = user.get("role", "OWNER")
    access_token = create_access_token(
        user_id=user_id_str,
        email=email_clean,
        role=role,
        workspace_id=ws_id,
    )
    raw_refresh_token, _ = await create_refresh_token(user_id_str, req.device_info or "Browser Session")

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_build_user_profile_response(user, workspace),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Rotates the supplied refresh token and issues a new access token and new refresh token.",
)
async def refresh_token(req: RefreshTokenRequest):
    settings = get_settings()
    rotated = await verify_and_rotate_refresh_token(req.refresh_token)

    if not rotated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked refresh token. Please sign in again.",
        )

    user_id, new_raw_refresh, _ = rotated
    users_collection = get_collection(Collections.USERS)
    user = await users_collection.find_one({"_id": ObjectId(user_id)})

    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is no longer active.",
        )

    user["_id"] = str(user["_id"])
    ws_id = user.get("current_workspace_id")
    workspaces_collection = get_collection(Collections.WORKSPACES)
    workspace = None
    if ws_id and ObjectId.is_valid(ws_id):
        workspace = await workspaces_collection.find_one({"_id": ObjectId(ws_id)})

    access_token = create_access_token(
        user_id=user["_id"],
        email=user["email"],
        role=user.get("role", "OWNER"),
        workspace_id=ws_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_raw_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_build_user_profile_response(user, workspace),
    )


@router.post(
    "/logout",
    summary="Sign out user session",
    description="Revokes the active refresh token session.",
)
async def logout(req: RefreshTokenRequest):
    revoked = await revoke_refresh_token(req.refresh_token)
    return {
        "success": True,
        "message": "Successfully logged out and session revoked." if revoked else "Session was already closed.",
    }


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get current user profile",
    description="Returns the authenticated user's profile and active workspace information.",
)
async def get_me(ctx: Dict[str, Any] = Depends(get_user_workspace_context)):
    user = ctx["user"]
    workspace = ctx["workspace"]
    return _build_user_profile_response(user, workspace)


@router.post(
    "/verify-email",
    summary="Verify email address",
    description="Consumes an email verification token and marks the user's email as verified.",
)
async def verify_email(req: VerifyEmailRequest):
    user_id = await verify_email_token(req.token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already-used email verification token.",
        )

    users_collection = get_collection(Collections.USERS)
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"email_verified": True, "updated_at": datetime.now(timezone.utc)}}
    )
    return {
        "success": True,
        "message": "Email address has been successfully verified! You may now use all features.",
    }


@router.post(
    "/resend-verification",
    summary="Resend email verification link",
    description="Dispatches a fresh verification token to the user's email.",
)
async def resend_verification(req: ResendVerificationRequest):
    email_clean = req.email.lower().strip()
    users_collection = get_collection(Collections.USERS)
    user = await users_collection.find_one({"email": email_clean})

    if user and not user.get("email_verified", False):
        try:
            token = await create_email_verification_token(str(user["_id"]))
            await email_service.send_verification_email(email_clean, user.get("name", "User"), token)
        except Exception as exc:
            logger.error("Failed to resend verification email: %s", exc)

    return {
        "success": True,
        "message": "If an unverified account exists with that email, a new verification link has been sent.",
    }


@router.post(
    "/forgot-password",
    summary="Request password reset link",
    description="Initiates password reset process without revealing account existence.",
)
async def forgot_password(req: ForgotPasswordRequest):
    email_clean = req.email.lower().strip()
    users_collection = get_collection(Collections.USERS)
    user = await users_collection.find_one({"email": email_clean})

    if user and user.get("is_active", True):
        try:
            reset_token = await create_password_reset_token(str(user["_id"]))
            await email_service.send_password_reset_email(email_clean, user.get("name", "User"), reset_token)
        except Exception as exc:
            logger.error("Failed to dispatch password reset email: %s", exc)

    # Anti-enumeration response: always return success
    return {
        "success": True,
        "message": "If an account with that email exists, a password reset link has been dispatched.",
    }


@router.post(
    "/reset-password",
    summary="Consume password reset token",
    description="Sets a new password using a valid single-use reset token and revokes previous sessions.",
)
async def reset_password(req: ResetPasswordRequest):
    if req.new_password != req.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    is_valid_pw, pw_err = validate_password_strength(req.new_password)
    if not is_valid_pw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_err)

    user_id = await verify_password_reset_token(req.token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already-used password reset token. Please request a new link.",
        )

    hashed_pw = hash_password(req.new_password)
    now = datetime.now(timezone.utc)
    users_collection = get_collection(Collections.USERS)

    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": hashed_pw, "updated_at": now}}
    )

    # Invalidate all active user sessions for security
    await revoke_all_user_sessions(user_id)

    return {
        "success": True,
        "message": "Your password has been successfully reset. Please sign in with your new password.",
    }


@router.post(
    "/change-password",
    summary="Change password for authenticated user",
    description="Allows an authenticated user to change their password upon confirming their current password.",
)
async def change_password(
    req: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if req.new_password != req.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match.",
        )

    is_valid_pw, pw_err = validate_password_strength(req.new_password)
    if not is_valid_pw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_err)

    if not verify_password(req.current_password, current_user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password entered is incorrect.",
        )

    hashed_pw = hash_password(req.new_password)
    now = datetime.now(timezone.utc)
    users_collection = get_collection(Collections.USERS)

    user_id_raw = current_user["_id"]
    user_obj_id = ObjectId(user_id_raw) if isinstance(user_id_raw, str) and ObjectId.is_valid(user_id_raw) else user_id_raw

    await users_collection.update_one(
        {"_id": user_obj_id},
        {"$set": {"password_hash": hashed_pw, "updated_at": now}}
    )

    # Revoke all sessions so the user re-authenticates with the new password
    await revoke_all_user_sessions(str(user_id_raw))

    return {
        "success": True,
        "message": "Password changed successfully. Please log in again with your new credentials.",
    }
