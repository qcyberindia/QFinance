"""Company routes — API Specification V1 §6. List/detail are public (company
pages are static metadata, viewable by FREE members per Section 10 of the
product doc); create/update/merge are ADMIN/SUPER_ADMIN only.
WRITTEN, NOT EXECUTED."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_csrf, require_role
from app.modules.companies import service
from app.modules.companies.schemas import (
    CompanyCreateRequest, CompanyListResponse, CompanyMergeRequest,
    CompanyResponse, CompanyUpdateRequest,
)
from app.modules.users.models import Profile

router = APIRouter(prefix="/companies", tags=["companies"])


async def _to_response(db: AsyncSession, company) -> CompanyResponse:
    counts = await service.get_content_counts(db, company.id)
    return CompanyResponse(
        id=str(company.id), name=company.name, exchange=company.exchange,
        sector=company.sector, industry=company.industry, website=company.website,
        description=company.description,
        is_merged_into=str(company.is_merged_into) if company.is_merged_into else None,
        created_at=company.created_at, **counts,
    )


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_companies(db, search=search, page=page, page_size=page_size)
    return CompanyListResponse(
        items=[await _to_response(db, c) for c in items], total=total, page=page, page_size=page_size,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    company = await service.get_company(db, company_id)
    return await _to_response(db, company)


@router.post(
    "", response_model=CompanyResponse, status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_company(
    body: CompanyCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("ADMIN", "SUPER_ADMIN")),
):
    company = await service.create_company(
        db, actor_id=profile.user_id, name=body.name, exchange=body.exchange,
        sector=body.sector, industry=body.industry, website=body.website, description=body.description,
    )
    return await _to_response(db, company)


@router.patch(
    "/{company_id}", response_model=CompanyResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("ADMIN", "SUPER_ADMIN")),
):
    company = await service.update_company(db, actor_id=profile.user_id, company_id=company_id, **body.model_dump())
    return await _to_response(db, company)


@router.post(
    "/{company_id}/merge", response_model=CompanyResponse,
    dependencies=[Depends(require_csrf)],
)
async def merge_company(
    company_id: uuid.UUID,
    body: CompanyMergeRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("ADMIN", "SUPER_ADMIN")),
):
    company = await service.merge_company(
        db, actor_id=profile.user_id, source_id=company_id, target_id=uuid.UUID(body.target_company_id),
    )
    return await _to_response(db, company)
