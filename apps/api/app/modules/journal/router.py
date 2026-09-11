"""Journal routes — API Specification V2 §1. WRITTEN, NOT EXECUTED."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_csrf
from app.modules.auth.models import User
from app.modules.journal import service
from app.modules.journal.schemas import (
    JournalEntryCreateRequest, JournalEntryListResponse, JournalEntryPatchRequest, JournalEntryResponse,
)

router = APIRouter(prefix="/journal", tags=["journal"])


@router.post("", response_model=JournalEntryResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_entry(
    body: JournalEntryCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = await service.create_entry(
        db, user_id=user.id, content=body.content, entry_type=body.entry_type,
        company_id=uuid.UUID(body.company_id) if body.company_id else None,
    )
    return JournalEntryResponse.model_validate(entry)


@router.get("", response_model=JournalEntryListResponse)
async def list_entries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entries, total = await service.list_own_entries(db, user_id=user.id, page=page, page_size=page_size)
    return JournalEntryListResponse(
        items=[JournalEntryResponse.model_validate(e) for e in entries], page=page, page_size=page_size, total=total,
    )


@router.get("/{entry_id}", response_model=JournalEntryResponse)
async def get_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = await service.get_own_entry(db, entry_id=entry_id, user_id=user.id)
    return JournalEntryResponse.model_validate(entry)


@router.patch("/{entry_id}", response_model=JournalEntryResponse, dependencies=[Depends(require_csrf)])
async def patch_entry(
    entry_id: uuid.UUID,
    body: JournalEntryPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    patch = body.model_dump(exclude_unset=True)
    if "company_id" in patch and patch["company_id"] is not None:
        patch["company_id"] = uuid.UUID(patch["company_id"])
    entry = await service.patch_entry(db, entry_id=entry_id, user_id=user.id, patch=patch)
    return JournalEntryResponse.model_validate(entry)


@router.delete("/{entry_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.delete_entry(db, entry_id=entry_id, user_id=user.id)
