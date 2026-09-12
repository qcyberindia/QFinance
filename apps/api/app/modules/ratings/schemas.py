from pydantic import BaseModel, Field


class RatingCreateRequest(BaseModel):
    score: int = Field(ge=1, le=5)


class RatingResponse(BaseModel):
    post_id: str
    score: int


class RatingSummaryResponse(BaseModel):
    average: float | None  # None (not 0) when count == 0 — "no ratings yet" is not "average 0"
    count: int
