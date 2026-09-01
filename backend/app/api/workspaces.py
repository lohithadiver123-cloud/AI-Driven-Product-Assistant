"""Workspaces API router for multi-tenant workspace management."""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.database.collections import Collections
from app.database.connection import get_collection
from app.dependencies.auth import (
    get_current_user,
    get_user_workspace_context,
    require_role,
)
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceDetailResponse,
    WorkspaceMember,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceResponse,
)

logger = logging.getLogger("ai_product_assistant.api.workspaces")

router = APIRouter(prefix="/workspaces", tags=["Workspaces & Team Management"])


@router.get(
    "",
    response_model=List[WorkspaceResponse],
    summary="List user workspaces",
    description="Returns all workspaces where the current user is an owner or member.",
)
async def list_workspaces(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user["_id"]
    collection = get_collection(Collections.WORKSPACES)

    cursor = collection.find({
        "$or": [
            {"owner_id": user_id},
            {"members.user_id": user_id},
        ]
    }).sort("created_at", -1)

    items = []
    async for doc in cursor:
        doc_id = str(doc["_id"])
        # Determine role in this workspace
        role = "MEMBER"
        if str(doc.get("owner_id")) == user_id:
            role = "OWNER"
        else:
            for m in doc.get("members", []):
                if str(m.get("user_id")) == user_id:
                    role = m.get("role", "MEMBER")
                    break

        items.append(
            WorkspaceResponse(
                id=doc_id,
                name=doc["name"],
                owner_id=str(doc.get("owner_id")),
                member_count=len(doc.get("members", [])),
                current_user_role=role,
                created_at=doc.get("created_at", datetime.now(timezone.utc)),
            )
        )
    return items


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new workspace",
    description="Creates a new workspace with the authenticated user as the OWNER.",
)
async def create_workspace(
    req: WorkspaceCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = current_user["_id"]
    now = datetime.now(timezone.utc)
    collection = get_collection(Collections.WORKSPACES)

    doc = {
        "name": req.name.strip(),
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
    res = await collection.insert_one(doc)
    ws_id = str(res.inserted_id)

    # Add to user's workspace_ids
    users_collection = get_collection(Collections.USERS)
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"workspace_ids": ws_id}, "$set": {"current_workspace_id": ws_id}}
    )

    return WorkspaceResponse(
        id=ws_id,
        name=doc["name"],
        owner_id=user_id,
        member_count=1,
        current_user_role="OWNER",
        created_at=now,
    )


@router.get(
    "/current",
    response_model=WorkspaceDetailResponse,
    summary="Get active workspace details",
    description="Returns detailed info and member list for the current active workspace.",
)
async def get_current_workspace(ctx: Dict[str, Any] = Depends(get_user_workspace_context)):
    workspace = ctx["workspace"]
    user_role = ctx["role"]

    return WorkspaceDetailResponse(
        id=workspace["_id"],
        name=workspace["name"],
        owner_id=str(workspace["owner_id"]),
        members=[WorkspaceMember(**m) for m in workspace.get("members", [])],
        current_user_role=user_role,
        created_at=workspace.get("created_at", datetime.now(timezone.utc)),
        updated_at=workspace.get("updated_at", datetime.now(timezone.utc)),
    )


@router.post(
    "/switch/{workspace_id}",
    summary="Switch active workspace",
    description="Updates the user's active workspace session context.",
)
async def switch_workspace(
    workspace_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid workspace ID format.")

    user_id = current_user["_id"]
    collection = get_collection(Collections.WORKSPACES)
    ws = await collection.find_one({
        "_id": ObjectId(workspace_id),
        "$or": [{"owner_id": user_id}, {"members.user_id": user_id}]
    })

    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found or not accessible.")

    users_collection = get_collection(Collections.USERS)
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"current_workspace_id": workspace_id}}
    )
    return {
        "success": True,
        "message": f"Switched active workspace to '{ws.get('name')}'.",
        "workspace_id": workspace_id,
        "workspace_name": ws.get("name"),
    }


@router.post(
    "/members",
    summary="Add team member to workspace",
    description="Adds an existing user to the workspace. Requires OWNER or ADMIN role.",
)
async def add_workspace_member(
    req: WorkspaceMemberAdd,
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN"])),
):
    target_email = req.email.lower().strip()
    users_collection = get_collection(Collections.USERS)
    target_user = await users_collection.find_one({"email": target_email})

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No account found with email '{target_email}'. User must register first.",
        )

    target_id_str = str(target_user["_id"])
    workspace = ctx["workspace"]
    ws_id_str = ctx["workspace_id"]

    # Check if already a member
    for m in workspace.get("members", []):
        if str(m.get("user_id")) == target_id_str:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member of this workspace.")

    now = datetime.now(timezone.utc)
    new_member = {
        "user_id": target_id_str,
        "name": target_user.get("name"),
        "email": target_email,
        "role": req.role.upper(),
        "joined_at": now,
    }

    workspaces_collection = get_collection(Collections.WORKSPACES)
    await workspaces_collection.update_one(
        {"_id": ObjectId(ws_id_str)},
        {"$push": {"members": new_member}, "$set": {"updated_at": now}}
    )

    # Link workspace to user's profile
    await users_collection.update_one(
        {"_id": target_user["_id"]},
        {"$addToSet": {"workspace_ids": ws_id_str}}
    )

    return {
        "success": True,
        "message": f"Successfully added {target_user.get('name')} ({target_email}) to workspace as {req.role.upper()}.",
    }


@router.patch(
    "/members/{user_id}",
    summary="Update member role",
    description="Updates role for a workspace member. Requires OWNER or ADMIN role.",
)
async def update_member_role(
    user_id: str,
    req: WorkspaceMemberUpdate,
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN"])),
):
    workspace = ctx["workspace"]
    ws_id_str = ctx["workspace_id"]

    if str(workspace.get("owner_id")) == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change the role of the workspace OWNER.")

    workspaces_collection = get_collection(Collections.WORKSPACES)
    result = await workspaces_collection.update_one(
        {"_id": ObjectId(ws_id_str), "members.user_id": user_id},
        {"$set": {"members.$.role": req.role.upper(), "updated_at": datetime.now(timezone.utc)}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this workspace.")

    return {"success": True, "message": f"Updated member role to {req.role.upper()}."}


@router.delete(
    "/members/{user_id}",
    summary="Remove member from workspace",
    description="Removes a member from the workspace. Requires OWNER role.",
)
async def remove_member(
    user_id: str,
    ctx: Dict[str, Any] = Depends(require_role(["OWNER"])),
):
    workspace = ctx["workspace"]
    ws_id_str = ctx["workspace_id"]

    if str(workspace.get("owner_id")) == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the workspace OWNER.")

    workspaces_collection = get_collection(Collections.WORKSPACES)
    await workspaces_collection.update_one(
        {"_id": ObjectId(ws_id_str)},
        {"$pull": {"members": {"user_id": user_id}}, "$set": {"updated_at": datetime.now(timezone.utc)}}
    )

    if ObjectId.is_valid(user_id):
        users_collection = get_collection(Collections.USERS)
        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$pull": {"workspace_ids": ws_id_str}}
        )

    return {"success": True, "message": "Member removed from workspace."}
