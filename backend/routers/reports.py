"""
Executive Summary & Product Strategy Report Router for Milestone 4.
Provides endpoints for:
- Generating an executive summary or a product strategy report
- Listing, reading, editing and deleting reports
- Exporting a report as Markdown
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from models.report import ReportGenerateRequest, ReportUpdateRequest
from services import report_service
from routers.auth import get_authorization_header, get_current_user
from routers.feedback import _verify_workspace_access

router = APIRouter(prefix="/api/reports", tags=["reports"])


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
async def generate_report(
    payload: ReportGenerateRequest,
    authorization: str = Depends(get_authorization_header),
):
    """Generate an executive summary or product strategy report from measured workspace evidence."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(payload.workspace_id, user)

    try:
        return await report_service.generate_report(
            workspace_id=payload.workspace_id,
            report_type=payload.report_type,
            audience=payload.audience,
            period=payload.period,
            focus=payload.focus,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(exc)}",
        )


@router.get("/workspace/{workspace_id}", response_model=List[Dict[str, Any]])
async def list_workspace_reports(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """List every report generated for a workspace, newest first."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    return await report_service.get_reports_for_workspace(workspace_id)


@router.get("/{report_id}", response_model=Dict[str, Any])
async def get_report(
    report_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Retrieve a single report by ID."""
    user = await _get_user_from_token(authorization)
    report = await report_service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    await _verify_workspace_access(report["workspace_id"], user)
    return report


@router.put("/{report_id}", response_model=Dict[str, Any])
async def update_report(
    report_id: str,
    payload: ReportUpdateRequest,
    authorization: str = Depends(get_authorization_header),
):
    """Update the editable fields of a stored report."""
    user = await _get_user_from_token(authorization)
    existing = await report_service.get_report_by_id(report_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    await _verify_workspace_access(existing["workspace_id"], user)

    updates = {key: value for key, value in payload.dict(exclude_unset=True).items() if value is not None}
    return await report_service.update_report(report_id, updates)


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Delete a report."""
    user = await _get_user_from_token(authorization)
    existing = await report_service.get_report_by_id(report_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    await _verify_workspace_access(existing["workspace_id"], user)

    success = await report_service.delete_report(report_id)
    return {"success": success, "deleted_id": report_id}


@router.get("/{report_id}/export", response_class=PlainTextResponse)
async def export_report_markdown(
    report_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Export a report as raw GitHub-flavoured Markdown."""
    user = await _get_user_from_token(authorization)
    report = await report_service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    await _verify_workspace_access(report["workspace_id"], user)

    markdown = report.get("raw_markdown") or report_service._build_markdown_from_report(report)
    return PlainTextResponse(content=markdown, media_type="text/markdown")
