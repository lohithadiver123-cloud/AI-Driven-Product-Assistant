from typing import Optional
from bson import ObjectId
from ..db import get_collections
from ..security import get_password_hash, verify_password, create_access_token
from datetime import timedelta


async def create_user(name: str, email: str, password: str) -> dict:
    cols = get_collections()
    users = cols["users"]
    workspaces = cols["workspaces"]

    existing = await users.find_one({"email": email})
    if existing:
        raise ValueError("User with this email already exists")

    # create workspace
    ws_doc = {"name": f"{name}'s workspace", "owner_id": None, "created_at": None}
    ws_res = await workspaces.insert_one(ws_doc)
    workspace_id = str(ws_res.inserted_id)

    hashed = get_password_hash(password)
    user_doc = {
        "name": name,
        "email": email,
        "password_hash": hashed,
        "workspace_id": workspace_id,
        "created_at": None,
    }
    user_res = await users.insert_one(user_doc)

    # update workspace owner
    await workspaces.update_one({"_id": ObjectId(workspace_id)}, {"$set": {"owner_id": str(user_res.inserted_id)}})

    token = create_access_token(subject=str(user_res.inserted_id), expires_delta=timedelta(days=7))

    return {"user": {"id": str(user_res.inserted_id), "email": email, "name": name, "workspace_id": workspace_id}, "token": token}


async def authenticate_user(email: str, password: str) -> Optional[dict]:
    cols = get_collections()
    users = cols["users"]
    user = await users.find_one({"email": email})
    if not user:
        return None
    if not verify_password(password, user.get("password_hash")):
        return None
    token = create_access_token(subject=str(user.get("_id") or user.get("_id")), expires_delta=timedelta(days=7))
    return {"user": {"id": str(user.get("_id") or user.get("_id")), "email": user.get("email"), "name": user.get("name"), "workspace_id": user.get("workspace_id")}, "token": token}
