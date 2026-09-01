"""Main API Router aggregator."""
from fastapi import APIRouter
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.workspaces import router as workspaces_router
from app.api.feedback import router as feedback_router
from app.api.support_tickets import router as support_tickets_router

api_router = APIRouter()

# Register core routers
api_router.include_router(auth_router)
api_router.include_router(workspaces_router)
api_router.include_router(feedback_router)
api_router.include_router(support_tickets_router)

__all__ = ["api_router", "health_router"]
