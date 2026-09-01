"""User schemas and validation models."""
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from app.schemas.common import MongoBaseModel


class UserBase(BaseModel):
    """Base user fields."""

    name: str = Field(..., min_length=2, max_length=100, description="User full name")
    email: EmailStr = Field(..., description="User email address")


class UserRegisterRequest(BaseModel):
    """Schema for user registration with automatic workspace creation."""

    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr = Field(...)
    password: str = Field(..., min_length=8, description="Plain-text password")
    confirm_password: str = Field(..., min_length=8)
    workspace_name: Optional[str] = Field(None, max_length=100, description="Custom workspace name")


class UserLoginRequest(BaseModel):
    """Schema for user credentials authentication."""

    email: EmailStr
    password: str
    device_info: Optional[str] = Field("Browser Session", description="Optional device signature")


class ChangePasswordRequest(BaseModel):
    """Schema for authenticated password change."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class UserInDB(MongoBaseModel, UserBase):
    """Internal user model stored in MongoDB."""

    id: Optional[str] = Field(default=None, alias="_id")
    password_hash: str
    role: str = Field("OWNER", description="Global/default role: OWNER, ADMIN, MEMBER, VIEWER")
    email_verified: bool = Field(False)
    workspace_ids: List[str] = Field(default_factory=list)
    current_workspace_id: Optional[str] = None
    is_active: bool = Field(True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None


class UserResponse(MongoBaseModel, UserBase):
    """Public user response model without password hash."""

    id: str = Field(..., alias="_id", serialization_alias="id")
    role: str
    email_verified: bool
    workspace_ids: List[str] = Field(default_factory=list)
    current_workspace_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class UserProfileResponse(BaseModel):
    """Authenticated user profile with active workspace details."""

    id: str
    name: str
    email: str
    role: str
    email_verified: bool
    workspace_ids: List[str]
    current_workspace_id: Optional[str]
    workspace_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
