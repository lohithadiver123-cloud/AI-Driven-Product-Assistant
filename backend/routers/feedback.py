"""
Feedback router.
Handles feedback import, data cleaning, categorization, listing, and import logs.
"""

import json
import io
import csv
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from bson import ObjectId
from database import db
from models.feedback import (
    FeedbackResponse,
    ImportLogResponse,
    ImportResultResponse,
    BulkActionResponse,
)
from models.workspace import WorkspaceStatsResponse
from services.data_cleaning import clean_workspace_feedback
from services.categorization import batch_categorize
from routers.auth import get_authorization_header, get_current_user
import pandas as pd

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


async def _get_user_from_token(authorization: str) -> dict:
    """Extract and validate the current user from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.replace("Bearer ", "")
    return await get_current_user(token)


import database
from fallback_db import (
    find_workspaces_by_user as fb_find_workspaces_by_user,
    find_feedback_by_workspace as fb_find_feedback_by_workspace,
    create_feedback as fb_create_feedback,
)


import time
_workspace_access_cache: dict = {}  # f"{ws_id}:{user_id}" -> (workspace, expires_at)


async def _verify_workspace_access(workspace_id: str, user: dict) -> dict:
    """Verify that a workspace exists and the user has access to it. Cached for 60s."""
    now = time.time()
    cache_key = f"{workspace_id}:{user.get('_id')}"
    cached = _workspace_access_cache.get(cache_key)
    if cached and cached[1] > now:
        return cached[0]

    if not database._mongodb_available:
        workspaces = await fb_find_workspaces_by_user(str(user["_id"]))
        workspace = next((ws for ws in workspaces if str(ws.get("_id")) == str(workspace_id)), None)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        _workspace_access_cache[cache_key] = (workspace, now + 60.0)
        return workspace

    workspace = None
    try:
        workspace = await database.db.workspaces.find_one({"_id": ObjectId(workspace_id)})
    except Exception:
        pass

    if not workspace:
        workspace = await database.db.workspaces.find_one({"_id": workspace_id})

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    user_id_str = str(user["_id"])
    # Ownership or membership, and nothing else. A workspace's name used to grant access
    # here (`spotify`, `demo`, anything containing `instagram`), which let any signed-in
    # account open another tenant's demo workspace by id.
    has_access = (
        str(workspace.get("created_by")) == user_id_str
        or user_id_str in [str(m) for m in workspace.get("members", [])]
        or str(workspace.get("_id")) in [str(wid) for wid in user.get("workspace_ids", [])]
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace",
        )

    if len(_workspace_access_cache) > 500:
        _workspace_access_cache.clear()
    _workspace_access_cache[cache_key] = (workspace, now + 60.0)

    return workspace


@router.post("/import", response_model=ImportResultResponse)
async def import_feedback(
    file: UploadFile = File(..., description="CSV or JSON file to import"),
    workspace_id: str = Form(..., description="Target workspace ID"),
    source: str = Form(..., description="Source type: app_review, support_ticket, survey, etc."),
    authorization: str = Depends(get_authorization_header),
):
    """
    Import feedback from a CSV or JSON file.
    Parses the file with pandas, validates data, and inserts into MongoDB.
    Creates an import log entry to track the operation.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    # Validate file extension
    filename = file.filename or "unknown"
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if file_ext not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and JSON files are supported",
        )

    # Create import log entry
    import_log = {
        "workspace_id": workspace_id,
        "filename": filename,
        "record_count": 0,
        "successful": 0,
        "failed": 0,
        "status": "processing",
        "imported_at": datetime.utcnow(),
    }
    log_result = await db.import_logs.insert_one(import_log)
    import_log_id = str(log_result.inserted_id)

    try:
        # Read file content
        content = await file.read()

        # Parse with pandas based on file type
        if file_ext == "csv":
            # Try reading with different encodings
            try:
                df = pd.read_csv(io.BytesIO(content))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(content), encoding="latin-1")
        else:
            # JSON file
            try:
                df = pd.read_json(io.BytesIO(content))
            except Exception:
                # Try parsing as JSON lines
                text_content = content.decode("utf-8")
                data = [json.loads(line) for line in text_content.strip().split("\n") if line.strip()]
                df = pd.DataFrame(data)

        # Normalize column names to lowercase
        df.columns = df.columns.str.lower().str.strip()

        # Map expected columns — be flexible with column names
        column_mapping = {
            "title": ["title", "subject", "heading", "summary"],
            "content": ["content", "text", "body", "message", "description", "feedback", "comment", "review"],
            "customer_name": ["customer_name", "customer name", "name", "author", "user", "username", "customer"],
            "customer_email": ["customer_email", "customer email", "email", "user_email"],
            "rating": ["rating", "score", "stars", "grade"],
            "source": ["source", "source_type", "channel", "platform"],
        }

        # Find matching columns
        mapped_columns = {}
        for target_field, possible_names in column_mapping.items():
            for possible_name in possible_names:
                if possible_name in df.columns:
                    mapped_columns[target_field] = possible_name
                    break

        # Convert DataFrame to list of dicts
        records = df.to_dict("records")

        # Prepare feedback documents for insertion
        feedback_docs = []
        successful = 0
        failed = 0

        for record in records:
            try:
                # Extract fields with mapped column names
                title_val = record.get(mapped_columns.get("title", ""))
                content_val = record.get(mapped_columns.get("content", ""))
                name_val = record.get(mapped_columns.get("customer_name", ""))
                email_val = record.get(mapped_columns.get("customer_email", ""))
                rating_val = record.get(mapped_columns.get("rating", ""))
                source_val = record.get(mapped_columns.get("source", ""))

                # Skip records with no content
                if content_val is None or (isinstance(content_val, str) and content_val.strip() == "") or \
                   (isinstance(content_val, float) and str(content_val) == "nan"):
                    failed += 1
                    continue

                # Clean up NaN values
                if title_val is not None and isinstance(title_val, float) and str(title_val) == "nan":
                    title_val = None
                if name_val is not None and isinstance(name_val, float) and str(name_val) == "nan":
                    name_val = None
                if email_val is not None and isinstance(email_val, float) and str(email_val) == "nan":
                    email_val = None

                # Determine effective source
                effective_source = source
                if source_val is not None and not (isinstance(source_val, float) and str(source_val) == "nan"):
                    src_str = str(source_val).strip()
                    if src_str:
                        effective_source = src_str

                # Parse rating
                rating_parsed = None
                if rating_val is not None:
                    try:
                        rating_parsed = int(float(rating_val))
                        rating_parsed = max(1, min(5, rating_parsed))
                    except (ValueError, TypeError):
                        pass

                # Generate title from content if not provided
                if not title_val:
                    content_str = str(content_val)
                    title_val = content_str[:50] + ("..." if len(content_str) > 50 else "")

                now = datetime.utcnow()
                feedback_doc = {
                    "workspace_id": workspace_id,
                    "source": effective_source,
                    "title": str(title_val).strip() if title_val else None,
                    "content": str(content_val).strip(),
                    "customer_name": str(name_val).strip() if name_val else None,
                    "customer_email": str(email_val).strip() if email_val else None,
                    "rating": rating_parsed,
                    "category": None,
                    "sentiment": None,
                    "priority": None,
                    "status": "new",
                    "tags": [],
                    "created_at": now,
                    "imported_at": now,
                    "imported_via": import_log_id,
                    "cleaned": False,
                }

                feedback_docs.append(feedback_doc)
                successful += 1

            except Exception:
                failed += 1
                continue

        # Bulk insert all valid feedback documents
        if feedback_docs:
            await db.feedback.insert_many(feedback_docs)

        # Update import log with final counts
        await db.import_logs.update_one(
            {"_id": log_result.inserted_id},
            {
                "$set": {
                    "record_count": len(records),
                    "successful": successful,
                    "failed": failed,
                    "status": "completed" if failed == 0 else "completed_with_errors",
                }
            },
        )

        # Analysis follows the data in. Imported rows arrive uncategorised and
        # unanalysed, so the pipeline is queued rather than left for someone to notice
        # and press. It runs in the background (the response returns now) and the caller
        # watches GET /api/insights/{id}/status for it to land.
        analysis_queued = False
        if successful > 0:
            from services.analysis_jobs import start as start_analysis

            start_analysis(workspace_id, authorization, reason="import")
            analysis_queued = True

        return ImportResultResponse(
            import_log_id=import_log_id,
            filename=filename,
            record_count=len(records),
            successful=successful,
            failed=failed,
            status="completed" if failed == 0 else "completed_with_errors",
            analysis_queued=analysis_queued,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        await db.import_logs.update_one(
            {"_id": log_result.inserted_id},
            {"$set": {"status": "failed"}},
        )
        raise
    except Exception as e:
        # Update log and report error
        await db.import_logs.update_one(
            {"_id": log_result.inserted_id},
            {"$set": {"status": "failed"}},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process file: {str(e)}",
        )


@router.post("/clean", response_model=BulkActionResponse)
async def clean_feedback(
    workspace_id: str = Form(..., description="Workspace ID to clean feedback for"),
    authorization: str = Depends(get_authorization_header),
):
    """
    Run data cleaning on all uncleaned feedback in a workspace.
    Removes duplicates, normalizes text, strips whitespace.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    result = await clean_workspace_feedback(workspace_id)

    return BulkActionResponse(
        processed=result["updated"],
        updated=result["updated"],
        skipped=0,
        message=f"Cleaned {result['updated']} records and removed {result['removed']} duplicates.",
    )


@router.post("/categorize", response_model=BulkActionResponse)
async def categorize_feedback(
    workspace_id: str = Form(..., description="Workspace ID to categorize feedback for"),
    authorization: str = Depends(get_authorization_header),
):
    """
    Run rule-based categorization on all uncategorized feedback in a workspace.
    Assigns category (bug_report, feature_request, etc.) and sentiment.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    result = await batch_categorize(workspace_id)

    return BulkActionResponse(
        processed=result["processed"],
        updated=result["updated"],
        skipped=result["processed"] - result["updated"],
        message=f"Categorized {result['updated']} out of {result['processed']} uncategorized records.",
    )


@router.get("", response_model=dict)
async def list_feedback(
    workspace_id: str = Query(..., description="Filter by workspace ID"),
    category: Optional[str] = Query(None, description="Filter by category"),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment"),
    source: Optional[str] = Query(None, description="Filter by source type"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    authorization: str = Depends(get_authorization_header),
):
    """
    Get paginated feedback with optional filters.
    Supports filtering by category, sentiment, and source.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    # Build the query filter
    query_filter: dict = {"workspace_id": workspace_id}

    if category:
        query_filter["category"] = category
    if sentiment:
        query_filter["sentiment"] = sentiment
    if source:
        query_filter["source"] = source

    # Count total matching documents
    total = await db.feedback.count_documents(query_filter)

    # Calculate pagination
    skip = (page - 1) * limit
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    # Fetch paginated results
    cursor = db.feedback.find(query_filter).sort("created_at", -1).skip(skip).limit(limit)
    records = await cursor.to_list(length=limit)

    # Convert ObjectId to string for JSON serialization
    for record in records:
        record["_id"] = str(record["_id"])
        # Convert datetime objects to ISO strings
        if record.get("created_at"):
            record["created_at"] = record["created_at"].isoformat()
        if record.get("imported_at"):
            record["imported_at"] = record["imported_at"].isoformat()

    return {
        "items": records,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
    }


@router.get("/import-logs", response_model=List[ImportLogResponse])
async def list_import_logs(
    workspace_id: str = Query(..., description="Filter by workspace ID"),
    authorization: str = Depends(get_authorization_header),
):
    """
    Get import history for a workspace.
    Returns all import log entries sorted by most recent first.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)

    cursor = db.import_logs.find({"workspace_id": workspace_id}).sort("imported_at", -1)
    logs = await cursor.to_list(length=None)

    # Convert ObjectId and datetime for JSON serialization
    for log in logs:
        log["_id"] = str(log["_id"])
        if log.get("imported_at"):
            log["imported_at"] = log["imported_at"].isoformat()

    return logs
