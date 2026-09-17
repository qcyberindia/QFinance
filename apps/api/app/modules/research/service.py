"""Research business logic — API Specification V1 §7 (RES/QRES/VER/SRC/AD-16-19).
WRITTEN, NOT EXECUTED — no real database has been reached in this session; only
the pure validation.py logic has actually been run (see work_memory.md).

FTS NOTE (Database Schema V1 §7/§8, Amendment Log row 1): the locked schema's
`ix_research_fts` index is defined as
`to_tsvector('english', coalesce(title,'') || ' ' || coalesce(business_model,''))`
— i.e. title + business_model, NOT summary and NOT a combined
title/company/tag expression. `ix_companies_name_fts` separately covers
company name. `research_tags` has no FTS index in any approved document.
This file follows those two indexes exactly rather than inventing a third,
and keeps tag matching as a direct ILIKE lookup on `research_tags`, matching
what's actually indexed. This is a known, pre-existing wording tension
between the DB Schema's concrete DDL and API Spec §7.4.2's prose description
of search scope ("title, company name, tags") — flagged in work_memory.md,
not silently resolved by changing either locked document here.
"""
import csv
import io
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.errors import Forbidden, NotFound, QFinanceAPIError
from app.modules.analytics.models import emit_event
from app.modules.research.models import (
    PLACEHOLDER_SUMMARY, PLACEHOLDER_TITLE, QRES_STAGE_FIELDS, Research, ResearchSource, ResearchTag, ResearchVersion,
)
from app.modules.research.validation import PublishCandidate, validate_publish_readiness

_PATCHABLE_CONTENT_FIELDS = (
    "title", "summary", *QRES_STAGE_FIELDS, "research_date",
    "conflict_disclosed", "conflict_detail", "position_disclosed", "position_detail",
)


# ---------------------------------------------------------------------------
# Create / read
# ---------------------------------------------------------------------------

async def create_research(db: AsyncSession, *, author_id: uuid.UUID, company_id: uuid.UUID,
                           research_type: str, industry: str | None, title: str | None,
                           summary: str | None) -> Research:
    research = Research(
        id=uuid.uuid4(), author_id=author_id, company_id=company_id,
        research_type=research_type, industry=industry,
        title=title or PLACEHOLDER_TITLE,
        summary=summary or PLACEHOLDER_SUMMARY,
        status="draft", current_version=0,
    )
    db.add(research)
    await db.flush()
    await emit_event(db, user_id=author_id, event_type="research_draft_created",
                      entity_type="research", entity_id=research.id)
    await db.commit()
    return research


async def get_research_or_404(db: AsyncSession, research_id: uuid.UUID) -> Research:
    research = await db.get(Research, research_id)
    if research is None or research.deleted_at is not None:
        raise NotFound("Research item not found.")
    return research


async def _load_sources(db: AsyncSession, research_id: uuid.UUID) -> list[ResearchSource]:
    return list((await db.execute(
        select(ResearchSource).where(ResearchSource.research_id == research_id)
    )).scalars().all())


async def _load_tags(db: AsyncSession, research_id: uuid.UUID) -> list[str]:
    rows = (await db.execute(select(ResearchTag.tag).where(ResearchTag.research_id == research_id))).scalars().all()
    return list(rows)


async def _load_author_and_company(db: AsyncSession, *, author_id: uuid.UUID, company_id: uuid.UUID) -> tuple[dict, dict]:
    """API Spec §7.4.1/§7.4.2 library/search response contract — nested `author`
    and `company` objects, not raw `author_id`/`company_id` strings. Raw SQL
    against `profiles`/`companies` rather than importing the users/companies
    ORM models directly, matching the same cross-module-avoidance pattern
    already used in companies/service.py's `get_content_counts` (Architecture
    §4.4 — modules communicate via service interfaces/queries, not direct
    cross-imports of another module's ORM models).

    SECURITY FIX (this pass): previously also selected/returned `profiles.name`
    (the real registration name) for `author` — the same real-identity leak
    already found and fixed in profile/service.py and community/service.py's
    `_load_author`, just not yet applied here. `/research/library` and
    `/research/search` are public-facing surfaces; `username` is the only
    public identity attached to a research item's author now."""
    author_row = (await db.execute(
        text("SELECT user_id, username FROM profiles WHERE user_id = :uid"),
        {"uid": str(author_id)},
    )).first()
    company_row = (await db.execute(
        text("SELECT id, name FROM companies WHERE id = :cid"),
        {"cid": str(company_id)},
    )).first()
    author = ({"id": str(author_row.user_id), "username": author_row.username}
              if author_row else {"id": str(author_id), "username": None})
    company = ({"id": str(company_row.id), "name": company_row.name}
               if company_row else {"id": str(company_id), "name": None})
    return author, company


