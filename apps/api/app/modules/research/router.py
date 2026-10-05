"""Research routes — API Specification V1 §7. Thin; delegates to service.py.

Route registration order matters in FastAPI (first match wins): static paths
(/library, /search, /export.csv) MUST be registered before the dynamic
/{research_id} routes, or "library"/"search"/"export.csv" would be parsed as a
research_id and 404/422 instead of hitting the intended handler. This ordering
was deliberately checked, not accidental — see work_memory.md for the earlier
draft that had this bug before it was caught and fixed.

WRITTEN, NOT EXECUTED."""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_profile, require_csrf, require_role, require_verified_profile
from app.modules.research import service
from app.modules.research.schemas import (
    AddAIFindingRequest, AddAIFindingResponse,
    PublishRequest, PublishToCommunityRequest,
    ResearchCreateRequest, ResearchCreateResponse, ResearchPatchRequest, SourceCreateRequest, SourceResponse,
    ResearchAIAskRequest, ResearchAIAskResponse,
)
from app.modules.users.models import Profile
from app.modules.ai import service as ai_service
from app.modules.research.ai_context import get_ai_context
from app.modules.research.sections import next_stage_key

router = APIRouter(prefix="/research", tags=["research"])

_STAFF_ROLES = {"MODERATOR", "ADMIN", "SUPER_ADMIN"}


def _is_staff(profile: Profile) -> bool:
    return bool(_STAFF_ROLES & set(profile.role_grants))


# ---------------------------------------------------------------------------
# 7.4 Library, search, export — registered FIRST (static paths before /{id})
# ---------------------------------------------------------------------------

