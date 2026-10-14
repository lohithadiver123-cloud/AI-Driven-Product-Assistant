"""
MongoDB database connection using Motor async driver.
Provides a shared client instance and database reference.
Falls back to JSON-based database if MongoDB is unavailable.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings


# Create a single Motor client instance for the application
client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)

# Reference to the pm_copilot database
db = client[settings.DB_NAME]

# Flag to track if MongoDB is available
_mongodb_available = False


async def get_database() -> AsyncIOMotorClient:
    """Return the database instance for use in dependency injection."""
    return db


async def connect_to_mongo() -> None:
    """Verify MongoDB connection is alive. Call on app startup."""
    global _mongodb_available
    try:
        # Use a short timeout for the ping command
        await asyncio.wait_for(
            client.admin.command('ping'),
            timeout=5.0
        )
        print("Successfully connected to MongoDB.")
        _mongodb_available = True
        # Ensure indexes in background for fast queries
        asyncio.create_task(_ensure_indexes())
    except asyncio.TimeoutError:
        print("MongoDB connection timeout - using fallback JSON database")
        print("Check your MongoDB Atlas connection string and network")
        _mongodb_available = False
    except Exception as e:
        # Log the error but don't crash - collections will be created on first use
        print(f"MongoDB connection warning: {type(e).__name__}")
        print("Using fallback JSON database for Milestone 1 demo...")
        _mongodb_available = False


async def _ensure_indexes() -> None:
    """Create essential MongoDB indexes in background to guarantee sub-millisecond queries."""
    try:
        await db.feedback.create_index([("workspace_id", 1), ("created_at", -1)], background=True)
        await db.feedback.create_index([("workspace_id", 1)], background=True)
        await db.workspace_insights.create_index([("workspace_id", 1)], background=True)
        await db.prds.create_index([("workspace_id", 1)], background=True)
        await db.user_stories.create_index([("workspace_id", 1)], background=True)
        await db.prioritization_items.create_index([("workspace_id", 1)], background=True)
        await db.roadmaps.create_index([("workspace_id", 1)], background=True)
        await db.copilot_messages.create_index([("workspace_id", 1), ("session_id", 1)], background=True)
    except Exception as idx_err:
        print(f"Warning: Index creation non-critical error: {idx_err}")


async def close_mongo_connection() -> None:
    """Close the MongoDB client connection. Call on app shutdown."""
    if _mongodb_available:
        client.close()
        print("MongoDB connection closed.")
