"""Support Tickets API router with automated categorization, priority detection, and dataset ingestion scoped to active workspace."""
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.database.collections import Collections
from app.database.connection import get_collection
from app.dependencies.auth import get_user_workspace_context, require_role
from app.schemas.common import PaginatedResponse
from app.schemas.ingestion import IngestionReport
from app.schemas.stats import FeedbackStatsResponse
from app.schemas.support_ticket import (
    SupportTicketCreate,
    SupportTicketResponse,
    SupportTicketUpdate,
)
from app.services.classification import (
    CATEGORIES,
    analyze_feedback_item,
)
from app.services.ingestion import ingestion_service

router = APIRouter(prefix="/support-tickets", tags=["Customer Support Tickets"])


@router.get(
    "/stats",
    response_model=FeedbackStatsResponse,
    summary="Get aggregated support ticket statistics",
    description="Calculates live aggregate distribution counts for support tickets for the active workspace.",
)
async def get_support_ticket_stats(ctx: Dict[str, Any] = Depends(get_user_workspace_context)):
    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.SUPPORT_TICKETS)
    query = {"workspace_id": ws_id}

    total = await collection.count_documents(query)
    if total == 0:
        return FeedbackStatsResponse(
            total=0,
            categories={cat: 0 for cat in CATEGORIES},
            sentiment={"Positive": 0, "Neutral": 0, "Negative": 0},
            priority={"Urgent": 0, "High": 0, "Medium": 0, "Low": 0},
            sources={},
            average_confidence=0.0,
            negative_percentage=0.0,
            high_priority_percentage=0.0,
        )

    pipeline = [
        {"$match": query},
        {
            "$facet": {
                "by_category": [{"$group": {"_id": "$category", "count": {"$sum": 1}}}],
                "by_sentiment": [{"$group": {"_id": "$sentiment", "count": {"$sum": 1}}}],
                "by_priority": [{"$group": {"_id": "$priority", "count": {"$sum": 1}}}],
                "by_source": [{"$group": {"_id": "$source", "count": {"$sum": 1}}}],
                "avg_confidence": [
                    {"$match": {"category_confidence": {"$ne": None}}},
                    {"$group": {"_id": None, "avg": {"$avg": "$category_confidence"}}},
                ],
            }
        }
    ]

    agg_result = await collection.aggregate(pipeline).to_list(length=1)
    facet_data = agg_result[0] if agg_result else {}

    cat_counts = {cat: 0 for cat in CATEGORIES}
    for item in facet_data.get("by_category", []):
        cat_name = item["_id"] or "Other"
        cat_counts[cat_name] = item["count"]

    sent_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    for item in facet_data.get("by_sentiment", []):
        sent_name = item["_id"] or "Neutral"
        sent_counts[sent_name] = item["count"]

    prio_counts = {"Urgent": 0, "High": 0, "Medium": 0, "Low": 0}
    for item in facet_data.get("by_priority", []):
        prio_name = item["_id"] or "Medium"
        prio_counts[prio_name] = item["count"]

    source_counts = {}
    for item in facet_data.get("by_source", []):
        if item["_id"]:
            source_counts[str(item["_id"])] = item["count"]

    avg_conf = 0.85
    avg_conf_list = facet_data.get("avg_confidence", [])
    if avg_conf_list and avg_conf_list[0].get("avg") is not None:
        avg_conf = round(float(avg_conf_list[0]["avg"]), 2)

    negative_pct = round(((sent_counts.get("Negative", 0) / total) * 100), 1) if total > 0 else 0.0
    high_prio_pct = (
        round((((prio_counts.get("High", 0) + prio_counts.get("Urgent", 0)) / total) * 100), 1)
        if total > 0
        else 0.0
    )

    return FeedbackStatsResponse(
        total=total,
        categories=cat_counts,
        sentiment=sent_counts,
        priority=prio_counts,
        sources=source_counts,
        average_confidence=avg_conf,
        negative_percentage=negative_pct,
        high_priority_percentage=high_prio_pct,
    )


@router.post(
    "/upload",
    response_model=IngestionReport,
    summary="Upload & ingest support tickets CSV dataset",
    description="Uploads a CSV dataset of customer support tickets for the active workspace.",
)
async def upload_support_tickets_csv(
    file: UploadFile = File(...),
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN", "MEMBER"])),
):
    if not file.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Please upload a CSV file (.csv).",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    report = await ingestion_service.ingest_support_tickets_csv(
        content,
        filename=file.filename,
        workspace_id=ctx["workspace_id"],
    )
    return report


@router.post(
    "/upload-json",
    response_model=IngestionReport,
    summary="Upload & ingest support tickets JSON dataset",
    description="Ingests a batch list of support tickets via JSON array.",
)
async def upload_support_tickets_json(
    records: List[Dict[str, Any]],
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN", "MEMBER"])),
):
    if not records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON record list is empty.",
        )

    report = await ingestion_service.ingest_support_tickets_json(
        records,
        filename="tickets_api_upload.json",
        workspace_id=ctx["workspace_id"],
    )
    return report


