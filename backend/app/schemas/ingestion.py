"""Schemas for data ingestion quality reports and file upload status."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IngestionRowError(BaseModel):
    """Detailed error info for a specific row during dataset ingestion."""

    row_index: int = Field(..., description="1-indexed row number in the source file")
    reason: str = Field(..., description="Reason for validation or ingestion failure")
    raw_data: Optional[Dict[str, Any]] = Field(default=None, description="Snapshot of the malformed row data")


class IngestionReport(BaseModel):
    """Comprehensive data quality and ingestion metrics report."""

    success: bool = Field(..., description="Overall ingestion outcome")
    message: str = Field(..., description="Summary status message")
    filename: Optional[str] = Field(None, description="Uploaded file name")
    total_records: int = Field(0, description="Total rows encountered in input file")
    valid_records: int = Field(0, description="Number of structurally valid records")
    processed_records: int = Field(0, description="Number of records cleaned and inserted into DB")
    duplicate_records: int = Field(0, description="Number of duplicate records skipped")
    empty_text_records: int = Field(0, description="Number of rows rejected due to empty feedback text")
    invalid_records: int = Field(0, description="Number of rows rejected due to missing or invalid fields")
    errors: List[IngestionRowError] = Field(default_factory=list, description="Row-by-row failure breakdown")
    inserted_ids: List[str] = Field(default_factory=list, description="MongoDB _id strings of newly inserted items")
    categories_summary: Dict[str, int] = Field(default_factory=dict, description="Count of records per detected category")
    sentiment_summary: Dict[str, int] = Field(default_factory=dict, description="Count of records per detected sentiment")
