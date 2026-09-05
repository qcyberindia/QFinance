"""Integration-level tests for the research module — ownership, RBAC,
versioning, publish/republish gates, sources, access_tier, and the audit/event
side effects that go with each.

STATUS: WRITTEN. NOT EXECUTABLE IN CURRENT ENVIRONMENT — these require a real
PostgreSQL instance (for `AsyncSession`/Alembic-migrated tables) and a real
Redis instance (for session cookies via the auth dependency chain), neither of
which is reachable from this session (see work_memory.md §30). This file has
NOT been run, and its assertions have NOT been confirmed correct beyond manual
review — do not treat "written" as "passing." A future session with genuine
database/Redis access must actually run this (`pytest apps/api/tests/`) before
any of it can be marked EXECUTED.

Structure: an `httpx.AsyncClient` against the real FastAPI app (`app.main.app`)
via ASGI transport, a session-scoped fixture creating/tearing-down a test
database, and a `register_and_login` helper that exercises the real auth flow
rather than faking a session, so RBAC/CSRF are tested end-to-end, not mocked
around.
"""
import pytest


# NOTE: fixtures below are declared but intentionally not implemented with a
# real engine/session — wiring them to an actual test database is exactly the
# "not executable in current environment" gap. A future session must supply:
#   - a `db_session` fixture (test-database-backed AsyncSession, rollback per test)
#   - a `client` fixture (httpx.AsyncClient(app=app, base_url="http://test"))
#   - a `member_a`, `member_b`, `admin_user` fixture set (registered + logged in,
#     with member_a/member_b holding MEMBER, admin_user holding ADMIN)
# without which every test below can only be collected, not run.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_create_research_as_member(client, member_a):
    resp = await client.post("/api/v1/research", json={
        "company_id": "00000000-0000-0000-0000-000000000001",
        "research_type": "deep_dive",
    }, headers=member_a.csrf_headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "draft"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_free_member_cannot_create_research(client, free_member):
    resp = await client.post("/api/v1/research", json={
        "company_id": "00000000-0000-0000-0000-000000000001",
        "research_type": "deep_dive",
    }, headers=free_member.csrf_headers)
    assert resp.status_code == 403


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_author_can_retrieve_own_draft(client, member_a, draft_research):
    resp = await client.get(f"/api/v1/research/{draft_research.id}", headers=member_a.auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_non_author_cannot_view_unpublished_draft(client, member_b, draft_research):
    """Ownership enforcement — a draft is only visible to its author (or staff),
    never to another ordinary member, matching §7.1.2's eligibility gate."""
    resp = await client.get(f"/api/v1/research/{draft_research.id}", headers=member_b.auth_headers)
    assert resp.status_code == 404  # MVP does not distinguish 404-vs-403 here (API Spec §0.5)


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_edit_draft_updates_field_and_emits_events(client, member_a, draft_research, db_session):
    resp = await client.patch(f"/api/v1/research/{draft_research.id}", json={
        "bear_case": "Semiconductor dependency risk.",
    }, headers=member_a.csrf_headers)
    assert resp.status_code == 200
    # Assert an `events` row with event_type='research_section_completed', field='bear_case' exists,
    # and a `research_draft_updated` row exists, both for this research_id.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_add_source_requires_author(client, member_a, member_b, draft_research):
    resp = await client.post(f"/api/v1/research/{draft_research.id}/sources", json={
        "label": "Company Q3 filing", "reference": "https://example.com/filing.pdf",
    }, headers=member_b.csrf_headers)  # member_b is NOT the author
    assert resp.status_code == 403


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_add_source_with_claim_by_author_succeeds(client, member_a, draft_research):
    resp = await client.post(f"/api/v1/research/{draft_research.id}/sources", json={
        "label": "Company Q3 filing", "reference": "https://example.com/filing.pdf",
        "supports_claim": "Revenue growth figure",
    }, headers=member_a.csrf_headers)
    assert resp.status_code == 201


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_publish_rejected_when_missing_required_fields(client, member_a, draft_research):
    """draft_research fixture deliberately has no sources, no bear_case, no
    disclosure answers, no research_date — publish must fail with the full
    set of missing fields named at once."""
    resp = await client.post(f"/api/v1/research/{draft_research.id}/publish", json={},
                              headers=member_a.csrf_headers)
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "RESEARCH_PUBLISH_MISSING_FIELDS"
    assert "bear_case" in body["fields"]
    assert "sources" in body["fields"]
    assert "conflict_disclosed" in body["fields"]
    assert "position_disclosed" in body["fields"]
    assert "research_date" in body["fields"]


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_publish_succeeds_when_complete_and_creates_version_1(client, member_a, complete_draft_research, db_session):
    resp = await client.post(f"/api/v1/research/{complete_draft_research.id}/publish", json={},
                              headers=member_a.csrf_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "published"
    assert body["current_version"] == 1
    # Assert exactly one research_versions row exists with version_number=1,
    # change_note="Initial publication", and a `research_published` events row exists.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_republish_without_change_note_rejected(client, member_a, published_research):
    resp = await client.post(f"/api/v1/research/{published_research.id}/publish", json={},
                              headers=member_a.csrf_headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CHANGE_NOTE_REQUIRED"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_published_edit_blanking_bear_case_rejected_and_leaves_row_untouched(
    client, member_a, published_research, db_session,
):
    """AD-17 — the core regression test for the gap that decision fixed:
    blanking a required field on a live published item via PATCH must fail
    validation, and must leave the currently-published row COMPLETELY
    unchanged (no partial write, no version increment, no snapshot row)."""
    before = await db_session.get(type(published_research), published_research.id)
    before_bear_case = before.bear_case
    before_version = before.current_version

    resp = await client.patch(f"/api/v1/research/{published_research.id}", json={
        "bear_case": "", "change_note": "Trying to blank the bear case",
    }, headers=member_a.csrf_headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RESEARCH_PUBLISH_MISSING_FIELDS"

    after = await db_session.get(type(published_research), published_research.id)
    assert after.bear_case == before_bear_case  # untouched
    assert after.current_version == before_version  # no increment
    # Assert no new research_versions row was inserted.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_published_edit_with_valid_change_creates_new_version(client, member_a, published_research):
    resp = await client.patch(f"/api/v1/research/{published_research.id}", json={
        "valuation_range": "Updated range given Q3 print.",
        "change_note": "Updated valuation after Q3 results.",
    }, headers=member_a.csrf_headers)
    assert resp.status_code == 200
    assert resp.json()["current_version"] == published_research.current_version + 1


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_free_member_sees_preview_for_core_tier_published_research(client, free_member, published_research):
    """LIB-003 — a 'core' access_tier item shows the paywalled preview shape
    to a FREE caller, not the full field set."""
    resp = await client.get(f"/api/v1/research/{published_research.id}", headers=free_member.auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preview") is True
    assert "bear_case" not in body


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_free_member_sees_full_content_for_free_example_tier(client, free_member, free_example_research):
    """MEM-004 — a 'free_example' item bypasses the paywall entirely for a
    FREE caller, per AD-18/Founder Decision #1."""
    resp = await client.get(f"/api/v1/research/{free_example_research.id}", headers=free_member.auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preview") is not True
    assert "bear_case" in body


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_only_admin_can_set_access_tier(client, member_a, moderator_user, admin_user, published_research):
    """AD-19/Founder Decision #2 — author, MODERATOR, and REVIEWER are all
    explicitly excluded; only ADMIN/SUPER_ADMIN may call this."""
    resp = await client.patch(f"/api/v1/research/{published_research.id}/access-tier",
                               json={"access_tier": "free_example"}, headers=member_a.csrf_headers)
    assert resp.status_code == 403  # author, not admin

    resp = await client.patch(f"/api/v1/research/{published_research.id}/access-tier",
                               json={"access_tier": "free_example"}, headers=moderator_user.csrf_headers)
    assert resp.status_code == 403  # moderator excluded per AD-19

    resp = await client.patch(f"/api/v1/research/{published_research.id}/access-tier",
                               json={"access_tier": "free_example"}, headers=admin_user.csrf_headers)
    assert resp.status_code == 200
    # Assert exactly one audit_logs row with action_type='research.access_tier_changed' now exists.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_invalid_access_tier_value_rejected_before_write(client, admin_user, published_research, db_session):
    resp = await client.patch(f"/api/v1/research/{published_research.id}/access-tier",
                               json={"access_tier": "premium"}, headers=admin_user.csrf_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_ACCESS_TIER"
    # Assert research.access_tier is unchanged and no audit_logs row was written.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_library_excludes_removed_and_restricted_research(client, member_a, removed_research, restricted_research):
    resp = await client.get("/api/v1/research/library", headers=member_a.auth_headers)
    ids = [item["id"] for item in resp.json()["items"] if "id" in item]
    assert str(removed_research.id) not in ids
    assert str(restricted_research.id) not in ids
