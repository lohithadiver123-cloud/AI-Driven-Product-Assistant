from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class WorkspaceInDB(BaseModel):
    _id: Optional[str] = None
    name: str
    owner_id: Optional[str]
    created_at: datetime = datetime.utcnow()
