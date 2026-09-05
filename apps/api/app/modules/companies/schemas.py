"""Pydantic schemas — companies (API Specification V1 §6, CO-001-004).
WRITTEN, NOT EXECUTED."""
from datetime import datetime

from pydantic import BaseModel

VALID_EXCHANGES = ("NSE", "BSE", "OTHER_RECOGNIZED")


class CompanyCreateRequest(BaseModel):
    name: str
    exchange: str
    sector: str | None = None
    industry: str | None = None
    website: str | None = None
    description: str | None = None


class CompanyUpdateRequest(BaseModel):
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    website: str | None = None
    description: str | None = None


class CompanyMergeRequest(BaseModel):
    target_company_id: str


class CompanyResponse(BaseModel):
    id: str
    name: str
    exchange: str
    sector: str | None
    industry: str | None
    website: str | None
    description: str | None
    is_merged_into: str | None
    research_count: int = 0
    discussion_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
    page: int
    page_size: int
