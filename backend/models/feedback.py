"""
Feedback and ImportLog model definitions for request/response validation and database schema.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    """Schema for creating a single feedback record (used internally after import parsing)."""
    workspace_id: str = Field(..., description="ID of the workspace this feedback belongs to")
    source: str = Field(..., description="Source type: app_review, support_ticket, survey, etc.")
    title: Optional[str] = Field(None, description="Feedback title or subject")
    content: str = Field(..., min_length=1, description="The feedback text content")
    customer_name: Optional[str] = Field(None, description="Name of the customer who submitted feedback")
    customer_email: Optional[str] = Field(None, description="Email of the customer")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Customer rating from 1 to 5")
    imported_via: Optional[str] = Field(None, description="Import log ID if imported via file")


class FeedbackResponse(BaseModel):
    """Schema for feedback data returned in API responses."""
    id: str = Field(..., alias="_id", description="Feedback unique identifier")
    workspace_id: str
    source: str
    title: Optional[str] = None
    content: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    rating: Optional[int] = None
    category: Optional[str] = Field(None, description="Categorized type: bug_report, feature_request, etc.")
    sentiment: Optional[str] = Field(None, description="Sentiment: positive, neutral, negative")
    priority: Optional[str] = Field(None, description="Priority level")
    status: str = Field(default="new", description="Processing status")
    tags: List[str] = Field(default_factory=list, description="User-defined tags")
    cleaned: bool = Field(default=False, description="Whether data cleaning has been applied")
    created_at: Optional[datetime] = None
    imported_at: Optional[datetime] = None
    imported_via: Optional[str] = None

    class Config:
        populate_by_name = True
        from_attributes = True


class FeedbackInDB(BaseModel):
    """Internal feedback representation as stored in MongoDB."""
    workspace_id: str
    source: str
    title: Optional[str] = None
    content: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    rating: Optional[int] = None
    category: Optional[str] = None
    sentiment: Optional[str] = None
    priority: Optional[str] = None
    status: str = "new"
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    imported_at: datetime = Field(default_factory=datetime.utcnow)
    imported_via: Optional[str] = None
    cleaned: bool = False

    class Config:
        populate_by_name = True
        from_attributes = True


class ImportLogCreate(BaseModel):
    """Schema for creating an import log entry."""
    workspace_id: str
    filename: str
    record_count: int = 0
    successful: int = 0
    failed: int = 0
    status: str = "pending"


class ImportLogResponse(BaseModel):
    """Schema for import log data returned in API responses."""
    id: str = Field(..., alias="_id", description="Import log unique identifier")
    workspace_id: str
    filename: str
    record_count: int
    successful: int
    failed: int
    status: str
    imported_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        from_attributes = True


class ImportLogInDB(BaseModel):
    """Internal import log representation as stored in MongoDB."""
    workspace_id: str
    filename: str
    record_count: int = 0
    successful: int = 0
    failed: int = 0
    status: str = "pending"
    imported_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        from_attributes = True


class ImportResultResponse(BaseModel):
    """Schema for the result of a file import operation."""
    import_log_id: str
    filename: str
    record_count: int
    successful: int
    failed: int
    status: str
    analysis_queued: bool = Field(
        False,
        description="Whether an AI analysis of the imported records was started in the background",
    )


class BulkActionResponse(BaseModel):
    """Schema for bulk operation results (cleaning, categorization)."""
    processed: int = Field(..., description="Number of records processed")
    updated: int = Field(..., description="Number of records updated")
    skipped: int = Field(..., description="Number of records skipped")
    message: str = Field(..., description="Summary message")
