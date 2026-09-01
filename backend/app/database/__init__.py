"""Database module initialization."""
from app.database.connection import (
    connect_to_mongo,
    close_mongo_connection,
    get_database,
    get_collection,
    check_database_health,
    db_manager
)
from app.database.collections import Collections

__all__ = [
    "connect_to_mongo",
    "close_mongo_connection",
    "get_database",
    "get_collection",
    "check_database_health",
    "db_manager",
    "Collections",
]
