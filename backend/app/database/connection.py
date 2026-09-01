"""MongoDB connection and lifecycle management module."""
import logging
import time
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from app.config import get_settings
from app.database.collections import Collections

logger = logging.getLogger("ai_product_assistant.database")


class DatabaseManager:
    """Singleton MongoDB Client & Database Manager."""

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None

    async def connect(self) -> None:
        """Initialize MongoDB client and connect to cluster."""
        settings = get_settings()
        try:
            logger.info("Initializing MongoDB connection to %s", settings.DATABASE_NAME)
            self.client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
            self.database = self.client[settings.DATABASE_NAME]
            # Verify connectivity with ping command
            await self.client.admin.command("ping")
            logger.info("Successfully connected to MongoDB database: %s", settings.DATABASE_NAME)

            # Ensure essential indexes
            await self.ensure_indexes()
        except Exception as err:
            logger.error("Failed to connect to MongoDB: %s", err)
            raise err

    async def ensure_indexes(self) -> None:
        """Create necessary database indexes for auth and workspace isolation."""
        if self.database is None:
            return
        try:
            # Users collection: unique email
            await self.database[Collections.USERS].create_index("email", unique=True)
            # Workspaces: owner_id, member user_ids
            await self.database[Collections.WORKSPACES].create_index("owner_id")
            await self.database[Collections.WORKSPACES].create_index("members.user_id")
            # Refresh Tokens: unique token_hash, user_id
            await self.database[Collections.REFRESH_TOKENS].create_index("token_hash", unique=True)
            await self.database[Collections.REFRESH_TOKENS].create_index("user_id")
            # Password Reset Tokens: unique token_hash, user_id
            await self.database[Collections.PASSWORD_RESET_TOKENS].create_index("token_hash", unique=True)
            await self.database[Collections.PASSWORD_RESET_TOKENS].create_index("user_id")
            # Email Verification Tokens: unique token_hash, user_id
            await self.database[Collections.EMAIL_VERIFICATION_TOKENS].create_index("token_hash", unique=True)
            await self.database[Collections.EMAIL_VERIFICATION_TOKENS].create_index("user_id")
            # Feedback: workspace_id, category, sentiment
            await self.database[Collections.FEEDBACK].create_index("workspace_id")
            await self.database[Collections.FEEDBACK].create_index("category")
            # Support Tickets: workspace_id, ticket_id
            await self.database[Collections.SUPPORT_TICKETS].create_index("workspace_id")
            logger.info("Database indexes verified/created successfully.")
        except Exception as exc:
            logger.warning("Non-critical index creation warning: %s", exc)

    async def disconnect(self) -> None:
        """Close MongoDB connection gracefully."""
        if self.client:
            logger.info("Closing MongoDB connection...")
            self.client.close()
            self.client = None
            self.database = None
            logger.info("MongoDB connection closed.")

    def get_database(self) -> AsyncIOMotorDatabase:
        """Return the active database instance."""
        if self.database is None:
            raise RuntimeError("Database is not initialized. Make sure connect() was called during startup.")
        return self.database

    def get_collection(self, collection_name: str) -> AsyncIOMotorCollection:
        """Return a collection by name from the active database."""
        db = self.get_database()
        return db[collection_name]

    async def health_check(self) -> Dict[str, Any]:
        """Perform a ping on MongoDB and measure latency."""
        settings = get_settings()
        if not self.client:
            return {
                "status": "unhealthy",
                "database": "disconnected",
                "database_name": settings.DATABASE_NAME,
                "latency_ms": None,
                "error": "MongoDB client is not initialized"
            }

        start_time = time.perf_counter()
        try:
            await self.client.admin.command("ping")
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            collection_names = await self.database.list_collection_names()
            
            return {
                "status": "healthy",
                "database": "connected",
                "database_name": settings.DATABASE_NAME,
                "latency_ms": latency_ms,
                "collections_count": len(collection_names),
                "collections": collection_names,
            }
        except Exception as err:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning("Database health check failed: %s", err)
            return {
                "status": "unhealthy",
                "database": "error",
                "database_name": settings.DATABASE_NAME,
                "latency_ms": latency_ms,
                "error": str(err)
            }


# Singleton instance
db_manager = DatabaseManager()


async def connect_to_mongo() -> None:
    """Connect helper for FastAPI lifecycle."""
    await db_manager.connect()


async def close_mongo_connection() -> None:
    """Close helper for FastAPI lifecycle."""
    await db_manager.disconnect()


def get_database() -> AsyncIOMotorDatabase:
    """Dependency helper to get the active database."""
    return db_manager.get_database()


def get_collection(name: str) -> AsyncIOMotorCollection:
    """Dependency helper to get a collection by name."""
    return db_manager.get_collection(name)


async def check_database_health() -> Dict[str, Any]:
    """Helper to check database health."""
    return await db_manager.health_check()
