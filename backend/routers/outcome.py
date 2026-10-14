"""
Outcome tracking router.

Exposes the measured change between two imports of the same workspace. This is the
one part of the API that reports what happened *after* the plan, rather than what
the plan proposes.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from services import outcome_service
from routers.auth import get_authorization_header, get_current_user
from routers.feedback import _verify_workspace_access

router = APIRouter(prefix="/api/outcome", tags=["outcome"])


async def _get_user_from_token(authorization: str) -> dict:
    """Extract and validate the current user from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.replace("Bearer ", "")
    return await get_current_user(token)


@router.get("/{workspace_id}/batches", response_model=List[Dict[str, Any]])
async def list_batches(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """List the imports this workspace's feedback arrived in, oldest first."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    return await outcome_service.list_batches(workspace_id)


@router.get("/{workspace_id}/compare", response_model=Dict[str, Any])
async def compare_imports(
    workspace_id: str,
    before: str = Query("", description="Batch id of the earlier import (default: second most recent)"),
    after: str = Query("", description="Batch id of the later import (default: most recent)"),
    max_themes: int = Query(8, ge=1, le=20, description="How many topics to compare"),
    authorization: str = Depends(get_authorization_header),
):
    """
    Compare two imports and report what measurably changed between them.

    Counts are normalised per 1,000 records, and a movement is only claimed when it
    clears the stated thresholds — otherwise the topic is reported as steady or as
    being short of evidence.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    try:
        return await outcome_service.build_comparison(
            workspace_id=workspace_id,
            before_batch_id=before or None,
            after_batch_id=after or None,
            max_themes=max_themes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{workspace_id}/export", response_class=PlainTextResponse)
async def export_comparison(
    workspace_id: str,
    before: str = Query("", description="Batch id of the earlier import"),
    after: str = Query("", description="Batch id of the later import"),
    authorization: str = Depends(get_authorization_header),
):
    """Export the comparison as raw GitHub-flavoured Markdown."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    try:
        comparison = await outcome_service.build_comparison(
            workspace_id=workspace_id,
            before_batch_id=before or None,
            after_batch_id=after or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return PlainTextResponse(
        content=outcome_service.build_markdown(comparison), media_type="text/markdown"
    )