def _is_visible_to(research: Research, *, viewer_id: uuid.UUID | None, is_staff: bool) -> bool:
    """§7.1.2 eligibility gate — BEFORE any access_tier/tier consideration.
    access_tier never bypasses this; it only affects what a FREE viewer sees
    once an item is otherwise eligible."""
    if is_staff:
        return True
    if research.author_id == viewer_id:
        return True
    return research.status == "published" and research.moderation_status == "active"


def serialize_for_viewer(research: Research, *, sources: list[ResearchSource], tags: list[str],
                          viewer_is_member: bool) -> dict:
    """§7.1.2/§7.4.1/§7.4.2 shared tier-gating rule, access_tier checked FIRST:
    (1) access_tier == 'free_example' -> full representation regardless of tier (MEM-004)
    (2) access_tier == 'core' -> existing LIB-003 rule: MEMBER sees full, FREE sees preview.
    Author/staff callers always get the full representation (checked by the caller
    before calling this — see router.py — so this function only implements the
    *tier* half of visibility, not the ownership/staff half)."""
    if research.access_tier == "free_example" or viewer_is_member:
        return {
            "id": str(research.id), "author_id": str(research.author_id), "company_id": str(research.company_id),
            "research_type": research.research_type, "industry": research.industry,
            "status": research.status, "moderation_status": research.moderation_status,
            "access_tier": research.access_tier, "title": research.title, "summary": research.summary,
            "current_version": research.current_version,
            **{f: getattr(research, f) for f in QRES_STAGE_FIELDS},
            "disclosure": {
                "conflict_disclosed": research.conflict_disclosed, "conflict_detail": research.conflict_detail,
                "position_disclosed": research.position_disclosed, "position_detail": research.position_detail,
                "research_date": research.research_date,
            },
            "sources": [{"id": str(s.id), "label": s.label, "reference": s.reference,
                         "supports_claim": s.supports_claim} for s in sources],
            "tags": tags, "published_at": research.published_at,
            "created_at": research.created_at, "updated_at": research.updated_at,
        }
    # 'core' access_tier + FREE viewer -> paywalled preview (LIB-003)
    return {
        "preview": True, "id": str(research.id), "title": research.title,
        "author_id": str(research.author_id), "summary": research.summary, "access_tier": "core",
    }


async def get_research_view(db: AsyncSession, research_id: uuid.UUID, *, viewer_id: uuid.UUID | None,
                             viewer_is_member: bool, is_staff: bool) -> dict:
    research = await get_research_or_404(db, research_id)
    if not _is_visible_to(research, viewer_id=viewer_id, is_staff=is_staff):
        raise NotFound("Research item not found.")  # §0.5 — MVP doesn't distinguish 404 vs 403 here
    sources = await _load_sources(db, research_id)
    tags = await _load_tags(db, research_id)
    # Author/staff always get the full representation, independent of access_tier.
    if is_staff or research.author_id == viewer_id:
        return serialize_for_viewer(research, sources=sources, tags=tags, viewer_is_member=True)
    return serialize_for_viewer(research, sources=sources, tags=tags, viewer_is_member=viewer_is_member)


# ---------------------------------------------------------------------------
# Edit (draft and published)
# ---------------------------------------------------------------------------

def _require_author(research: Research, actor_id: uuid.UUID) -> None:
    if research.author_id != actor_id:
        raise Forbidden("Only the author may modify this research item.")


