"""Schemas for feedback analytics, statistics, and category definitions."""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CategoryInfoResponse(BaseModel):
    """Metadata for a controlled feedback category."""

    name: str = Field(..., description="Category label")
    description: str = Field(..., description="Category functional definition")
    icon: Optional[str] = Field(None, description="Suggested Lucide icon identifier")
    color: Optional[str] = Field(None, description="Hex color theme")
    count: int = Field(0, description="Number of feedback records in this category")


class FeedbackStatsResponse(BaseModel):
    """Aggregated feedback metrics across the database."""

    total: int = Field(0, description="Total feedback records count")
    categories: Dict[str, int] = Field(default_factory=dict, description="Counts by category")
    sentiment: Dict[str, int] = Field(default_factory=dict, description="Counts by sentiment (Positive, Neutral, Negative)")
    priority: Dict[str, int] = Field(default_factory=dict, description="Counts by priority (Urgent, High, Medium, Low)")
    sources: Dict[str, int] = Field(default_factory=dict, description="Counts by source channel")
    average_confidence: float = Field(0.0, description="Average category confidence score (0.0 to 1.0)")
    negative_percentage: float = Field(0.0, description="Percentage of negative feedback")
    high_priority_percentage: float = Field(0.0, description="Percentage of High or Urgent feedback")
