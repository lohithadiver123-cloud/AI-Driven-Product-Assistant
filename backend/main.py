"""
PM Copilot Backend - FastAPI Application Entry Point.
Milestone 1: Auth, Workspace, Feedback Import/Clean/Categorize (rule-based only).
"""

import sys
import os

# Add the backend directory to Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import connect_to_mongo, close_mongo_connection
from routers import (
    auth,
    workspace,
    feedback,
    insights,
    prd,
    user_stories,
    prioritization,
    copilot,
    roadmap,
    reports,
    quality,
    outcome,
)
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — connect/disconnect from MongoDB."""
    # Startup
    await connect_to_mongo()
    yield
    # Shutdown
    await close_mongo_connection()


# Create FastAPI app
app = FastAPI(
    title="PM Copilot API",
    description="AI Product Manager Copilot — Feedback Management, Prioritization & Requirements Workspace",
    version="0.5.0",
    lifespan=lifespan,
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Disable credentials for wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers (Milestones 1 to 4)
app.include_router(auth.router)
app.include_router(workspace.router)
app.include_router(feedback.router)
app.include_router(insights.router)
app.include_router(prd.router)
app.include_router(user_stories.router)
app.include_router(prioritization.router)
app.include_router(copilot.router)
app.include_router(roadmap.router)
app.include_router(reports.router)
app.include_router(quality.router)
app.include_router(outcome.router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint to verify the API is running."""
    return {"status": "healthy", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
