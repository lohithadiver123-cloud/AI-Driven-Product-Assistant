"""Health check schema responses."""
from typing import List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """General service health status."""

    status: str = Field("healthy", description="Service health state")
    app_name: str
    version: str
    environment: str


class DatabaseHealthResponse(BaseModel):
    """Database health and connectivity status."""

    status: str = Field(..., description="Database connection status: 'healthy' or 'unhealthy'")
    database: str = Field(..., description="Connection status: 'connected', 'disconnected', or 'error'")
    database_name: str
    latency_ms: Optional[float] = Field(None, description="Round-trip latency in milliseconds")
    collections_count: Optional[int] = Field(None, description="Number of collections found in DB")
    collections: Optional[List[str]] = Field(None, description="List of collections")
    error: Optional[str] = Field(None, description="Error message if unhealthy")
