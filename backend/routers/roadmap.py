"""
Roadmap Planning Router for Milestone 4.
Provides endpoints for:
- Generating a roadmap and recommended milestones from the prioritised backlog
- Reading, rescheduling and deleting the workspace roadmap
- Exporting the roadmap as Markdown
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from models.roadmap import RoadmapGenerateRequest
from services import roadmap_service
from routers.auth import get_authorization_header, get_current_user
from routers.feedback import _verify_workspace_access

router = APIRouter(prefix="/api/roadmap", tags=["roadmap"])


class RoadmapRescheduleRequest(BaseModel):
    """Move one initiative into another release window."""

    target_release_index: int = Field(..., ge=0, le=12, description="Zero-based release window to move the item into")


async def _get_user_from_token(authorization: str) -> dict:
    """Extract and validate the current user from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.replace("Bearer ", "")
    return await get_current_user(token)


@router.post("/generate", response_model=Dict[str, Any])
async def generate_roadmap(
    payload: RoadmapGenerateRequest,
    authorization: str = Depends(get_authorization_header),
):
    """
    Generate a roadmap for a workspace: sequence its prioritised backlog into release
    windows and recommend the milestones inside each one.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(payload.workspace_id, user)

    try:
        return await roadmap_service.generate_roadmap(
            workspace_id=payload.workspace_id,
            horizon_weeks=payload.horizon_weeks,
            velocity=payload.velocity,
            focus=payload.focus,
            include_items=payload.include_items,
            replace_existing=payload.replace_existing,
        )
    except Exception as exc:  # noqa: BLE001 - surface the failure as a 500, as the PRD route does
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Roadmap generation failed: {str(exc)}",
        )


@router.get("/{workspace_id}", response_model=Dict[str, Any])
async def get_roadmap(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Return the stored roadmap for a workspace, if one exists."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    roadmap = await roadmap_service.get_roadmap(workspace_id)
    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No roadmap has been generated for this workspace yet",
        )
    return roadmap


@router.patch("/{workspace_id}/items/{item_id}", response_model=Dict[str, Any])
async def reschedule_roadmap_item(
    workspace_id: str,
    item_id: str,
    payload: RoadmapRescheduleRequest,
    authorization: str = Depends(get_authorization_header),
):
    """Move an initiative into another release window and rebuild the plan around it."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    updated = await roadmap_service.reschedule_item(workspace_id, item_id, payload.target_release_index)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roadmap or initiative not found",
        )
    return updated


@router.delete("/{workspace_id}")
async def delete_roadmap(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Delete the stored roadmap for a workspace."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    deleted = await roadmap_service.delete_roadmap(workspace_id)
    return {"success": deleted, "workspace_id": workspace_id}


@router.get("/{workspace_id}/export", response_class=PlainTextResponse)
async def export_roadmap_markdown(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Export the roadmap as raw GitHub-flavoured Markdown."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    roadmap = await roadmap_service.get_roadmap(workspace_id)
    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No roadmap has been generated for this workspace yet",
        )
    markdown = roadmap.get("raw_markdown") or roadmap_service._build_markdown_from_roadmap(roadmap)
    return PlainTextResponse(content=markdown, media_type="text/markdown")
