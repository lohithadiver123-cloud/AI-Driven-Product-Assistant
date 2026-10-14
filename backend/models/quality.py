"""
Output quality evaluation models for Milestone 4.

Every generated artefact (insights, roadmap, PRDs, user stories, prioritization,
reports) is scored against checks that can be verified from the workspace itself:
completeness of the required sections, whether stated numbers are traceable to
measured workspace data, and whether the artefact is stale relative to the
feedback it claims to describe.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class QualityCheck(BaseModel):
    """One verifiable check applied to a generated artefact."""

    id: str = Field(..., description="Stable check ID, e.g. 'grounding.untraceable_numbers'")
    name: str = Field(..., description="Human-readable check name")
    category: str = Field(..., description="completeness, grounding, freshness, or consistency")
    status: str = Field(..., description="pass, warn, or fail")
    detail: str = Field("", description="What the check observed")
    evidence: List[str] = Field(default_factory=list, description="Concrete values the verdict rests on")


class ArtifactEvaluation(BaseModel):
    """Evaluation of one artefact family in a workspace."""

    artifact_type: str = Field(..., description="insights, roadmap, prd, user_story, prioritization, report")
    label: str = Field(..., description="Display label")
    available: bool = Field(False, description="Whether the artefact exists for this workspace")
    artifact_id: Optional[str] = Field(None, description="ID of the newest artefact evaluated")
    score: int = Field(0, description="Weighted score 0-100 across its checks")
    grade: str = Field("not_generated", description="excellent, good, fair, needs_review, or not_generated")
    passed: int = Field(0, description="Checks that passed")
    warned: int = Field(0, description="Checks that warned")
    failed: int = Field(0, description="Checks that failed")
    checks: List[QualityCheck] = Field(default_factory=list, description="Individual checks")
    notes: List[str] = Field(default_factory=list, description="Plain-language observations")


class QualityReport(BaseModel):
    """An output quality evaluation for a workspace."""

    workspace_id: str = Field(..., description="Workspace ID")
    workspace_name: str = Field("", description="Workspace name")
    evaluated_at: str = Field("", description="Evaluation timestamp (ISO)")
    overall_score: int = Field(0, description="Mean artefact score 0-100")
    grade: str = Field("not_generated", description="Overall grade")
    artifacts: List[ArtifactEvaluation] = Field(default_factory=list, description="Per-artefact evaluations")
    summary: str = Field("", description="Plain-language read of the evaluation")
    counts: Dict[str, int] = Field(default_factory=dict, description="Check tallies across all artefacts")
    raw_markdown: str = Field("", description="Markdown rendering of the evaluation")
