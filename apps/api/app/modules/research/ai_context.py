"""Research AI Context — the ONE authoritative context builder (consolidated
in this pass; a second, near-duplicate `context.py` written in an earlier
pass has been retired to `context.py.disabled`, keeping this file because it
is a typed dataclass and the name other work already references).

A pure assembly over data ALREADY persisted in `research` + `companies`. It
persists nothing, has no model/table/migration, makes no AI call, and
structurally cannot carry an API key, email, real name, broker credential or
session secret: no field for any of them exists, and `build_research_ai_
context()` has no parameter that could smuggle one in. BYOK stays solely in
`app/modules/ai/` — this module never imports it.

RESEARCH QUESTION SOURCE (bug fixed in an earlier pass): the Start Research UI writes
the question into both `title` and `summary`, but Section 01 of the
workspace edits `summary` afterwards. `summary` is therefore the live
question; `title` is only its value at creation. This builder reads
`summary`, falling back to `title` only when `summary` is empty.

CURRENT_STAGE BUG FIXED THIS PASS: `current_stage` previously iterated
`QRES_STAGE_FIELDS + EXTENDED_SECTION_FIELDS` in raw column-declaration
order. That set includes `business_quality`, a column the actual frontend
workspace (`research-progress.ts`) never binds to any section at all — a
user could never fill it, so `current_stage` would get stuck reporting
"business_quality" forever on any real research item. It also omitted
Section 01 and didn't group bull/base/bear as the single "scenarios" section
the UI treats them as. Now delegates to `research/sections.py`, the one
place that mirrors the frontend's real section list, so the two cannot
drift again without both being edited.
"""
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.research.models import Research
from app.modules.research.sections import current_stage_key


def research_question_of(research: Research) -> str:
    """Single source of truth for 'what is the research question' — used by
    both the AI context and the Initial Research Brief so they cannot drift."""
    return (research.summary or "").strip() or (research.title or "").strip()


@dataclass
class ResearchAIContext:
    research_id: str
    subject_type: str  # "STOCK" only — Industry/Economy have no persistable subject yet (research.company_id is NOT NULL)
    company_id: str
    company_name: str | None
    symbol: str | None
    exchange: str | None
    sector: str | None
    industry: str | None
    company_description: str | None
    research_question: str
    current_stage: str  # first unfilled section field, or "review" when all are filled
    previous_questions: list[str] = field(default_factory=list)  # always [] — no question log is persisted anywhere yet
    saved_findings: dict[str, str] = field(default_factory=dict)  # non-empty section fields the USER wrote, keyed by field
    user_notes: list[str] = field(default_factory=list)  # always [] — no notes model exists; not faked
    assumptions: str | None = None
    risks: str | None = None
    invalidation_conditions: str | None = None


def build_research_ai_context(research: Research, *, company: dict) -> ResearchAIContext:
    """Pure: no I/O. `company` is the dict `service._load_author_and_company`
    already builds for `GET /research/{id}`."""
    from app.modules.research.models import EXTENDED_SECTION_FIELDS, QRES_STAGE_FIELDS

    def _filled(name: str) -> bool:
        value = getattr(research, name)
        return bool(value) and str(value).strip() != ""

    # saved_findings still reports every real column the researcher has
    # written (unrelated to the current_stage fix above) — an AI prompt
    # benefits from seeing all filled sections, not just the "next" one.
    all_fields = (*QRES_STAGE_FIELDS, *EXTENDED_SECTION_FIELDS)
    saved_findings = {f: getattr(research, f) for f in all_fields if _filled(f)}
    current_stage = current_stage_key(research)

    return ResearchAIContext(
        research_id=str(research.id),
        subject_type="STOCK",
        company_id=str(research.company_id),
        company_name=company.get("name"),
        symbol=company.get("symbol"),
        exchange=company.get("exchange"),
        sector=company.get("sector"),
        industry=company.get("industry"),
        company_description=company.get("description"),
        research_question=research_question_of(research),
        current_stage=current_stage,
        saved_findings=saved_findings,
        assumptions=research.assumptions_outlook,
        risks=research.risk_register,
        invalidation_conditions=research.invalidation_conditions,
    )


async def get_ai_context(db: AsyncSession, research_id: uuid.UUID, *, actor_id: uuid.UUID) -> ResearchAIContext:
    """Author-only: saved findings/assumptions/risks can be an unpublished
    draft's private thinking. Imported lazily to avoid a service<->context
    import cycle. Called by research/router.py's POST /{id}/ai/ask."""
    from app.modules.research import service as research_service

    research = await research_service.get_research_or_404(db, research_id)
    research_service._require_author(research, actor_id)
    _, company = await research_service._load_author_and_company(
        db, author_id=research.author_id, company_id=research.company_id,
    )
    return build_research_ai_context(research, company=company)
