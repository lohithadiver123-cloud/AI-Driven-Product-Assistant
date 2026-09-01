"""Feedback API router with categorization, statistics, and dataset ingestion scoped to active workspace."""
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.database.collections import Collections
from app.database.connection import get_collection
from app.dependencies.auth import get_user_workspace_context, require_role
from app.schemas.common import PaginatedResponse
from app.schemas.feedback import FeedbackCreate, FeedbackResponse, FeedbackUpdate
from app.schemas.ingestion import IngestionReport
from app.schemas.stats import FeedbackStatsResponse, CategoryInfoResponse
from app.services.classification import (
    CATEGORIES,
    CATEGORY_METADATA,
    analyze_feedback_item,
)
from app.services.ingestion import ingestion_service

router = APIRouter(prefix="/feedback", tags=["Customer Feedback"])


@router.get(
    "/stats",
    response_model=FeedbackStatsResponse,
    summary="Get aggregated feedback statistics",
    description="Calculates live aggregate distribution counts for categories, sentiment, priority, and data quality for the active workspace.",
)
async def get_feedback_stats(ctx: Dict[str, Any] = Depends(get_user_workspace_context)):
    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.FEEDBACK)
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

    # Aggregation pipeline scoped by workspace_id
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

    # Category counts
    cat_counts = {cat: 0 for cat in CATEGORIES}
    for item in facet_data.get("by_category", []):
        cat_name = item["_id"] or "Other"
        cat_counts[cat_name] = item["count"]

    # Sentiment counts
    sent_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    for item in facet_data.get("by_sentiment", []):
        sent_name = item["_id"] or "Neutral"
        if sent_name in sent_counts:
            sent_counts[sent_name] = item["count"]
        else:
            sent_counts[sent_name] = item["count"]

    # Priority counts
    prio_counts = {"Urgent": 0, "High": 0, "Medium": 0, "Low": 0}
    for item in facet_data.get("by_priority", []):
        prio_name = item["_id"] or "Medium"
        if prio_name in prio_counts:
            prio_counts[prio_name] = item["count"]
        else:
            prio_counts[prio_name] = item["count"]

    # Sources counts
    source_counts = {}
    for item in facet_data.get("by_source", []):
        if item["_id"]:
            source_counts[str(item["_id"])] = item["count"]

    # Avg confidence
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


@router.get(
    "/categories",
    response_model=List[CategoryInfoResponse],
    summary="Get 10 controlled categories metadata",
    description="Returns metadata and active item counts for the 10 controlled feedback categories.",
)
async def get_categories_list(ctx: Dict[str, Any] = Depends(get_user_workspace_context)):
    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.FEEDBACK)

    pipeline = [
        {"$match": {"workspace_id": ws_id}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    ]
    counts_map = {}
    async for doc in collection.aggregate(pipeline):
        cat = doc["_id"] or "Other"
        counts_map[cat] = doc["count"]

    result = []
    for cat in CATEGORIES:
        meta = CATEGORY_METADATA.get(cat, {})
        result.append(
            CategoryInfoResponse(
                name=cat,
                description=meta.get("description", ""),
                icon=meta.get("icon", "Folder"),
                color=meta.get("color", "#6366f1"),
                count=counts_map.get(cat, 0),
            )
        )
    return result


@router.post(
    "/upload",
    response_model=IngestionReport,
    summary="Upload & ingest feedback CSV dataset",
    description="Uploads a CSV dataset of customer feedback, performs cleaning, categorization, and persists.",
)
async def upload_feedback_csv(
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

    report = await ingestion_service.ingest_csv_bytes(
        content,
        filename=file.filename,
        workspace_id=ctx["workspace_id"],
    )
    return report


@router.post(
    "/upload-json",
    response_model=IngestionReport,
    summary="Upload & ingest feedback JSON dataset",
    description="Ingests a batch list of feedback records via JSON array.",
)
async def upload_feedback_json(
    records: List[Dict[str, Any]],
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN", "MEMBER"])),
):
    if not records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON record list is empty.",
        )

    report = await ingestion_service.ingest_json_records(
        records,
        filename="api_upload.json",
        workspace_id=ctx["workspace_id"],
    )
    return report


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create feedback record",
    description="Inserts a new feedback document with automatic preprocessing and categorization.",
)
async def create_feedback(
    feedback_in: FeedbackCreate,
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN", "MEMBER"])),
):
    collection = get_collection(Collections.FEEDBACK)
    doc = feedback_in.model_dump()
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

    now = datetime.now(timezone.utc)
    doc["created_at"] = now
    doc["updated_at"] = now

    result = await collection.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get(
    "",
    response_model=PaginatedResponse[FeedbackResponse],
    summary="List feedback records",
    description="Retrieve a paginated list of feedback records with search and multi-criteria filtering for the active workspace.",
)
async def list_feedback(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(15, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search keyword across text, cleaned_text, customer_id"),
    category: Optional[str] = Query(None, description="Filter by category"),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment (Positive, Neutral, Negative)"),
    priority: Optional[str] = Query(None, description="Filter by priority (Urgent, High, Medium, Low)"),
    source: Optional[str] = Query(None, description="Filter by source channel"),
    ctx: Dict[str, Any] = Depends(get_user_workspace_context),
):
    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.FEEDBACK)
    query: Dict[str, Any] = {"workspace_id": ws_id}

    if search and search.strip():
        search_escaped = re.escape(search.strip())
        query["$or"] = [
            {"text": {"$regex": search_escaped, "$options": "i"}},
            {"cleaned_text": {"$regex": search_escaped, "$options": "i"}},
            {"customer_id": {"$regex": search_escaped, "$options": "i"}},
        ]

    if category:
        query["category"] = category
    if sentiment:
        query["sentiment"] = sentiment
    if priority:
        query["priority"] = priority
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
    response_model=FeedbackResponse,
    summary="Get single feedback record",
    description="Fetch a feedback document by its MongoDB ObjectId within the active workspace.",
)
async def get_feedback_by_id(
    id: str,
    ctx: Dict[str, Any] = Depends(get_user_workspace_context),
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ObjectId format")

    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.FEEDBACK)
    doc = await collection.find_one({"_id": ObjectId(id), "workspace_id": ws_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback record not found in active workspace.")

    doc["_id"] = str(doc["_id"])
    return doc


@router.patch(
    "/{id}",
    response_model=FeedbackResponse,
    summary="Update feedback record",
    description="Update fields of an existing feedback document.",
)
async def update_feedback(
    id: str,
    update_data: FeedbackUpdate,
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
    collection = get_collection(Collections.FEEDBACK)

    result = await collection.find_one_and_update(
        {"_id": ObjectId(id), "workspace_id": ws_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback record not found in active workspace.")

    result["_id"] = str(result["_id"])
    return result


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete feedback record",
    description="Deletes a feedback record from the active workspace. Requires OWNER or ADMIN role.",
)
async def delete_feedback(
    id: str,
    ctx: Dict[str, Any] = Depends(require_role(["OWNER", "ADMIN"])),
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ObjectId format")

    ws_id = ctx["workspace_id"]
    collection = get_collection(Collections.FEEDBACK)
    result = await collection.delete_one({"_id": ObjectId(id), "workspace_id": ws_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback record not found in active workspace.")
    return None
