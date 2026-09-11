"""Journal business logic — API Specification V2 §1 (J.1-J.5).
WRITTEN, NOT EXECUTED — not run against a real database in this session.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, NotFound, QFinanceAPIError
from app.modules.journal.models import VALID_ENTRY_TYPES, JournalEntry

_PATCHABLE_FIELDS = ("content", "entry_type", "company_id")


def _validate_entry_type(entry_type: str) -> None:
    if entry_type not in VALID_ENTRY_TYPES:
        raise QFinanceAPIError("INVALID_ENTRY_TYPE", f"entry_type must be one of {VALID_ENTRY_TYPES}.", 400)


def _validate_content(content: str) -> None:
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "content cannot be empty.", 400, fields={"content": "required"})
    if len(content) > 10000:
        raise QFinanceAPIError(
            "VALIDATION_ERROR", "content must be 10,000 characters or fewer.", 400, fields={"content": "too_long"},
        )


async def create_entry(db: AsyncSession, *, user_id: uuid.UUID, content: str, entry_type: str,
                        company_id: uuid.UUID | None) -> JournalEntry:
    _validate_content(content)
    _validate_entry_type(entry_type)
    entry = JournalEntry(
        id=uuid.uuid4(), user_id=user_id, company_id=company_id, entry_type=entry_type, content=content,
    )
    db.add(entry)
    await db.commit()
    return entry


async def get_entry_or_404(db: AsyncSession, entry_id: uuid.UUID) -> JournalEntry:
    entry = await db.get(JournalEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise NotFound("Journal entry not found.")
    return entry


def _require_owner(entry: JournalEntry, user_id: uuid.UUID) -> None:
    """Per API Spec V2 J.3: 404, never 403, on a non-owner access attempt —
    matching V1's §7.1.2 precedent of not revealing existence of another
    user's private content via a different status code."""
    if entry.user_id != user_id:
        raise NotFound("Journal entry not found.")


async def get_own_entry(db: AsyncSession, *, entry_id: uuid.UUID, user_id: uuid.UUID) -> JournalEntry:
    entry = await get_entry_or_404(db, entry_id)
    _require_owner(entry, user_id)
    return entry


async def list_own_entries(db: AsyncSession, *, user_id: uuid.UUID, page: int, page_size: int) -> tuple[list[JournalEntry], int]:
    base_filter = (JournalEntry.user_id == user_id, JournalEntry.deleted_at.is_(None))
    total = (await db.execute(select(func.count()).select_from(JournalEntry).where(*base_filter))).scalar_one()
    rows = (await db.execute(
        select(JournalEntry).where(*base_filter)
        .order_by(JournalEntry.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(rows), total


async def patch_entry(db: AsyncSession, *, entry_id: uuid.UUID, user_id: uuid.UUID, patch: dict) -> JournalEntry:
    entry = await get_own_entry(db, entry_id=entry_id, user_id=user_id)
    if "content" in patch and patch["content"] is not None:
        _validate_content(patch["content"])
    if "entry_type" in patch and patch["entry_type"] is not None:
        _validate_entry_type(patch["entry_type"])
    for field in _PATCHABLE_FIELDS:
        if field in patch and patch[field] is not None:
            setattr(entry, field, patch[field])
    await db.commit()
    return entry


async def delete_entry(db: AsyncSession, *, entry_id: uuid.UUID, user_id: uuid.UUID) -> None:
    entry = await get_own_entry(db, entry_id=entry_id, user_id=user_id)
    from datetime import datetime
    entry.deleted_at = datetime.now().replace(microsecond=0)
    await db.commit()
