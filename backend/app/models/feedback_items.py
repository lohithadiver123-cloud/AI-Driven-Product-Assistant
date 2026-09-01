from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class FeedbackItemInDB(BaseModel):
    _id: Optional[str] = None
    workspace_id: str
    text: str
    source: str  # csv/manual/review/ticket
    date: Optional[datetime] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    status: str = "raw"  # raw/cleaned
