"""Journal schemas — API Specification V2 §1. WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.modules.journal.models import VALID_ENTRY_TYPES


class JournalEntryCreateRequest(BaseModel):
    content: str
    entry_type: str
    company_id: str | None = None


class JournalEntryPatchRequest(BaseModel):
    content: str | None = None
    entry_type: str | None = None
    company_id: str | None = None


class JournalEntryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID | None
    entry_type: str
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JournalEntryListResponse(BaseModel):
    items: list[JournalEntryResponse]
    page: int
    page_size: int
    total: int
