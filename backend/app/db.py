import os
from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings


_client: AsyncIOMotorClient = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        if not settings.MONGO_URI:
            raise RuntimeError("MONGO_URI is not set in environment or .env file")
        _client = AsyncIOMotorClient(settings.MONGO_URI)
    return _client


def get_db():
    client = get_client()
    return client[settings.MONGO_DB]


def get_collections():
    db = get_db()
    return {
        "users": db["users"],
        "workspaces": db["workspaces"],
        "feedback_items": db["feedback_items"],
    }
