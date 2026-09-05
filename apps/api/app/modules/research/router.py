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
from app.core.deps import get_current_profile, require_csrf, require_role
from app.modules.research import service
from app.modules.research.schemas import (
    AccessTierUpdateRequest, AccessTierUpdateResponse, PublishRequest, ResearchCreateRequest,
    ResearchCreateResponse, ResearchPatchRequest, SourceCreateRequest, SourceResponse,
)
from app.modules.users.models import Profile

router = APIRouter(prefix="/research", tags=["research"])

_STAFF_ROLES = {"MODERATOR", "ADMIN", "SUPER_ADMIN"}


def _is_member(profile: Profile) -> bool:
    return "MEMBER" in profile.role_grants


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
        viewer_is_member=_is_member(profile), include_moderated=include_moderated, is_staff=_is_staff(profile),
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
        db, query=q, page=page, page_size=page_size, viewer_is_member=_is_member(profile),
        include_moderated=include_moderated, is_staff=_is_staff(profile),
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/export.csv")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
):
    csv_text = await service.export_csv(db, author_id=profile.user_id)
    return StreamingResponse(iter([csv_text]), media_type="text/csv",
                              headers={"Content-Disposition": "attachment; filename=research_export.csv"})


# ---------------------------------------------------------------------------
# 7.1 Create / edit / draft
# ---------------------------------------------------------------------------

@router.post("", response_model=ResearchCreateResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_research(
    body: ResearchCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
):
    research = await service.create_research(
        db, author_id=profile.user_id, company_id=uuid.UUID(body.company_id),
        research_type=body.research_type, industry=body.industry, title=body.title, summary=body.summary,
    )
    return ResearchCreateResponse(id=str(research.id), status=research.status,
                                   title=research.title, summary=research.summary)


@router.get("/{research_id}")
async def get_research(
    research_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    return await service.get_research_view(
        db, research_id, viewer_id=profile.user_id, viewer_is_member=_is_member(profile), is_staff=_is_staff(profile),
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
    return SourceResponse.model_validate(source)


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
        db, research_id, viewer_id=profile.user_id, viewer_is_member=_is_member(profile), is_staff=_is_staff(profile),
    )
    sources = await service.list_sources(db, research_id)
    return [SourceResponse.model_validate(s) for s in sources]


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


@router.get("/{research_id}/versions")
async def list_versions(
    research_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    await service.get_research_view(
        db, research_id, viewer_id=profile.user_id, viewer_is_member=_is_member(profile), is_staff=_is_staff(profile),
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
        db, research_id, viewer_id=profile.user_id, viewer_is_member=_is_member(profile), is_staff=_is_staff(profile),
    )
    version, is_current = await service.get_version(db, research_id, version_number)
    return {"version_number": version.version_number, "snapshot": version.snapshot,
            "change_note": version.change_note, "edited_by": str(version.edited_by),
            "created_at": version.created_at, "is_current": is_current}


# ---------------------------------------------------------------------------
# 7.5 Access classification — ADMIN/SUPER_ADMIN only, AD-19
# ---------------------------------------------------------------------------

@router.patch("/{research_id}/access-tier", response_model=AccessTierUpdateResponse,
              dependencies=[Depends(require_csrf)])
async def set_access_tier(
    research_id: uuid.UUID,
    body: AccessTierUpdateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("ADMIN", "SUPER_ADMIN")),
):
    research = await service.set_access_tier(
        db, research_id=research_id, actor_id=profile.user_id, access_tier=body.access_tier,
    )
    return AccessTierUpdateResponse(id=str(research.id), access_tier=research.access_tier)
