"""Feedback schemas and validation models."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from app.schemas.common import MongoBaseModel


class FeedbackBase(BaseModel):
    """Base feedback fields shared across create, update, and response models."""

    workspace_id: Optional[str] = Field(None, description="Workspace partition identifier")
    customer_id: Optional[str] = Field(None, description="Identifier of the customer or user")
    source: str = Field(..., description="Source of the feedback (e.g., Zendesk, AppStore, Trustpilot, CSV, API)")
    type: str = Field("review", description="Type of feedback (e.g., review, survey, interview, social, in-app)")
    text: str = Field(..., min_length=1, description="Raw original feedback text")
    cleaned_text: Optional[str] = Field(None, description="Preprocessed/cleaned text")
    category: Optional[str] = Field("Other", description="Categorization tag or cluster label")
    category_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Classification confidence score (0.0 to 1.0)")
    sentiment: Optional[str] = Field(None, description="Sentiment analysis (e.g., Positive, Neutral, Negative)")
    priority: Optional[str] = Field("Medium", description="Priority level (Low, Medium, High, Urgent)")
    status: Optional[str] = Field("New", description="Workflow status (New, Processed, In-Review, Actioned, Archived)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata and source-specific attributes")


class FeedbackCreate(FeedbackBase):
    """Schema for submitting new customer feedback."""
    pass


class FeedbackUpdate(BaseModel):
    """Schema for updating an existing feedback record."""

    workspace_id: Optional[str] = None
    customer_id: Optional[str] = None
    source: Optional[str] = None
    type: Optional[str] = None
    text: Optional[str] = None
    cleaned_text: Optional[str] = None
    category: Optional[str] = None
    category_confidence: Optional[float] = None
    sentiment: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class FeedbackInDB(MongoBaseModel, FeedbackBase):
    """Schema for feedback document stored in MongoDB."""

    id: Optional[str] = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackResponse(MongoBaseModel, FeedbackBase):
    """Public feedback response schema."""

    id: str = Field(..., alias="_id", serialization_alias="id")
    created_at: datetime
    updated_at: datetime
