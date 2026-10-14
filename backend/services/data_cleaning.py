"""
Data cleaning service for feedback records.
Provides text cleaning, deduplication, and missing value handling.
"""

import re
from typing import List, Dict, Any
from database import db


async def clean_text(text: str) -> str:
    """
    Clean a single text string.
    - Convert to lowercase
    - Strip leading/trailing whitespace
    - Remove special characters (keep letters, numbers, spaces, basic punctuation)
    - Remove extra spaces (multiple spaces become single)
    """
    if not text or not isinstance(text, str):
        return ""

    # Convert to lowercase
    text = text.lower()

    # Strip leading/trailing whitespace
    text = text.strip()

    # Remove special characters — keep only alphanumeric, spaces, and basic punctuation
    # We keep . , ! ? ' - to preserve sentence structure
    text = re.sub(r"[^a-z0-9\s.,!?'\-]", " ", text)

    # Remove extra whitespace (multiple spaces collapse to single)
    text = re.sub(r"\s+", " ", text)

    # Strip again after cleaning
    text = text.strip()

    return text


async def handle_missing_values(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Handle records with missing values.
    - Remove records where content is null or empty after cleaning
    - Fill missing title with truncated content (first 50 chars)
    - Convert NaN values to None
    """
    cleaned_records = []

    for record in records:
        # Skip records with no content
        content = record.get("content")
        if content is None or (isinstance(content, float) and str(content) == "nan"):
            continue
        if isinstance(content, str) and content.strip() == "":
            continue

        # Clean up NaN values for string fields
        for key in ["title", "customer_name", "customer_email"]:
            value = record.get(key)
            if value is not None and isinstance(value, float) and str(value) == "nan":
                record[key] = None

        # If title is missing, generate from content
        if not record.get("title"):
            content_str = str(record.get("content", ""))
            record["title"] = content_str[:50] + ("..." if len(content_str) > 50 else "")

        # Handle NaN rating
        rating = record.get("rating")
        if rating is not None and isinstance(rating, float) and str(rating) == "nan":
            record["rating"] = None

        cleaned_records.append(record)

    return cleaned_records


async def remove_duplicates(workspace_id: str) -> Dict[str, int]:
    """
    Find and remove near-duplicate feedback within a workspace.
    Duplicates are identified by comparing cleaned content strings.
    Keeps the first occurrence and marks/removes subsequent duplicates.
    Returns counts of processed and removed records.
    """
    # Fetch all feedback for the workspace
    cursor = db.feedback.find(
        {"workspace_id": workspace_id},
        {"_id": 1, "content": 1}
    )
    records = await cursor.to_list(length=None)

    if not records:
        return {"processed": 0, "removed": 0}

    # Build a map of cleaned content to first seen document ID
    seen_content: Dict[str, str] = {}
    duplicate_ids: List[str] = []
    processed = 0

    for record in records:
        processed += 1
        record_id = str(record["_id"])
        content = record.get("content", "")

        # Clean the content for comparison
        cleaned = await clean_text(str(content))

        if not cleaned:
            # Empty content after cleaning — treat as duplicate
            duplicate_ids.append(record_id)
            continue

        if cleaned in seen_content:
            # Already seen this content — it's a duplicate
            duplicate_ids.append(record_id)
        else:
            seen_content[cleaned] = record_id

    # Delete all duplicate records from the database
    if duplicate_ids:
        from bson import ObjectId
        object_ids = [ObjectId(did) if ObjectId.is_valid(did) else did for did in duplicate_ids]
        delete_result = await db.feedback.delete_many({"_id": {"$in": object_ids}})
        removed = delete_result.deleted_count
    else:
        removed = 0

    return {"processed": processed, "removed": removed}


async def clean_workspace_feedback(workspace_id: str) -> Dict[str, int]:
    """
    Run the full data cleaning pipeline on all uncleaned feedback in a workspace.
    Steps:
    1. Clean text content for all uncleaned records
    2. Mark them as cleaned
    3. Remove duplicates
       Returns counts of updated and removed records.
    """
    # Find all uncleaned feedback in this workspace
    cursor = db.feedback.find(
        {"workspace_id": workspace_id, "cleaned": False}
    )
    records = await cursor.to_list(length=None)

    operations = []
    for record in records:
        record_id = record["_id"]

        # Clean the content field
        original_content = record.get("content", "")
        cleaned_content = await clean_text(str(original_content))

        # Clean the title field
        original_title = record.get("title", "")
        cleaned_title = await clean_text(str(original_title)) if original_title else None

        # Clean customer name
        original_name = record.get("customer_name")
        cleaned_name = str(original_name).strip() if original_name else None

        operations.append((
            record_id,
            {
                "content": cleaned_content,
                "title": cleaned_title,
                "customer_name": cleaned_name,
                "cleaned": True,
            }
        ))

    from pymongo import UpdateOne

    updated_count = 0
    if operations:
        for start in range(0, len(operations), 500):
            chunk = operations[start : start + 500]
            writes = [UpdateOne({"_id": rec_id}, {"$set": fields}) for rec_id, fields in chunk]
            result = await db.feedback.bulk_write(writes, ordered=False)
            updated_count += result.modified_count

    # Remove duplicates
    dup_result = await remove_duplicates(workspace_id)

    return {
        "updated": updated_count,
        "removed": dup_result["removed"],
    }