async def patch_draft(db: AsyncSession, *, research_id: uuid.UUID, actor_id: uuid.UUID, patch: dict) -> Research:
    """§7.1.3 — pre-publish edits. Emits research_draft_updated once, plus
    research_section_completed per field transitioning empty->non-empty
    (Architecture §21.1's exact trigger)."""
    research = await get_research_or_404(db, research_id)
    _require_author(research, actor_id)
    if research.status != "draft":
        raise QFinanceAPIError("NOT_A_DRAFT", "Use the published-edit flow for a published item.", 400)

    newly_completed: list[str] = []
    for field, value in patch.items():
        if field not in _PATCHABLE_CONTENT_FIELDS or value is None:
            continue
        before = getattr(research, field)
        was_empty = before is None or (isinstance(before, str) and before.strip() == "")
        setattr(research, field, value)
        is_now_filled = value is not None and not (isinstance(value, str) and value.strip() == "")
        if field in QRES_STAGE_FIELDS and was_empty and is_now_filled:
            newly_completed.append(field)

    await emit_event(db, user_id=actor_id, event_type="research_draft_updated",
                      entity_type="research", entity_id=research.id)
    for field in newly_completed:
        await emit_event(db, user_id=actor_id, event_type="research_section_completed",
                          entity_type="research", entity_id=research.id, metadata={"field": field})
    await db.commit()
    return research


def _snapshot(research: Research, sources: list[ResearchSource], tags: list[str]) -> dict:
    snap = {f: getattr(research, f) for f in QRES_STAGE_FIELDS}
    snap.update({
        "title": research.title, "summary": research.summary,
        "conflict_disclosed": research.conflict_disclosed, "conflict_detail": research.conflict_detail,
        "position_disclosed": research.position_disclosed, "position_detail": research.position_detail,
        "research_date": research.research_date.isoformat() if research.research_date else None,
        "sources": [{"label": s.label, "reference": s.reference, "supports_claim": s.supports_claim} for s in sources],
        "tags": tags,
    })
    return snap


async def patch_published(db: AsyncSession, *, research_id: uuid.UUID, actor_id: uuid.UUID, patch: dict) -> Research:
    """§7.1.4/AD-17 — editing an already-published item. Runs the identical
    full publish-validation gate as §7.3.1 against the *proposed* post-edit
    state before writing anything. On failure: nothing is written at all."""
    research = await get_research_or_404(db, research_id)
    _require_author(research, actor_id)
    if research.status != "published":
        raise QFinanceAPIError("NOT_PUBLISHED", "This research item is not published.", 400)

    change_note = patch.get("change_note")
    if not change_note or not change_note.strip():
        raise QFinanceAPIError("CHANGE_NOTE_REQUIRED", "A change note is required to edit published research.", 422)

    # Build the proposed post-edit state WITHOUT mutating the ORM object yet,
    # so a validation failure leaves the live row completely untouched (AD-17's
    # explicit "no partial write on failure" requirement).
    proposed = {f: getattr(research, f) for f in _PATCHABLE_CONTENT_FIELDS}
    for field, value in patch.items():
        if field in _PATCHABLE_CONTENT_FIELDS and value is not None:
            proposed[field] = value

    sources = await _load_sources(db, research_id)
    errors = validate_publish_readiness(PublishCandidate(
        title=proposed["title"], summary=proposed["summary"], bear_case=proposed["bear_case"],
        conflict_disclosed=proposed["conflict_disclosed"], position_disclosed=proposed["position_disclosed"],
        research_date=proposed["research_date"], source_count=len(sources),
    ))
    if errors:
        raise QFinanceAPIError("RESEARCH_PUBLISH_MISSING_FIELDS",
                                "This research item cannot be re-published yet.", 422, fields=errors)

    # Validation passed — now actually apply the changes.
    for field, value in proposed.items():
        setattr(research, field, value)
    research.current_version += 1
    tags = await _load_tags(db, research_id)
    db.add(ResearchVersion(
        id=uuid.uuid4(), research_id=research.id, version_number=research.current_version,
        snapshot=_snapshot(research, sources, tags), change_note=change_note, edited_by=actor_id,
    ))
    await db.commit()
    return research


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

async def add_source(db: AsyncSession, *, research_id: uuid.UUID, actor_id: uuid.UUID,
                      label: str, reference: str, supports_claim: str | None) -> ResearchSource:
    research = await get_research_or_404(db, research_id)
    _require_author(research, actor_id)
    if not label or not label.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Source label cannot be empty.", 400, fields={"label": "required"})
    source = ResearchSource(id=uuid.uuid4(), research_id=research_id, label=label,
                             reference=reference, supports_claim=supports_claim)
    db.add(source)
    await emit_event(db, user_id=actor_id, event_type="research_source_added",
                      entity_type="research", entity_id=research_id)
    await db.commit()
    return source


