"""Common Pydantic models, ObjectId converters, and shared utilities."""
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field
from bson import ObjectId

T = TypeVar("T")


class PyObjectId(str):
    """Custom type to handle MongoDB ObjectId in Pydantic models."""

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):
        from pydantic_core import core_schema

        def validate(value: Any) -> str:
            if isinstance(value, ObjectId):
                return str(value)
            if isinstance(value, str) and ObjectId.is_valid(value):
                return value
            raise ValueError(f"Invalid ObjectId: {value}")

        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.with_info_plain_validator_function(
                lambda v, _: validate(v)
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )


class MongoBaseModel(BaseModel):
    """Base model for all MongoDB entities with alias and type support."""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={
            ObjectId: str,
            datetime: lambda dt: dt.isoformat(),
        },
    )


class ApiResponse(BaseModel, Generic[T]):
    """Standardized API response wrapper."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized pagination envelope."""

    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
