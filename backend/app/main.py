"""Main FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database.connection import connect_to_mongo, close_mongo_connection
from app.api.health import router as health_router
from app.api.router import api_router

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_product_assistant")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown events."""
    settings = get_settings()
    logger.info("Starting up %s v%s in %s mode...", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    
    # Initialize MongoDB connection
    try:
        await connect_to_mongo()
        logger.info("MongoDB initialized successfully.")
    except Exception as exc:
        logger.warning("MongoDB connection failed at startup: %s. Application will run in degraded mode.", exc)

    yield

    # Teardown MongoDB connection
    logger.info("Shutting down %s...", settings.APP_NAME)
    try:
        await close_mongo_connection()
    except Exception as exc:
        logger.error("Error closing MongoDB connection: %s", exc)


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AI-Driven Product Assistant Backend API. "
        "Provides data ingestion, feedback processing, support ticket management, "
        "and product requirements workspace foundation."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Configuration
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/",
    tags=["Root"],
    summary="API Root Information",
    description="Returns top-level metadata, status, and links to interactive API documentation.",
)
async def root():
    """Root endpoint providing metadata and API status."""
    return JSONResponse(
        content={
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "online",
            "environment": settings.ENVIRONMENT,
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "health_url": "/health",
            "database_health_url": "/health/database",
            "api_v1_prefix": settings.API_PREFIX,
        }
    )


# Include health routes at root level: /health, /health/database
app.include_router(health_router)

# Include API v1 routes: /api/v1/...
app.include_router(api_router, prefix=settings.API_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
