"""Company business logic — API Specification V1 §6 (CO-001-004).
OD-23: exchange-listed companies only; validation rejects anything else here,
not just at the DB CHECK constraint (defense in depth, Architecture Principle 2).
Dedup/merge (CO-004) archives via `is_merged_into`, never deletes (Section 15.1
of the product doc — "no hard deletes").
WRITTEN, NOT EXECUTED — no real database has been reached in this session.
"""
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.errors import NotFound, QFinanceAPIError
from app.modules.companies.models import Company
from app.modules.companies.schemas import VALID_EXCHANGES


async def create_company(db: AsyncSession, *, actor_id: uuid.UUID, name: str, exchange: str,
                          sector: str | None, industry: str | None, website: str | None,
                          description: str | None) -> Company:
    if exchange not in VALID_EXCHANGES:
        # OD-23 — explicit application-level rejection, not just relying on the DB CHECK,
        # so the caller gets a clear message rather than a raw constraint-violation error.
        raise QFinanceAPIError(
            "UNLISTED_COMPANY_REJECTED",
            "Only exchange-listed companies (NSE/BSE/recognized exchange) can be added.",
            400,
        )
    company = Company(
        id=uuid.uuid4(), name=name, exchange=exchange, sector=sector,
        industry=industry, website=website, description=description,
    )
    db.add(company)
    await db.flush()
    await write_audit_log(
        db, actor_id=actor_id, action_type="company.create",
        target_entity_type="company", target_entity_id=company.id,
        after_state={"name": name, "exchange": exchange},
    )
    await db.commit()
    return company


async def get_company(db: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await db.get(Company, company_id)
    if company is None or company.deleted_at is not None:
        raise NotFound("Company not found.")
    return company


async def list_companies(db: AsyncSession, *, search: str | None, page: int, page_size: int) -> tuple[list[Company], int]:
    stmt = select(Company).where(Company.deleted_at.is_(None), Company.is_merged_into.is_(None))
    count_stmt = select(func.count()).select_from(Company).where(
        Company.deleted_at.is_(None), Company.is_merged_into.is_(None)
    )
    if search:
        # Uses the ix_companies_name_trgm GIN index defined in the migration (CO-002).
        stmt = stmt.where(Company.name.ilike(f"%{search}%"))
        count_stmt = count_stmt.where(Company.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Company.name).offset((page - 1) * page_size).limit(page_size)
    total = (await db.execute(count_stmt)).scalar_one()
    items = (await db.execute(stmt)).scalars().all()
    return list(items), total


async def update_company(db: AsyncSession, *, actor_id: uuid.UUID, company_id: uuid.UUID, **fields) -> Company:
    company = await get_company(db, company_id)
    before = {"name": company.name, "sector": company.sector, "industry": company.industry}
    for key, value in fields.items():
        if value is not None:
            setattr(company, key, value)
    await write_audit_log(
        db, actor_id=actor_id, action_type="company.update",
        target_entity_type="company", target_entity_id=company.id,
        before_state=before, after_state=fields,
    )
    await db.commit()
    return company


async def merge_company(db: AsyncSession, *, actor_id: uuid.UUID, source_id: uuid.UUID, target_id: uuid.UUID) -> Company:
    """CO-004 — archives `source` into `target`. Source is NOT deleted (is_merged_into
    set instead) so existing research/watchlist references remain valid, per the
    product doc's Section 10 ("duplicates are archived, not deleted")."""
    if source_id == target_id:
        raise QFinanceAPIError("INVALID_MERGE", "Cannot merge a company into itself.", 400)
    source = await get_company(db, source_id)
    target = await get_company(db, target_id)  # raises NotFound if target invalid
    source.is_merged_into = target.id
    await write_audit_log(
        db, actor_id=actor_id, action_type="company.merge",
        target_entity_type="company", target_entity_id=source.id,
        before_state={"is_merged_into": None}, after_state={"is_merged_into": str(target.id)},
    )
    await db.commit()
    return source


async def get_content_counts(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """Research/discussion counts shown on company pages and the Ledger Row
    component (Section 10 of the product doc). Raw SQL against the `research`/
    `posts` tables rather than importing the research/community modules, to
    avoid a companies -> research circular dependency (Architecture §4.4 —
    modules communicate via service interfaces, not direct cross-imports)."""
    research_count = (
        await db.execute(
            text("SELECT COUNT(*) FROM research WHERE company_id = :cid AND status = 'published' "
                 "AND moderation_status != 'removed'"),
            {"cid": str(company_id)},
        )
    ).scalar_one()
    discussion_count = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM posts p JOIN research r ON p.research_id = r.id "
                "WHERE r.company_id = :cid AND p.status = 'visible'"
            ),
            {"cid": str(company_id)},
        )
    ).scalar_one()
    return {"research_count": research_count, "discussion_count": discussion_count}
