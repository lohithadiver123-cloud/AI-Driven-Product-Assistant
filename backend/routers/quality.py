"""
Output Quality Evaluation Router for Milestone 4.
Provides endpoints for:
- Scoring every generated artefact in a workspace against verifiable checks
- Exporting the evaluation as Markdown
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from services import quality_service
from routers.auth import get_authorization_header, get_current_user
from routers.feedback import _verify_workspace_access

router = APIRouter(prefix="/api/quality", tags=["quality"])


async def _get_user_from_token(authorization: str) -> dict:
    """Extract and validate the current user from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.replace("Bearer ", "")
    return await get_current_user(token)


@router.get("/{workspace_id}/evaluate", response_model=Dict[str, Any])
async def evaluate_output_quality(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """
    Evaluate the quality of everything generated for a workspace.

    Checks completeness, evidence grounding, freshness and internal consistency of
    the insights, backlog, roadmap, PRDs, user stories and reports.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    return await quality_service.evaluate_workspace(workspace_id)


@router.get("/{workspace_id}/export", response_class=PlainTextResponse)
async def export_quality_markdown(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Export the output quality evaluation as raw GitHub-flavoured Markdown."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    report = await quality_service.evaluate_workspace(workspace_id)
    markdown = report.get("raw_markdown") or quality_service._build_markdown_from_quality(report)
    return PlainTextResponse(content=markdown, media_type="text/markdown")
