"""
Shared read helpers for the Milestone 4 planning and reporting services.

The roadmap, report and quality services all need the same picture of a workspace:
its stored insights, its prioritised backlog, the documents already generated from
it, and how much feedback is behind the whole thing. Loading that picture in one
place keeps every planner honest — they all read the same measured numbers instead
of each re-deriving their own.
"""

from typing import Any, Dict, List, Optional

import database
from database import db
import fallback_db
from services.prioritization_service import normalise_prioritization_item


async def load_stored_insights(workspace_id: str) -> Optional[Dict[str, Any]]:
    """Return the stored Milestone 2 analysis for a workspace, if one exists."""
    if database._mongodb_available:
        cached = await db.workspace_insights.find_one({"workspace_id": workspace_id})
        if cached and "_id" in cached:
            cached["_id"] = str(cached["_id"])
        return cached
    return await fallback_db.get_workspace_insights(workspace_id)


async def resolve_workspace(workspace_id: str, insights: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    Resolve the workspace's display name and description.

    The stored insights carry the name the analysis was run under, which is the
    most reliable source; the workspace document is the fallback.
    """
    name = (insights or {}).get("workspace_name") or ""
    description = ""

    if database._mongodb_available:
        workspace = None
        try:
            from bson import ObjectId
            workspace = await db.workspaces.find_one({"_id": ObjectId(workspace_id)})
        except Exception:
            workspace = None
        if not workspace:
            workspace = await db.workspaces.find_one({"_id": workspace_id})
        if workspace:
            name = name or workspace.get("name") or ""
            description = workspace.get("description") or ""
    else:
        workspace = await fallback_db.find_workspace_by_id(workspace_id)
        if workspace:
            name = name or workspace.get("name") or ""
            description = workspace.get("description") or ""

    return {"name": name or "Workspace", "description": description}


async def load_prioritization_items(workspace_id: str) -> List[Dict[str, Any]]:
    """Return every prioritization item for a workspace, ranked and canonically shaped."""
    if database._mongodb_available:
        cursor = db.prioritization_items.find({"workspace_id": workspace_id}).sort("rank", 1)
        items = await cursor.to_list(length=None)
        for item in items:
            if "_id" in item:
                item["_id"] = str(item["_id"])
            normalise_prioritization_item(item)
        return items
    items = await fallback_db.find_prioritization_items_by_workspace(workspace_id)
    for item in items:
        normalise_prioritization_item(item)
    return sorted(items, key=lambda item: item.get("rank") or 0)


async def load_prds(workspace_id: str) -> List[Dict[str, Any]]:
    """Return every generated PRD for a workspace."""
    if database._mongodb_available:
        cursor = db.prds.find({"workspace_id": workspace_id}).sort("created_at", -1)
        return await cursor.to_list(length=None)
    return await fallback_db.find_prds_by_workspace(workspace_id)


async def load_user_stories(workspace_id: str) -> List[Dict[str, Any]]:
    """Return every generated user story for a workspace."""
    if database._mongodb_available:
        cursor = db.user_stories.find({"workspace_id": workspace_id})
        return await cursor.to_list(length=None)
    return await fallback_db.find_stories_by_workspace(workspace_id)


async def count_feedback(workspace_id: str) -> int:
    """Count the feedback records actually stored against a workspace."""
    if database._mongodb_available:
        return int(await db.feedback.count_documents({"workspace_id": workspace_id}))
    return len(await fallback_db.find_all_feedback_by_workspace(workspace_id))