@router.post(
    "",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create support ticket",
    description="Inserts a new support ticket record with automated categorization and priority scoring.",
)
async def create_support_ticket(
    ticket_in: SupportTicketCreate,
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN", "MEMBER"])),
):
    collection = get_collection(Collections.SUPPORT_TICKETS)
    doc = ticket_in.model_dump()
    doc["workspace_id"] = ctx["workspace_id"]

    analysis = analyze_feedback_item(doc["text"])
    if not doc.get("cleaned_text"):
        doc["cleaned_text"] = analysis["cleaned_text"]
    if not doc.get("category") or doc["category"] == "Other":
        doc["category"] = analysis["category"]
        doc["category_confidence"] = analysis["category_confidence"]
    elif doc.get("category_confidence") is None:
        doc["category_confidence"] = analysis["category_confidence"]

    if not doc.get("sentiment"):
        doc["sentiment"] = analysis["sentiment"]
    if not doc.get("priority") or doc["priority"] == "Medium":
        doc["priority"] = analysis["priority"]

    if not doc.get("ticket_id"):
        total_count = await collection.count_documents({"workspace_id": ctx["workspace_id"]})
        doc["ticket_id"] = f"TIK-{1001 + total_count}"

    now = datetime.now(timezone.utc)
    doc["created_at"] = now
    doc["updated_at"] = now

    result = await collection.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get(
    "",
    response_model=PaginatedResponse[SupportTicketResponse],
    summary="List support tickets",
    description="Retrieve a paginated list of support tickets with multi-criteria filtering for the active workspace.",
)
async def list_support_tickets(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(15, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search keyword across text, ticket_id, customer_id"),
    category: Optional[str] = Query(None, description="Filter by category"),
    priority: Optional[str] = Query(None, description="Filter by priority (Urgent, High, Medium, Low)"),
    status: Optional[str] = Query(None, description="Filter by ticket status (Open, In-Progress, Resolved, Closed)"),
    source: Optional[str] = Query(None, description="Filter by source channel"),
    ctx: Dict[str, Any] = Depends(get_user_workspace_context),
):
    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.SUPPORT_TICKETS)
    query: Dict[str, Any] = {"workspace_id": ws_id}

    if search and search.strip():
        search_escaped = re.escape(search.strip())
        query["$or"] = [
            {"text": {"$regex": search_escaped, "$options": "i"}},
            {"cleaned_text": {"$regex": search_escaped, "$options": "i"}},
            {"ticket_id": {"$regex": search_escaped, "$options": "i"}},
            {"customer_id": {"$regex": search_escaped, "$options": "i"}},
        ]

    if category:
        query["category"] = category
    if priority:
        query["priority"] = priority
    if status:
        query["status"] = status
    if source:
        query["source"] = source

    total = await collection.count_documents(query)
    skip = (page - 1) * page_size
    cursor = collection.find(query).sort("created_at", -1).skip(skip).limit(page_size)

    items = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        items.append(doc)

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{id}",
    response_model=SupportTicketResponse,
    summary="Get single support ticket",
    description="Fetch a support ticket document by its MongoDB ObjectId within the active workspace.",
)
async def get_support_ticket_by_id(
    id: str,
    ctx: Dict[str, Any] = Depends(get_user_workspace_context),
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ObjectId format")

    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.SUPPORT_TICKETS)
    doc = await collection.find_one({"_id": ObjectId(id), "workspace_id": ws_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support ticket not found in active workspace.")

    doc["_id"] = str(doc["_id"])
    return doc


@router.patch(
    "/{id}",
    response_model=SupportTicketResponse,
    summary="Update support ticket",
    description="Update fields of an existing support ticket document.",
)
async def update_support_ticket(
    id: str,
    update_data: SupportTicketUpdate,
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN", "MEMBER"])),
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ObjectId format")

    updates = {k: v for k, v in update_data.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update")

    if "text" in updates and updates["text"]:
        analysis = analyze_feedback_item(updates["text"])
        updates["cleaned_text"] = analysis["cleaned_text"]
        updates["category"] = analysis["category"]
        updates["category_confidence"] = analysis["category_confidence"]

    updates["updated_at"] = datetime.now(timezone.utc)
    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.SUPPORT_TICKETS)

    result = await collection.find_one_and_update(
        {"_id": ObjectId(id), "workspace_id": ws_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support ticket not found in active workspace.")

    result["_id"] = str(result["_id"])
    return result


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete support ticket",
    description="Deletes a support ticket from the active workspace. Requires OWNER or ADMIN role.",
)
async def delete_support_ticket(
    id: str,
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN"])),
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ObjectId format")

    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.SUPPORT_TICKETS)
    result = await collection.delete_one({"_id": ObjectId(id), "workspace_id": ws_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support ticket not found in active workspace.")
    return None
