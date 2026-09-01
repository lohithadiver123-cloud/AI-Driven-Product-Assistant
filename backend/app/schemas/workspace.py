"""Workspace schemas and membership models."""
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import MongoBaseModel


class WorkspaceMember(BaseModel):
    """Workspace team member reference."""

    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    role: str = Field("MEMBER", description="Role in this workspace: OWNER, ADMIN, MEMBER, VIEWER")
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkspaceCreate(BaseModel):
    """Schema for creating a new workspace."""

    name: str = Field(..., min_length=2, max_length=100, description="Workspace name")


class WorkspaceMemberAdd(BaseModel):
    """Schema for adding/inviting a user to a workspace."""

    email: str
    role: str = Field("MEMBER", description="Assigned role: ADMIN, MEMBER, VIEWER")


class WorkspaceMemberUpdate(BaseModel):
    """Schema for updating member role."""

    role: str = Field(..., description="New role: ADMIN, MEMBER, VIEWER")


class WorkspaceInDB(MongoBaseModel):
    """Workspace database entity."""

    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    owner_id: str
    members: List[WorkspaceMember] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkspaceResponse(MongoBaseModel):
    """Public workspace summary response."""

    id: str = Field(..., alias="_id", serialization_alias="id")
    name: str
    owner_id: str
    member_count: int = 1
    current_user_role: Optional[str] = "OWNER"
    created_at: datetime


class WorkspaceDetailResponse(MongoBaseModel):
    """Detailed workspace view with full members list."""

    id: str = Field(..., alias="_id", serialization_alias="id")
    name: str
    owner_id: str
    members: List[WorkspaceMember]
    current_user_role: Optional[str] = "OWNER"
    created_at: datetime
    updated_at: datetime
