"""Q-Points responses. Q-Points are a reputation/contribution score — these
schemas deliberately carry no currency, balance or paise fields."""
from datetime import datetime

from pydantic import BaseModel


class QPointEntryResponse(BaseModel):
    points: int
    source_type: str
    reason: str
    created_at: datetime


class QPointsSummaryResponse(BaseModel):
    points: int
    entries: list[QPointEntryResponse]
    page: int
    page_size: int
    total: int
