"""Health and readiness check endpoints."""
from fastapi import APIRouter, status, Response
from app.config import get_settings
from app.database.connection import check_database_health
from app.schemas.health import HealthResponse, DatabaseHealthResponse

router = APIRouter(tags=["Health & Diagnostics"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Health Check",
    description="Returns general operational status of the FastAPI backend application.",
)
async def get_health():
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )


@router.get(
    "/health/database",
    response_model=DatabaseHealthResponse,
    summary="MongoDB Database Health Check",
    description="Tests live connectivity to the MongoDB database cluster by pinging the admin database and measuring round-trip latency.",
)
async def get_database_health(response: Response):
    health_data = await check_database_health()
    if health_data.get("status") != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return DatabaseHealthResponse(**health_data)
