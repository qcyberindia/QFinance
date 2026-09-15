"""Profile schemas — API Specification V2 §6 (P.1). WRITTEN, NOT EXECUTED."""
from datetime import datetime

from pydantic import BaseModel


class PublicPostSummary(BaseModel):
    id: str
    post_type: str
    content: str
    created_at: datetime


class PublicProfileResponse(BaseModel):
    """Never includes journal/drafts/broker/portfolio fields — this Pydantic
    model simply has no field name for any of them, so a future careless
    change to service.py can add extra dict keys without them ever reaching
    the client (FastAPI's response_model drops unknown keys silently), per
    PRD V2 §4.7's explicit privacy requirement."""
    username: str
    name: str | None
    bio: str | None
    published_posts_count: int
    published_theses_count: int
    contribution_points: int
    recent_posts: list[PublicPostSummary]
