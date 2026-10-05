"""Product-rule regression tests against the real app + database
(conftest.py's rolled-back savepoint isolation):

  1. Qfinera is free — published Research is readable by any member with no
     paid membership; drafts stay private to the author.
  2. Q-Points are not money — a score only: no rupee/paise values in any
     API response and no credit_ledger rows written.
"""
from sqlalchemy import text

from app.modules.contributions import service as contributions_service
from tests.test_community_pillars_integration import (
    _member, _post, _published_research, _walk_keys,
)

MONEY_KEYS = {"balance_paise", "amount_paise", "available_credit_paise", "effective_next_period_price_paise",
              "paise", "rupees", "balance", "amount", "currency"}


async def _ledger_rows(db_session, user_id) -> int:
    return (await db_session.execute(
        text("SELECT COUNT(*) FROM credit_ledger WHERE user_id = :u"), {"u": str(user_id)}
    )).scalar_one()


# ---------------------------------------------------------------------------
# Research: free access to published work, private drafts
# ---------------------------------------------------------------------------

async def test_draft_is_private_and_published_research_is_fully_visible_to_a_free_member(client, db_session):
    author, headers = await _member(client, db_session)
    # A separate draft that is never published.
    from tests.test_research_ai_add_to_research import _create_research, _make_company
    company = await _make_company(db_session)
    draft_id = await _create_research(client, company.id, headers)
    rid = await _published_research(client, db_session, headers)

    reader, _ = await _member(client, db_session)
    roles = (await db_session.execute(
        text("SELECT role_grants FROM profiles WHERE user_id = :u"), {"u": str(reader.id)})).scalar_one()
    assert "MEMBER" not in roles  # an ordinary free account, no paid membership

    assert (await client.get(f"/api/v1/research/{draft_id}")).status_code == 404
    resp = await client.get(f"/api/v1/research/{rid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "preview" not in body and "access_tier" not in body
    assert body["bear_case"] == "A price war compresses margins."
    assert body["invalidation_conditions"] == "Gross margin below 30% for two quarters."
    assert body["sources"][0]["label"] == "Annual report FY26"

    # Versions and sources are readable too; the draft's are not.
    assert (await client.get(f"/api/v1/research/{rid}/versions")).status_code == 200
    assert (await client.get(f"/api/v1/research/{draft_id}/sources")).status_code == 404


async def test_library_lists_full_items_without_preview_or_tier(client, db_session):
    _, headers = await _member(client, db_session)
    rid = await _published_research(client, db_session, headers)
    await _member(client, db_session)
    items = (await client.get("/api/v1/research/library?page_size=100")).json()["items"]
    mine = next(i for i in items if i["id"] == rid)
    assert "preview" not in mine and "access_tier" not in mine
    assert mine["source_count"] == 1


async def test_access_tier_endpoint_is_gone(client, db_session):
    _, headers = await _member(client, db_session)
    rid = await _published_research(client, db_session, headers)
    resp = await client.patch(f"/api/v1/research/{rid}/access-tier", json={"access_tier": "core"}, headers=headers)
    assert resp.status_code in (404, 405)


async def test_non_author_cannot_edit_published_research(client, db_session):
    _, headers = await _member(client, db_session)
    rid = await _published_research(client, db_session, headers)
    _, other = await _member(client, db_session)
    resp = await client.patch(f"/api/v1/research/{rid}", json={"summary": "hijack", "change_note": "x"}, headers=other)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Q-Points: a score, never money
# ---------------------------------------------------------------------------

async def test_q_points_awarded_once_without_any_monetary_ledger(client, db_session):
    author, headers_a = await _member(client, db_session)
    post = await _post(client, headers_a, "Points check", "question")
    # Own content earns nothing.
    await client.post(f"/api/v1/community/posts/{post['id']}/comments", json={"content": "self"}, headers=headers_a)
    assert await contributions_service.get_total_points(db_session, user_id=author.id) == 0

    _, headers_b = await _member(client, db_session)
    await client.post(f"/api/v1/community/post/{post['id']}/reactions", json={}, headers=headers_b)
    await client.delete(f"/api/v1/community/post/{post['id']}/reactions", headers=headers_b)
    await client.post(f"/api/v1/community/post/{post['id']}/reactions", json={}, headers=headers_b)  # re-like: no new points
    await client.post(f"/api/v1/community/posts/{post['id']}/comments", json={"content": "answer"}, headers=headers_b)

    points = await contributions_service.get_total_points(db_session, user_id=author.id)
    assert points == contributions_service.POINTS_BY_SOURCE["engagement_received"] * 2  # one like + one answer
    assert await _ledger_rows(db_session, author.id) == 0
    assert not hasattr(contributions_service, "POINTS_TO_PAISE_RATE")


async def test_q_points_api_returns_score_only(client, db_session):
    author, headers_a = await _member(client, db_session)
    rid = await _published_research(client, db_session, headers_a)
    await client.post(f"/api/v1/research/{rid}/publish-to-community", json={"summary": "s"}, headers=headers_a)

    resp = await client.get("/api/v1/credits/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["points"] == contributions_service.POINTS_BY_SOURCE["thesis_published"]
    assert body["entries"][0]["points"] == body["points"]
    assert not (_walk_keys(body) & MONEY_KEYS)
    assert "₹" not in str(body) and "paise" not in str(body).lower()
    assert await _ledger_rows(db_session, author.id) == 0


async def test_membership_response_has_no_q_point_credit_fields(client, db_session):
    await _member(client, db_session)
    resp = await client.get("/api/v1/membership/me")
    assert resp.status_code == 200, resp.text
    assert "available_credit_paise" not in resp.json()
    assert "effective_next_period_price_paise" not in resp.json()


async def test_profile_q_points_is_a_plain_number(client, db_session):
    author, headers_a = await _member(client, db_session)
    username = (await db_session.execute(
        text("SELECT username FROM profiles WHERE user_id = :u"), {"u": str(author.id)})).scalar_one()
    resp = await client.get(f"/api/v1/profile/{username}")
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json()["contribution_points"], int)
    assert not (_walk_keys(resp.json()) & MONEY_KEYS)

