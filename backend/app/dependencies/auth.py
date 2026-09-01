"""FastAPI authentication and authorization dependencies."""
import logging
from typing import Any, Callable, Dict, List, Optional
from bson import ObjectId
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from app.database.collections import Collections
from app.database.connection import get_collection
from app.services.token_service import decode_access_token

logger = logging.getLogger("ai_product_assistant.auth")

security_bearer = HTTPBearer(auto_error=False)

ROLE_HIERARCHY = {
    "OWNER": 4,
    "ADMIN": 3,
    "MEMBER": 2,
    "VIEWER": 1,
}


async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> Dict[str, Any]:
    """
    Extract, decode, and validate the JWT Bearer access token.
    
    Returns:
        User document dictionary with string '_id'.
    """
    if not auth_header or not auth_header.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.credentials.strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please refresh your session or log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token identity payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    users_collection = get_collection(Collections.USERS)
    user = await users_collection.find_one({"_id": ObjectId(user_id)})

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has been deactivated. Please contact an administrator.",
        )

    user["_id"] = str(user["_id"])
    return user


async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Dependency verifying the user is fully active."""
    return current_user


async def get_user_workspace_context(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Resolve the active workspace document and effective role for the current user.
    """
    user_id = current_user["_id"]
    current_ws_id = current_user.get("current_workspace_id")

    workspaces_collection = get_collection(Collections.WORKSPACES)
    workspace = None

    if current_ws_id and ObjectId.is_valid(current_ws_id):
        workspace = await workspaces_collection.find_one({
            "_id": ObjectId(current_ws_id),
            "$or": [
                {"owner_id": user_id},
                {"members.user_id": user_id},
            ]
        })

    if not workspace:
        # Fallback to the first available workspace for this user
        workspace = await workspaces_collection.find_one({
            "$or": [
                {"owner_id": user_id},
                {"members.user_id": user_id},
            ]
        })

    if not workspace:
        # Auto-provision a default personal workspace if none exists
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        ws_name = f"{current_user.get('name', 'My')}'s Workspace"
        new_ws_doc = {
            "name": ws_name,
            "owner_id": user_id,
            "members": [{
                "user_id": user_id,
                "name": current_user.get("name"),
                "email": current_user.get("email"),
                "role": "OWNER",
                "joined_at": now,
            }],
            "created_at": now,
            "updated_at": now,
        }
        res = await workspaces_collection.insert_one(new_ws_doc)
        workspace = new_ws_doc
        workspace["_id"] = res.inserted_id

        # Update user record
        users_collection = get_collection(Collections.USERS)
        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$addToSet": {"workspace_ids": str(res.inserted_id)},
                "$set": {"current_workspace_id": str(res.inserted_id), "role": "OWNER"}
            }
        )

    workspace["_id"] = str(workspace["_id"])

    # Determine effective role in this workspace
    effective_role = "MEMBER"
    if str(workspace.get("owner_id")) == user_id:
        effective_role = "OWNER"
    else:
        for m in workspace.get("members", []):
            if str(m.get("user_id")) == user_id:
                effective_role = m.get("role", "MEMBER")
                break

    return {
        "user": current_user,
        "workspace": workspace,
        "workspace_id": workspace["_id"],
        "role": effective_role,
    }


def require_role(allowed_roles: List[str]) -> Callable:
    """
    Factory dependency requiring the user's workspace role to be one of allowed_roles.
    
    Example:
        @router.delete('/dataset', dependencies=[Depends(require_role(['OWNER', 'ADMIN']))])
    """
    async def role_checker(
        ctx: Dict[str, Any] = Depends(get_user_workspace_context),
    ) -> Dict[str, Any]:
        user_role = ctx.get("role", "VIEWER").upper()
        allowed = [r.upper() for r in allowed_roles]

        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {', '.join(allowed_roles)}. Your current role is {user_role}.",
            )
        return ctx

    return role_checker
