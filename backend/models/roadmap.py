"""
Roadmap Planning & Milestone Recommendation data models for Milestone 4.
Defines the shapes for horizon planning, sequenced roadmap items, recommended
milestones, and the request payload used to generate or regenerate a plan.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class RoadmapItem(BaseModel):
    """A single prioritised initiative placed on the roadmap."""

    id: str = Field(..., description="Unique roadmap item ID")
    prioritization_item_id: Optional[str] = Field(None, description="Source prioritization item")
    name: str = Field(..., description="Initiative name")
    description: str = Field("", description="Summary of the customer demand behind it")
    category: str = Field("feature_request", description="feature_request, bug_fix, performance, security")
    horizon: str = Field("now", description="now, next, or later")
    release: str = Field(..., description="Release window this item is scheduled into")
    sequence: int = Field(1, description="Global sequence position across the roadmap")
    rice_score: float = Field(0.0, description="RICE score carried from prioritization")
    weighted_score: float = Field(0.0, description="Weighted multi-factor score carried from prioritization")
    moscow: str = Field("should_have", description="must_have, should_have, could_have, wont_have")
    effort: float = Field(2.0, description="Effort carried from prioritization (person-months)")
    feedback_count: int = Field(0, description="Customer records supporting this item")
    rationale: str = Field("", description="Why this item sits here, in this order")
    dependencies: List[str] = Field(default_factory=list, description="Work that must land first")
    milestone_id: Optional[str] = Field(None, description="Milestone this item belongs to")


class MilestoneSuccessMetric(BaseModel):
    """A measurable outcome a milestone is judged against."""

    metric: str = Field(..., description="What is measured")
    baseline: str = Field("", description="Measured baseline from this workspace")
    target: str = Field("", description="Proposed target once the milestone lands")
    tracking_mechanism: str = Field("", description="How the metric would actually be observed")


class RoadmapMilestone(BaseModel):
    """A recommended milestone: a themed, time-boxed batch of roadmap items."""

    id: str = Field(..., description="Unique milestone ID")
    name: str = Field(..., description="Milestone name")
    objective: str = Field("", description="The outcome this milestone is meant to deliver")
    horizon: str = Field("now", description="now, next, or later")
    release: str = Field(..., description="Release window label")
    start_date: str = Field(..., description="Recommended start (ISO date)")
    end_date: str = Field(..., description="Recommended end (ISO date)")
    item_ids: List[str] = Field(default_factory=list, description="Roadmap items in this milestone")
    item_count: int = Field(0, description="Number of items in this milestone")
    effort_total: float = Field(0.0, description="Total effort committed to this milestone")
    feedback_count: int = Field(0, description="Customer records behind this milestone")
    confidence: str = Field("medium", description="high, medium, or low — based on evidence volume")
    rationale: str = Field("", description="Sequencing rationale")
    exit_criteria: List[str] = Field(default_factory=list, description="What must be true to close it")
    success_metrics: List[MilestoneSuccessMetric] = Field(default_factory=list)


class RoadmapRelease(BaseModel):
    """A release window containing one or more milestones."""

    name: str = Field(..., description="Release window label")
    horizon: str = Field("now", description="now, next, or later")
    start_date: str = Field(..., description="Window start (ISO date)")
    end_date: str = Field(..., description="Window end (ISO date)")
    capacity: float = Field(0.0, description="Committed effort capacity for this window")
    effort_total: float = Field(0.0, description="Effort actually allocated")
    item_count: int = Field(0, description="Items scheduled into this window")
    milestone_ids: List[str] = Field(default_factory=list, description="Milestones in this window")


class RoadmapGenerateRequest(BaseModel):
    """Payload for generating or regenerating a workspace roadmap."""

    workspace_id: str = Field(..., description="Workspace whose prioritised work is planned")
    horizon_weeks: int = Field(12, description="Planning horizon in weeks (4-52)")
    velocity: float = Field(8.0, description="Committed effort per release window (0.5-100)")
    focus: Optional[str] = Field(None, description="Optional strategic focus to bias sequencing")
    include_items: Optional[List[str]] = Field(None, description="Restrict the plan to these prioritization item IDs")
    replace_existing: bool = Field(True, description="Replace any previously generated roadmap")


class RoadmapModel(BaseModel):
    """Complete roadmap plan for a workspace."""

    workspace_id: str = Field(..., description="Workspace ID")
    workspace_name: str = Field("", description="Workspace name")
    strategy: str = Field("", description="How this plan was sequenced")
    focus: Optional[str] = Field(None, description="Strategic focus the plan was generated with")
    generated_at: str = Field("", description="Generation timestamp (ISO)")
    horizon_weeks: int = Field(12, description="Planning horizon in weeks")
    velocity: float = Field(8.0, description="Committed effort per release window")
    releases: List[RoadmapRelease] = Field(default_factory=list, description="Release windows")
    milestones: List[RoadmapMilestone] = Field(default_factory=list, description="Recommended milestones")
    items: List[RoadmapItem] = Field(default_factory=list, description="Sequenced roadmap items")
    deferred: List[RoadmapItem] = Field(default_factory=list, description="Items beyond the horizon")
    deferred_reason: str = Field("", description="Why items fell outside the horizon")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Measured provenance block")
    ai_generated: bool = Field(False, description="Whether a model wrote the narrative")
    ai_model: str = Field("Deterministic planning engine", description="Engine that produced the plan")
    raw_markdown: str = Field("", description="Markdown rendering of the roadmap")
    created_at: str = Field("", description="Creation timestamp (ISO)")
    updated_at: str = Field("", description="Last update timestamp (ISO)")
