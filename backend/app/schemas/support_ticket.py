"""Support Ticket schemas and validation models."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from app.schemas.common import MongoBaseModel


class SupportTicketBase(BaseModel):
    """Base support ticket fields shared across operations."""

    workspace_id: Optional[str] = Field(None, description="Workspace partition identifier")
    ticket_id: Optional[str] = Field(None, description="External ticket ID (e.g., TIK-1049, JIRA-234)")
    customer_id: Optional[str] = Field(None, description="Identifier of the customer or submitter")
    source: str = Field("Support Portal", description="Source channel (e.g., Zendesk, Intercom, Email, Jira, CSV)")
    text: str = Field(..., min_length=1, description="Raw customer support issue description")
    cleaned_text: Optional[str] = Field(None, description="Preprocessed/cleaned text")
    category: Optional[str] = Field("Other", description="Support issue category (e.g., Authentication, Bug, Payment, UI/UX)")
    category_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Classification confidence score")
    sentiment: Optional[str] = Field(None, description="Customer sentiment")
    priority: Optional[str] = Field("Medium", description="Ticket priority (Low, Medium, High, Urgent)")
    status: Optional[str] = Field("Open", description="Ticket status (Open, In-Progress, Resolved, Closed)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata (e.g. browser, OS, assigned agent)")


class SupportTicketCreate(SupportTicketBase):
    """Schema for creating a new support ticket."""
    pass


class SupportTicketUpdate(BaseModel):
    """Schema for updating support ticket."""

    workspace_id: Optional[str] = None
    ticket_id: Optional[str] = None
    customer_id: Optional[str] = None
    source: Optional[str] = None
    text: Optional[str] = None
    cleaned_text: Optional[str] = None
    category: Optional[str] = None
    category_confidence: Optional[float] = None
    sentiment: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SupportTicketInDB(MongoBaseModel, SupportTicketBase):
    """Schema for support ticket stored in MongoDB."""

    id: Optional[str] = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SupportTicketResponse(MongoBaseModel, SupportTicketBase):
    """Public support ticket response schema."""

    id: str = Field(..., alias="_id", serialization_alias="id")
    created_at: datetime
    updated_at: datetime