async def delete_source(db: AsyncSession, *, research_id: uuid.UUID, source_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    research = await get_research_or_404(db, research_id)
    _require_author(research, actor_id)
    if research.status != "draft":
        raise QFinanceAPIError(
            "PUBLISHED_SOURCE_IMMUTABLE",
            "Sources on a published item are changed via re-publish with a new source list, not deleted directly.",
            400,
        )
    source = await db.get(ResearchSource, source_id)
    if source is None or source.research_id != research_id:
        raise NotFound("Source not found.")
    await db.delete(source)
    await db.commit()


async def list_sources(db: AsyncSession, research_id: uuid.UUID) -> list[ResearchSource]:
    await get_research_or_404(db, research_id)
    return await _load_sources(db, research_id)


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

async def publish(db: AsyncSession, *, research_id: uuid.UUID, actor_id: uuid.UUID,
                   change_note: str | None) -> Research:
    research = await get_research_or_404(db, research_id)
    _require_author(research, actor_id)

    is_first_publish = research.current_version == 0
    if not is_first_publish and (not change_note or not change_note.strip()):
        raise QFinanceAPIError("CHANGE_NOTE_REQUIRED", "A change note is required to re-publish.", 422)
    effective_note = change_note.strip() if change_note and change_note.strip() else "Initial publication"

    sources = await _load_sources(db, research_id)
    errors = validate_publish_readiness(PublishCandidate(
        title=research.title, summary=research.summary, bear_case=research.bear_case,
        conflict_disclosed=research.conflict_disclosed, position_disclosed=research.position_disclosed,
        research_date=research.research_date, source_count=len(sources),
    ))
    if errors:
        raise QFinanceAPIError("RESEARCH_PUBLISH_MISSING_FIELDS",
                                "This research item cannot be published yet.", 422, fields=errors)

    research.status = "published"
    if is_first_publish:
        research.published_at = datetime.now(timezone.utc)
    research.current_version += 1
    tags = await _load_tags(db, research_id)
    db.add(ResearchVersion(
        id=uuid.uuid4(), research_id=research.id, version_number=research.current_version,
        snapshot=_snapshot(research, sources, tags), change_note=effective_note, edited_by=actor_id,
    ))
    await emit_event(db, user_id=actor_id, event_type="research_published",
                      entity_type="research", entity_id=research.id)
    await db.commit()
    return research


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

async def list_versions(db: AsyncSession, research_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[ResearchVersion], int]:
    await get_research_or_404(db, research_id)
    count = (await db.execute(
        select(func.count()).select_from(ResearchVersion).where(ResearchVersion.research_id == research_id)
    )).scalar_one()
    rows = (await db.execute(
        select(ResearchVersion).where(ResearchVersion.research_id == research_id)
        .order_by(ResearchVersion.version_number.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(rows), count


async def get_version(db: AsyncSession, research_id: uuid.UUID, version_number: int) -> tuple[ResearchVersion, bool]:
    research = await get_research_or_404(db, research_id)
    version = (await db.execute(
        select(ResearchVersion).where(
            ResearchVersion.research_id == research_id, ResearchVersion.version_number == version_number
        )
    )).scalar_one_or_none()
    if version is None:
        raise NotFound("Version not found.")
    return version, version_number == research.current_version


# ---------------------------------------------------------------------------
# Library / search
# ---------------------------------------------------------------------------

async def _library_item(db: AsyncSession, r: Research) -> dict:
    """Full (non-preview) library/search item shape — API Spec §7.4.1/§7.4.2:
    nested `author`/`company` objects, not raw id strings (fix for the
    contract gap found during Research verification, 2026-09-01)."""
    sources = await _load_sources(db, r.id)
    tags = await _load_tags(db, r.id)
    author, company = await _load_author_and_company(db, author_id=r.author_id, company_id=r.company_id)
    return {
        "id": str(r.id), "title": r.title, "summary": r.summary, "author": author, "company": company,
        "industry": r.industry, "created_at": r.created_at, "updated_at": r.updated_at,
        "status_label": r.status, "moderation_status": r.moderation_status, "tags": tags,
        "source_count": len(sources), "current_version": r.current_version,
        "access_tier": r.access_tier, "preview": False,
    }


def _preview_item(r: Research, author: dict) -> dict:
    return {
        "preview": True, "id": str(r.id), "title": r.title,
        "author": author, "summary": r.summary, "access_tier": "core",
    }


async def list_library(db: AsyncSession, *, company_id: uuid.UUID | None, industry: str | None,
                        page: int, page_size: int, viewer_is_member: bool,
                        include_moderated: bool = False, is_staff: bool = False) -> tuple[list[dict], int]:
    """LIB-001/002. `include_moderated` (API Spec §12 item 3, end of §10) lets
    MODERATOR/ADMIN/SUPER_ADMIN see `restricted`/`removed` items too — gated
    by the caller-supplied `is_staff` flag (derived server-side from
    `profile.role_grants` in router.py, never trusted from the query string
    itself), so a non-staff caller passing `?include_moderated=true` has no
    effect: the default `status='published' AND moderation_status='active'`
    filter still applies unless `is_staff` is True."""
    apply_moderation_filter = not (include_moderated and is_staff)

    stmt = select(Research).where(Research.status == "published")
    count_stmt = select(func.count()).select_from(Research).where(Research.status == "published")
    if apply_moderation_filter:
        stmt = stmt.where(Research.moderation_status == "active")
        count_stmt = count_stmt.where(Research.moderation_status == "active")
    if company_id:
        stmt = stmt.where(Research.company_id == company_id)
        count_stmt = count_stmt.where(Research.company_id == company_id)
    if industry:
        stmt = stmt.where(Research.industry == industry)
        count_stmt = count_stmt.where(Research.industry == industry)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Research.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for r in rows:
        if r.access_tier == "free_example" or viewer_is_member or is_staff:
            items.append(await _library_item(db, r))
        else:
            author, _ = await _load_author_and_company(db, author_id=r.author_id, company_id=r.company_id)
            items.append(_preview_item(r, author))
    return items, total


def build_research_search_sql(select_clause: str, *, include_moderated: bool = False) -> str:
    """Pure query-construction logic, factored out so it can be unit-tested
    without a real PostgreSQL connection (tsvector/GIN syntax and predicate
    structure can be verified statically; actual execution against real data
    cannot be, in this environment — see work_memory.md).

    Uses the two indexes Database Schema V1 actually defines (§7
    `ix_companies_name_fts`, §8 `ix_research_fts` on title+business_model) via
    `plainto_tsquery`, OR'd with a direct ILIKE on `research_tags.tag` (no FTS
    index exists for tags in any locked document, so tag matching is
    intentionally not tsvector-based) — replacing the prior all-ILIKE
    implementation, which ignored the locked FTS mechanism entirely.

    `include_moderated=True` drops the `moderation_status='active'` filter
    (API Spec §12 item 3 / end of §10) — callers must only pass True after
    verifying the caller is MODERATOR/ADMIN/SUPER_ADMIN server-side; this
    function itself performs no authorization, by design, so it stays pure
    and testable."""
    moderation_filter = "" if include_moderated else " AND r.moderation_status = 'active'"
    return (
        f"{select_clause} FROM research r "
        "LEFT JOIN research_tags rt ON rt.research_id = r.id "
        "LEFT JOIN companies c ON c.id = r.company_id "
        "WHERE r.status = 'published'" + moderation_filter + " "
        "AND ("
        "  to_tsvector('english', coalesce(r.title, '') || ' ' || coalesce(r.business_model, ''))"
        "    @@ plainto_tsquery('english', :q)"
        "  OR to_tsvector('english', c.name) @@ plainto_tsquery('english', :q)"
        "  OR rt.tag ILIKE :like_q"
        ")"
    )


async def search_research(db: AsyncSession, *, query: str, page: int, page_size: int,
                           viewer_is_member: bool, include_moderated: bool = False,
                           is_staff: bool = False) -> tuple[list[dict], int]:
    """LIB-004/SEARCH-001-003. Uses the exact FTS indexes Database Schema V1
    §7/§8 defines (see build_research_search_sql). `include_moderated` mirrors
    list_library's staff-only override (API Spec §12 item 3 applies
    identically to search per §7.4.2's "tier-gating applied identically to
    library browsing" note) — SEARCH-002 requires search not to be *more*
    restrictive than library browsing, and this keeps the moderation-
    visibility rule consistent between the two. As in list_library, the
    effective flag is `include_moderated and is_staff` — `is_staff` is
    derived server-side by the router from `profile.role_grants`, never from
    the query string, so a non-staff caller passing the flag has no effect."""
    like_q = f"%{query}%"
    effective_include_moderated = include_moderated and is_staff

    count_row = (await db.execute(
        text(build_research_search_sql("SELECT COUNT(DISTINCT r.id)", include_moderated=effective_include_moderated)),
        {"q": query, "like_q": like_q},
    )).scalar_one()
    id_rows = (await db.execute(
        text(
            build_research_search_sql("SELECT DISTINCT r.id, r.updated_at", include_moderated=effective_include_moderated)
            + " ORDER BY r.updated_at DESC OFFSET :off LIMIT :lim"
        ),
        {"q": query, "like_q": like_q, "off": (page - 1) * page_size, "lim": page_size},
    )).all()
    items = []
    for row in id_rows:
        r = await db.get(Research, row.id)
        if r.access_tier == "free_example" or viewer_is_member or is_staff:
            items.append(await _library_item(db, r))
        else:
            author, _ = await _load_author_and_company(db, author_id=r.author_id, company_id=r.company_id)
            items.append(_preview_item(r, author))
    return items, count_row


async def export_csv(db: AsyncSession, author_id: uuid.UUID) -> str:
    """AD-11 — self-only, streamed synchronously. Returns CSV text; the router
    wraps this in a StreamingResponse."""
    rows = (await db.execute(
        select(Research).where(Research.author_id == author_id, Research.deleted_at.is_(None))
        .order_by(Research.created_at.desc())
    )).scalars().all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["title", "company_id", "status", "created_at", "updated_at", "tags", "current_version"])
    for r in rows:
        tags = await _load_tags(db, r.id)
        writer.writerow([r.title, str(r.company_id), r.status, r.created_at.isoformat(),
                          r.updated_at.isoformat(), ";".join(tags), r.current_version])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Moderation status (used by moderation/service.py's take_action, API Spec
# §5.3) — BUG FIX, this verification pass: moderation/service.py already called
# `research_service.apply_moderation_status(...)`, but no such function existed
# here, which would have raised AttributeError the first time a moderator
# tried to restrict/remove/reinstate a research item. Added now, matching the
# exact non-committing-helper contract community/service.py's
# apply_moderation_status_to_post/_comment already establish (validated
# new_status, fetch target, record previous state, set new state, db.flush()
# only — caller controls the commit boundary so this participates correctly
# in take_action's single atomic transaction, Architecture §10.1).
#
# SECOND BUG, caught during the follow-up verification pass: this function and
# VALID_MODERATION_STATUSES were accidentally defined TWICE in this file (the
# duplicate sat right above VALID_ACCESS_TIERS, near set_access_tier). Python
# doesn't error on this — the second definition silently wins — but it's dead,
# confusing duplication. Removed; this is now the single definition.
# ---------------------------------------------------------------------------

VALID_MODERATION_STATUSES = ("active", "restricted", "removed")


async def apply_moderation_status(db: AsyncSession, *, research_id: uuid.UUID, new_status: str) -> str:
    """Used by moderation/service.py's take_action (API Spec §5.3) — same
    non-committing contract as community/service.py's apply_moderation_status_to_*
    functions (see that module's docstring for the full rationale). Note the
    different vocabulary from posts/comments: research's moderation dimension
    uses 'active' (not 'visible') as its normal state, per Database Schema V1
    §8 / Architecture §10.1's research row."""
    if new_status not in VALID_MODERATION_STATUSES:
        raise QFinanceAPIError(
            "INVALID_MODERATION_STATUS", f"moderation_status must be one of {VALID_MODERATION_STATUSES}.", 400,
        )
    research = await get_research_or_404(db, research_id)
    previous_state = research.moderation_status
    research.moderation_status = new_status
    await db.flush()
    return previous_state


# ---------------------------------------------------------------------------
# Access tier (§7.5.1, AD-19, Founder Decision #2)
# ---------------------------------------------------------------------------

VALID_ACCESS_TIERS = ("core", "free_example")


async def set_access_tier(db: AsyncSession, *, research_id: uuid.UUID, actor_id: uuid.UUID,
                           access_tier: str) -> Research:
    if access_tier not in VALID_ACCESS_TIERS:
        raise QFinanceAPIError("INVALID_ACCESS_TIER", "access_tier must be 'core' or 'free_example'.", 400)
    research = await get_research_or_404(db, research_id)
    before = research.access_tier
    research.access_tier = access_tier
    await write_audit_log(
        db, actor_id=actor_id, action_type="research.access_tier_changed",
        target_entity_type="research", target_entity_id=research.id,
        before_state={"access_tier": before}, after_state={"access_tier": access_tier},
    )
    await db.commit()
    return research


# ---------------------------------------------------------------------------
# My Research listing + publish-to-community bridge (API Spec V2 §2, Architecture V2 §5)
# ---------------------------------------------------------------------------

async def list_my_research(db: AsyncSession, *, author_id: uuid.UUID, page: int, page_size: int) -> tuple[list[dict], int]:
    """API Spec V2 §2 — the member's OWN drafts AND published items, unlike
    §7.4's public library (published-only, all authors). Genuinely new: no
    prior V1 endpoint returned this shape at all (only CSV export existed for
    'my own research', and only in export form, not JSON)  — confirmed by
    inspection before writing this, not assumed."""
    base_filter = (Research.author_id == author_id, Research.deleted_at.is_(None))
    total = (await db.execute(select(func.count()).select_from(Research).where(*base_filter))).scalar_one()
    rows = (await db.execute(
        select(Research).where(*base_filter)
        .order_by(Research.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    items = []
    for r in rows:
        _, company = await _load_author_and_company(db, author_id=r.author_id, company_id=r.company_id)
        items.append({
            "id": str(r.id), "title": r.title, "summary": r.summary, "status": r.status, "company": company,
            "research_type": r.research_type, "current_version": r.current_version,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "created_at": r.created_at, "updated_at": r.updated_at,
        })
    return items, total


async def publish_to_community(db: AsyncSession, *, research_id: uuid.UUID, actor_id: uuid.UUID,
                                summary: str) -> dict:
    """API Spec V2 §2 `POST /research/{id}/publish-to-community`, Architecture V2
    §5. Requires the research item to already be `status='published'` — this
    does NOT publish a draft itself (that's the existing `publish()` function,
    unchanged, called separately first); this only creates the Community
    bridge post for an already-published item. Reuses
    `community.service.create_research_discussion_post` (which already
    anticipated this exact caller — see that function's own docstring) with
    `post_type='thesis'`, rather than duplicating post-creation logic here,
    per Architecture V2 §5's explicit 'reuses posts.research_id... rather than
    adding a new column' design.

    Does NOT record a contribution here directly — contributions/service.py's
    `record_thesis_published` is called from the router after this succeeds,
    keeping this function focused on the bridge itself and the contribution
    module free of a reverse import back into research."""
    research = await get_research_or_404(db, research_id)
    _require_author(research, actor_id)
    if research.status != "published":
        raise QFinanceAPIError(
            "RESEARCH_NOT_PUBLISHED",
            "Publish this research item first before sharing it to Community.", 400,
        )
    if not summary or not summary.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "A summary is required.", 400, fields={"summary": "required"})

    # Imported here (not at module top) to avoid a circular import at module
    # load time: community/service.py imports nothing from research/service.py,
    # but research/router.py's import graph loads before community's router in
    # api/v1/router.py, and a top-level `from app.modules.community import
    # service` here would force community's module (and its own import of
    # `app.modules.users.service`) to fully resolve during research/service.py's
    # own import — deferred to call-time instead, matching the same deferred-
    # import pattern community/router.py itself already uses for research.
    from app.modules.community import service as community_service

    post = await community_service.create_research_discussion_post(
        db, actor_id=actor_id, research_id=research_id, content=summary, post_type="thesis",
    )
    serialized = await community_service.serialize_post(db, post)
    return serialized