@router.get("/library")
async def library(
    company_id: uuid.UUID | None = Query(default=None),
    industry: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_moderated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    """`include_moderated` (API Spec §12 item 3, end of §10) has no effect
    unless the caller is MODERATOR/ADMIN/SUPER_ADMIN — `is_staff` is computed
    server-side from `profile.role_grants` here and passed to the service
    layer alongside the raw query-string value; service.list_library only
    honors the override when BOTH are true, so an ordinary member setting
    `?include_moderated=true` gets the normal, unchanged default result."""
    items, total = await service.list_library(
        db, company_id=company_id, industry=industry, page=page, page_size=page_size,
        include_moderated=include_moderated, is_staff=_is_staff(profile),
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/search")
async def search(
    q: str = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_moderated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    items, total = await service.search_research(
        db, query=q, page=page, page_size=page_size,
        include_moderated=include_moderated, is_staff=_is_staff(profile),
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/export.csv")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """FIX (this pass): previously gated on `require_role("MEMBER")` as a
    deliberate Pro-tier feature. The MVP product rule is now explicit and
    absolute: MVP is 100% free, single Basic tier, no Pro/Premium gates
    anywhere in MVP participation flows. Exporting one's own research is
    exactly the kind of thing a verified member should be able to do -
    changed to `require_verified_profile`, matching every other endpoint in
    this file. The `MEMBER` role_grant and `require_role` dependency remain
    in the codebase (still legitimately used for ADMIN/SUPER_ADMIN staff
    gates, e.g. access-tier below) - only this specific MVP-participation
    gate was removed."""
    csv_text = await service.export_csv(db, author_id=profile.user_id)
    return StreamingResponse(iter([csv_text]), media_type="text/csv",
                              headers={"Content-Disposition": "attachment; filename=research_export.csv"})


@router.get("/mine")
async def list_my_research(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """API Spec V2 §2 — registered here, alongside the other static paths
    (/library, /search, /export.csv), before the dynamic /{research_id}
    routes below — 'mine' would otherwise be parsed as a research_id.

    Basic/Pro product decision: viewing your OWN research/thesis drafts is
    core "document what I believe" participation, not a Pro perk — changed
    from require_role("MEMBER") to require_verified_profile, matching
    create_research/publish_to_community below."""
    items, total = await service.list_my_research(db, author_id=profile.user_id, page=page, page_size=page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


# ---------------------------------------------------------------------------
# 7.1 Create / edit / draft
# ---------------------------------------------------------------------------

@router.post("", response_model=ResearchCreateResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_research(
    body: ResearchCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """Basic/Pro product decision: creating a research draft/thesis is core
    "document what I believe" participation — changed from
    require_role("MEMBER") to require_verified_profile."""
    research = await service.create_research(
        db, author_id=profile.user_id, company_id=uuid.UUID(body.company_id),
        research_type=body.research_type, industry=body.industry, title=body.title, summary=body.summary,
    )
    return ResearchCreateResponse(id=str(research.id), status=research.status,
                                   title=research.title, summary=research.summary)


@router.post(
    "/{research_id}/ai/ask",
    response_model=ResearchAIAskResponse,
    dependencies=[Depends(require_csrf)],
)
async def ask_research_ai(
    research_id: uuid.UUID,
    body: ResearchAIAskRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """Ask the user's connected BYOK Research Assistant about this research.

    The AI receives only persisted research context plus the user's question.
    The API key is resolved/decrypted internally and is never exposed to the
    request or response.
    """
    question = body.normalized_question

    if not question:
        from app.core.errors import QFinanceAPIError
        raise QFinanceAPIError(
            "AI_QUESTION_EMPTY",
            "Enter a research question.",
            400,
        )

    if len(question) > 4000:
        from app.core.errors import QFinanceAPIError
        raise QFinanceAPIError(
            "AI_QUESTION_TOO_LONG",
            "Research questions must be 4,000 characters or fewer.",
            400,
        )

    context = await get_ai_context(
        db,
        research_id,
        actor_id=profile.user_id,
    )

    adapter, api_key, connection = await ai_service.resolve_provider_for_user(
        db,
        user_id=profile.user_id,
    )

    context_payload = {
        "research_question": context.research_question,
        "subject_type": context.subject_type,
        "company": {
            "name": context.company_name,
            "symbol": context.symbol,
            "exchange": context.exchange,
            "sector": context.sector,
            "industry": context.industry,
            "description": context.company_description,
        },
        "current_stage": context.current_stage,
        "saved_findings": context.saved_findings,
        "assumptions": context.assumptions,
        "risks": context.risks,
        "invalidation_conditions": context.invalidation_conditions,
    }

    system_prompt = """You are Qfinera's Research Assistant.

Your role is to help a retail investor investigate and challenge an
investment research question. You are an analytical research assistant,
not a financial adviser.

RULES:
- Use the research context supplied below.
- Do not invent company facts, financial figures, sources, or events.
- Clearly distinguish facts from interpretation.
- If the supplied context is insufficient, say what information is missing.
- Do not issue personalized BUY, SELL, or HOLD instructions.
- Do not provide target prices or trading signals.
- Challenge assumptions and identify risks where relevant.
- Keep the response structured and educational.
- Do not modify the research document yourself.
- The user decides what, if anything, gets added to their research.

RESEARCH CONTEXT:
""" + __import__("json").dumps(context_payload, ensure_ascii=False, default=str)

    answer = await adapter.ask(
        api_key=api_key,
        system_prompt=system_prompt,
        question=question,
    )

    return ResearchAIAskResponse(
        answer=answer,
        current_stage=context.current_stage,
        provider=connection.provider,
        model=connection.model,
    )


@router.post(
    "/{research_id}/ai/add-to-research",
    response_model=AddAIFindingResponse,
    dependencies=[Depends(require_csrf)],
)
async def add_ai_finding_to_research(
    research_id: uuid.UUID,
    body: AddAIFindingRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """Explicit-only: the AI never calls this itself; only a user clicking
    "Add to Research" reaches this route. Ownership is enforced in
    service.add_ai_finding via the same `_require_author` every other mutating
    research route uses. The saved content lands in the SAME field the
    section's own textarea edits — it is immediately editable there, not a
    separate immutable AI record (see service.add_ai_finding's docstring)."""
    result = await service.add_ai_finding(
        db, research_id=research_id, actor_id=profile.user_id,
        stage=body.stage, question=body.question, answer=body.answer,
    )
    return AddAIFindingResponse(**result)


@router.get("/{research_id}")
async def get_research(
    research_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    return await service.get_research_view(
        db, research_id, viewer_id=profile.user_id, is_staff=_is_staff(profile),
    )


@router.patch("/{research_id}", dependencies=[Depends(require_csrf)])
async def patch_research(
    research_id: uuid.UUID,
    body: ResearchPatchRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    """Dispatches to the draft-edit (§7.1.3) or published-edit (§7.1.4/AD-17)
    flow depending on the item's current status — both require authorship,
    enforced inside service.py, not just here."""
    research = await service.get_research_or_404(db, research_id)
    patch = body.model_dump(exclude_unset=True)
    if research.status == "draft":
        updated = await service.patch_draft(db, research_id=research_id, actor_id=profile.user_id, patch=patch)
        return {"id": str(updated.id), "status": updated.status, "title": updated.title, "summary": updated.summary}
    updated = await service.patch_published(db, research_id=research_id, actor_id=profile.user_id, patch=patch)
    return {"status": updated.status, "current_version": updated.current_version,
            "title": updated.title, "summary": updated.summary}


# ---------------------------------------------------------------------------
# 7.2 Sources
# ---------------------------------------------------------------------------

@router.post("/{research_id}/sources", response_model=SourceResponse, status_code=201,
             dependencies=[Depends(require_csrf)])
async def add_source(
    research_id: uuid.UUID,
    body: SourceCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    source = await service.add_source(
        db, research_id=research_id, actor_id=profile.user_id,
        label=body.label, reference=body.reference, supports_claim=body.supports_claim,
    )
    return SourceResponse(id=str(source.id), label=source.label, reference=source.reference,
                           supports_claim=source.supports_claim)


@router.delete("/{research_id}/sources/{source_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_source(
    research_id: uuid.UUID,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    await service.delete_source(db, research_id=research_id, source_id=source_id, actor_id=profile.user_id)


@router.get("/{research_id}/sources", response_model=list[SourceResponse])
async def list_sources(
    research_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    await service.get_research_view(
        db, research_id, viewer_id=profile.user_id, is_staff=_is_staff(profile),
    )
    sources = await service.list_sources(db, research_id)
    return [SourceResponse(id=str(s.id), label=s.label, reference=s.reference, supports_claim=s.supports_claim)
            for s in sources]


# ---------------------------------------------------------------------------
# 7.3 Publishing and versioning
# ---------------------------------------------------------------------------

@router.post("/{research_id}/publish", dependencies=[Depends(require_csrf)])
async def publish_research(
    research_id: uuid.UUID,
    body: PublishRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    research = await service.publish(db, research_id=research_id, actor_id=profile.user_id,
                                      change_note=body.change_note)
    return {"status": research.status, "current_version": research.current_version}


@router.post("/{research_id}/publish-to-community", dependencies=[Depends(require_csrf)])
async def publish_to_community(
    research_id: uuid.UUID,
    body: PublishToCommunityRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """API Spec V2 §2. Bridges an already-published research item into a
    Community thesis post, then records a `thesis_published` contribution
    (Architecture V2 §7) — a self-engagement guard isn't needed for this
    specific event (unlike likes/comments/ratings, publishing your own thesis
    is the intended, sole trigger, not something to filter as 'self-
    engagement').

    Basic/Pro product decision: explicitly listed as a Basic action — changed
    from require_role("MEMBER") to require_verified_profile."""
    post = await service.publish_to_community(db, research_id=research_id, actor_id=profile.user_id,
                                               summary=body.summary)
    from app.modules.contributions import service as contributions_service
    await contributions_service.record_thesis_published(db, user_id=profile.user_id, research_id=research_id)
    return post


@router.get("/{research_id}/versions")
async def list_versions(
    research_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    await service.get_research_view(
        db, research_id, viewer_id=profile.user_id, is_staff=_is_staff(profile),
    )
    versions, total = await service.list_versions(db, research_id, page=page, page_size=page_size)
    return {
        "items": [{"version_number": v.version_number, "change_note": v.change_note,
                   "edited_by": str(v.edited_by), "created_at": v.created_at} for v in versions],
        "page": page, "page_size": page_size, "total": total,
    }


@router.get("/{research_id}/versions/{version_number}")
async def get_version(
    research_id: uuid.UUID,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    await service.get_research_view(
        db, research_id, viewer_id=profile.user_id, is_staff=_is_staff(profile),
    )
    version, is_current = await service.get_version(db, research_id, version_number)
    return {"version_number": version.version_number, "snapshot": version.snapshot,
            "change_note": version.change_note, "edited_by": str(version.edited_by),
            "created_at": version.created_at, "is_current": is_current}
