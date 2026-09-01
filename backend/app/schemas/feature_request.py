"""Feature Request and Product schemas."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import MongoBaseModel


class FeatureRequestBase(BaseModel):
    """Base schema for extracted or suggested feature requests."""

    workspace_id: Optional[str] = Field(None, description="Workspace partition identifier")
    title: str = Field(..., description="Short title of the feature request")
    description: str = Field(..., description="Detailed description of the requested feature")
    source_feedback_ids: List[str] = Field(default_factory=list, description="IDs of linked feedback/tickets")
    category: Optional[str] = Field(None, description="Feature area / module")
    frequency_count: int = Field(1, description="Number of customer mentions/requests")
    impact_score: float = Field(0.0, description="Calculated impact score (0.0 to 10.0)")
    effort_score: float = Field(0.0, description="Estimated effort score (0.0 to 10.0)")
    priority: Optional[str] = Field("Medium", description="Priority level (Low, Medium, High, Urgent)")
    status: Optional[str] = Field("Backlog", description="Status (Backlog, Planned, In-Progress, Completed)")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FeatureRequestCreate(FeatureRequestBase):
    """Schema for creating a feature request."""
    pass


class FeatureRequestUpdate(BaseModel):
    """Schema for updating a feature request."""

    workspace_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    frequency_count: Optional[int] = None
    impact_score: Optional[float] = None
    effort_score: Optional[float] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class FeatureRequestInDB(MongoBaseModel, FeatureRequestBase):
    """Stored Feature Request in DB."""

    id: Optional[str] = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureRequestResponse(MongoBaseModel, FeatureRequestBase):
    """Response model for feature request."""

    id: str = Field(..., alias="_id", serialization_alias="id")
    created_at: datetime
    updated_at: datetime
