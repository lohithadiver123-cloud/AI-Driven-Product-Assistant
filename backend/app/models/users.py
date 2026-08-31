from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserInDB(BaseModel):
    _id: Optional[str] = Field(None, alias="id")
    name: str
    email: EmailStr
    password_hash: str
    workspace_id: Optional[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
