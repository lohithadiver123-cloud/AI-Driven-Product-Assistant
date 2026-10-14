"""
Executive summary and product strategy report models for Milestone 4.
Reports are generated from measured workspace evidence rather than free narrative:
every figure in a report is traceable to stored feedback, insights, prioritization
or roadmap data.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ReportFinding(BaseModel):
    """A single evidence-backed finding."""

    title: str = Field(..., description="Short finding headline")
    detail: str = Field(..., description="What the data shows")
    evidence: str = Field("", description="The measured numbers behind the finding")
    severity: str = Field("medium", description="high, medium, or low")
    source: str = Field("", description="Which analysis this came from")


class StrategyPillar(BaseModel):
    """A strategic pillar of the product plan."""

    name: str = Field(..., description="Pillar name")
    objective: str = Field("", description="What the pillar sets out to achieve")
    rationale: str = Field("", description="Why this pillar, grounded in the evidence")
    linked_items: List[str] = Field(default_factory=list, description="Roadmap items serving this pillar")
    evidence: str = Field("", description="Measured basis for the pillar")


class ReportRecommendation(BaseModel):
    """A recommended action for the reader to take."""

    action: str = Field(..., description="What to do")
    owner: str = Field("Product", description="Suggested owner")
    rationale: str = Field("", description="Why now, grounded in the evidence")
    horizon: str = Field("now", description="now, next, or later")


class ReportKPI(BaseModel):
    """A product health indicator stated with its measured baseline."""

    metric: str = Field(..., description="Indicator name")
    value: str = Field(..., description="Measured value in this workspace")
    interpretation: str = Field("", description="What the value means")
    trend: str = Field("flat", description="up, down, or flat against the measured baseline")


class ReportRisk(BaseModel):
    """A risk to the plan and how to reduce it."""

    risk: str = Field(..., description="What could go wrong")
    severity: str = Field("medium", description="high, medium, or low")
    mitigation: str = Field(..., description="How to reduce or detect it")


class ReportGenerateRequest(BaseModel):
    """Payload for generating an executive summary or strategy report."""

    workspace_id: str = Field(..., description="Workspace the report is about")
    report_type: str = Field("executive_summary", description="executive_summary or product_strategy")
    audience: Optional[str] = Field("executive_leadership", description="Who the report is written for")
    period: Optional[str] = Field(None, description="Reporting period, e.g. 'Q4 2026'")
    focus: Optional[str] = Field(None, description="Optional focus area for the report")


class ReportUpdateRequest(BaseModel):
    """Editable fields of a stored report."""

    title: Optional[str] = None
    status: Optional[str] = None
    executive_summary: Optional[str] = None
    recommendations: Optional[List[Dict[str, Any]]] = None
    raw_markdown: Optional[str] = None


class ReportModel(BaseModel):
    """Complete executive or strategy report."""

    id: str = Field(..., description="Unique report ID")
    workspace_id: str = Field(..., description="Workspace ID")
    workspace_name: str = Field("", description="Workspace name")
    title: str = Field(..., description="Report title")
    report_type: str = Field("executive_summary", description="executive_summary or product_strategy")
    audience: str = Field("executive_leadership", description="Intended audience")
    period: Optional[str] = Field(None, description="Reporting period")
    status: str = Field("draft", description="draft, in_review, approved, archived")
    version: str = Field("1.0", description="Document version")
    executive_summary: str = Field("", description="The headline read for a busy executive")
    headline: str = Field("", description="One-line state of the product")
    product_health: Dict[str, Any] = Field(default_factory=dict, description="Measured health snapshot")
    key_findings: List[ReportFinding] = Field(default_factory=list, description="Evidence-backed findings")
    strategic_pillars: List[StrategyPillar] = Field(default_factory=list, description="Product strategy pillars")
    roadmap_outlook: List[Dict[str, Any]] = Field(default_factory=list, description="What ships when")
    kpis: List[ReportKPI] = Field(default_factory=list, description="Measured product indicators")
    risks: List[ReportRisk] = Field(default_factory=list, description="Risks to the plan")
    recommendations: List[ReportRecommendation] = Field(default_factory=list, description="Recommended actions")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Measured provenance block")
    ai_generated: bool = Field(False, description="Whether a model wrote the narrative")
    ai_model: str = Field("Deterministic reporting engine", description="Engine that produced the report")
    raw_markdown: str = Field("", description="Markdown rendering of the report")
    created_at: str = Field("", description="Creation timestamp (ISO)")
    updated_at: str = Field("", description="Last update timestamp (ISO)")
