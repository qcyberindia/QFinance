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
    management_notes: str | None = None
    assumptions_outlook: str | None = None
    research_date: date | None = None
    conflict_disclosed: bool | None = None
    conflict_detail: str | None = None
    position_disclosed: bool | None = None
    position_detail: str | None = None
    change_note: str | None = None  # only meaningful/required on a published item, §7.1.4



class ResearchAIAskRequest(BaseModel):
    """A question sent to the user's connected BYOK Research Assistant."""
    question: str

    @property
    def normalized_question(self) -> str:
        return self.question.strip()


class ResearchAIAskResponse(BaseModel):
    """AI answer plus the research context stage used for the response."""
    answer: str
    current_stage: str
    provider: str
    model: str | None = None


class AddAIFindingRequest(BaseModel):
    """Explicit user action only — the AI never calls this itself. `stage` must
    be one of research/sections.py's ADD_TO_RESEARCH_STAGES keys (validated in
    service.py, not here, so the error message can list the exact valid set)."""
    stage: str
    question: str
    answer: str


class AddAIFindingResponse(BaseModel):
    added: bool
    already_added: bool
    stage: str
    field: str
    content: str


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


class CompanyRef(BaseModel):
    """Nested company reference — API Spec §7.4.1/§7.4.2 library/search response
    contract. Extended in Research Phase 3 with symbol/exchange/sector/
    industry/description (all optional — absence is real absence, never
    fabricated) so `GET /research/{id}` can carry the full Research Subject
    context in one call, per that phase's explicit preference for reusing
    this endpoint over adding a dedicated one. Defined here (moved above
    ResearchFullResponse, which is the first class to reference it —
    Pydantic v2 evaluates annotations at class-definition time, so the
    referencing class must come after this one, not before)."""
    id: str
    name: str | None = None
    symbol: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    description: str | None = None


class ResearchFullResponse(BaseModel):
    """§7.1.2 full representation — returned to the author/staff for drafts
    and to any member for published research (Qfinera is free; no tiers)."""
    id: str
    author_id: str
    company_id: str
    company: CompanyRef
    brief: dict
    research_type: str
    industry: str | None
    status: str
    moderation_status: str
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
    management_notes: str | None
    assumptions_outlook: str | None
    disclosure: DisclosureBlock
    sources: list[SourceResponse]
    tags: list[str]
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuthorRef(BaseModel):
    """Nested author reference — API Spec §7.4.1/§7.4.2 library/search response
    contract. SECURITY FIX (this pass): `name` removed — previously exposed
    the author's real registration name on every public library/search item;
    `username` is the only public identity a research item's author has."""
    id: str
    username: str | None = None


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


class LibraryListResponse(BaseModel):
    items: list[LibraryItem]
    page: int
    page_size: int
    total: int


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
