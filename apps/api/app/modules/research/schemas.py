"""Pydantic schemas — research module, API Specification V1 §7.
WRITTEN, NOT EXECUTED."""
from datetime import date, datetime

from pydantic import BaseModel


class ResearchCreateRequest(BaseModel):
    company_id: str
    research_type: str
    industry: str | None = None
    title: str | None = None
    summary: str | None = None


class ResearchCreateResponse(BaseModel):
    id: str
    status: str
    title: str
    summary: str


class ResearchPatchRequest(BaseModel):
    """§7.1.3/§7.1.4 — every field independently optional (partial PATCH)."""
    title: str | None = None
    summary: str | None = None
    business_quality: str | None = None
    financial_snapshot: str | None = None
    business_model: str | None = None
    competitive_position: str | None = None
    valuation_range: str | None = None
    bull_case: str | None = None
    base_case: str | None = None
    bear_case: str | None = None
    risk_register: str | None = None
    catalysts: str | None = None
    invalidation_conditions: str | None = None
    research_date: date | None = None
    conflict_disclosed: bool | None = None
    conflict_detail: str | None = None
    position_disclosed: bool | None = None
    position_detail: str | None = None
    change_note: str | None = None  # only meaningful/required on a published item, §7.1.4


class PublishRequest(BaseModel):
    change_note: str | None = None


class SourceCreateRequest(BaseModel):
    label: str
    reference: str
    supports_claim: str | None = None


class SourceResponse(BaseModel):
    id: str
    label: str
    reference: str
    supports_claim: str | None

    class Config:
        from_attributes = True


class DisclosureBlock(BaseModel):
    conflict_disclosed: bool | None
    conflict_detail: str | None
    position_disclosed: bool | None
    position_detail: str | None
    research_date: date | None


class ResearchFullResponse(BaseModel):
    """§7.1.2 full representation — returned to author, MODERATOR+, or any
    caller once access_tier/tier-gating rules permit it (see router.py)."""
    id: str
    author_id: str
    company_id: str
    research_type: str
    industry: str | None
    status: str
    moderation_status: str
    access_tier: str
    title: str
    summary: str
    current_version: int
    business_quality: str | None
    financial_snapshot: str | None
    business_model: str | None
    competitive_position: str | None
    valuation_range: str | None
    bull_case: str | None
    base_case: str | None
    bear_case: str | None
    risk_register: str | None
    catalysts: str | None
    invalidation_conditions: str | None
    disclosure: DisclosureBlock
    sources: list[SourceResponse]
    tags: list[str]
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuthorRef(BaseModel):
    """Nested author reference — API Spec §7.4.1/§7.4.2 library/search response
    contract. `name`/`username` may be null if the profile lookup ever fails
    to resolve (defensive; should not happen for a real author_id)."""
    id: str
    name: str | None = None
    username: str | None = None


class CompanyRef(BaseModel):
    """Nested company reference — API Spec §7.4.1/§7.4.2 library/search response
    contract."""
    id: str
    name: str | None = None


class ResearchPreviewResponse(BaseModel):
    """§7.1.2 — FREE caller viewing a 'core' access_tier published item."""
    preview: bool = True
    id: str
    title: str
    author: AuthorRef
    summary: str
    access_tier: str = "core"


class PublishResponse(BaseModel):
    status: str
    current_version: int


class PublishErrorFields(BaseModel):
    pass  # error body built directly in errors.py-style dict, not a strict model


class VersionListItem(BaseModel):
    version_number: int
    change_note: str
    edited_by: str
    created_at: datetime


class VersionDetail(BaseModel):
    version_number: int
    snapshot: dict
    change_note: str
    edited_by: str
    created_at: datetime
    is_current: bool


class LibraryItem(BaseModel):
    """API Spec §7.4.1/§7.4.2 — nested `author`/`company` objects, not raw
    `author_id`/`company_id` strings (contract fix, 2026-09-01)."""
    id: str
    title: str
    summary: str
    author: AuthorRef
    company: CompanyRef
    industry: str | None
    created_at: datetime
    updated_at: datetime
    status_label: str
    moderation_status: str
    tags: list[str]
    source_count: int
    current_version: int
    access_tier: str
    preview: bool = False


class LibraryListResponse(BaseModel):
    items: list[LibraryItem | ResearchPreviewResponse]
    page: int
    page_size: int
    total: int


class AccessTierUpdateRequest(BaseModel):
    access_tier: str


class AccessTierUpdateResponse(BaseModel):
    id: str
    access_tier: str


class MyResearchItem(BaseModel):
    """API Spec V2 §2 'My Research listing' — own drafts AND published items,
    unlike §7.4's public library (published-only, all authors). Deliberately
    thinner than ResearchFullResponse (no Q-RESEARCH section bodies) since
    this is a scanning list, not the editor view."""
    id: str
    title: str
    summary: str
    status: str
    company: CompanyRef
    research_type: str
    current_version: int
    published_at: str | None
    created_at: datetime
    updated_at: datetime


class MyResearchListResponse(BaseModel):
    items: list[MyResearchItem]
    page: int
    page_size: int
    total: int


class PublishToCommunityRequest(BaseModel):
    summary: str


class PublishToCommunityResponse(BaseModel):
    """The created community post — same shape as community.schemas.PostResponse,
    duplicated here (rather than importing community's schema into research) to
    avoid a cross-module schema import; the actual VALUE returned by the router
    is built by community/service.py's own serializer, so the two shapes must be
    kept in sync by hand if either changes — flagged in work_memory.md."""
    id: str
    post_type: str
    research_id: str
    content: str
    created_at: datetime
