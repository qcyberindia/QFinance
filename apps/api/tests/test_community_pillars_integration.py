"""Community pillars — Discussion, Q&A, Thesis — against the real app and the
real database (conftest.py's rolled-back savepoint isolation). Uses the same
real-login + CSRF pattern as test_research_ai_add_to_research.py.

Covers the feed endpoint (GET /community/posts), the thesis snapshot
endpoint (GET /community/posts/{id}/thesis), the Research -> Thesis bridge,
moderation/verification gates on single-post reads, Saved/reaction
visibility, privacy of public serializers, and contribution dedup.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.modules.companies.models import Company
from app.modules.community.models import Post
from tests.conftest import _make_user

settings = get_settings()

PRIVATE_KEYS = {"email", "name", "password_hash", "role_grants", "email_verified_at", "status_reason"}


async def _verify(db_session, ru) -> None:
    ru.user.email_verified_at = datetime.now(timezone.utc)
    await db_session.flush()


async def _login(client, ru) -> dict:
    client.cookies.clear()
    resp = await client.post("/api/v1/auth/login", json={"email": ru.email, "password": ru.raw_password})
    assert resp.status_code == 200, resp.text
    return {"X-CSRF-Token": client.cookies.get(settings.CSRF_COOKIE_NAME)}


async def _member(client, db_session) -> tuple[object, dict]:
    """A verified member who has acknowledged the charter, logged in."""
    ru = await _make_user(db_session)
    await _verify(db_session, ru)
    headers = await _login(client, ru)
    resp = await client.post("/api/v1/users/me/acknowledge-charter", headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return ru, headers


async def _post(client, headers, content: str, post_type: str) -> dict:
    resp = await client.post("/api/v1/community/channels/general_discussion/posts",
                             json={"content": content, "post_type": post_type}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _walk_keys(obj) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "company":  # public company reference (name/symbol/exchange), not a person
                assert set(v or {}) <= {"name", "symbol", "exchange"}
                continue
            keys.add(k)
            keys |= _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            keys |= _walk_keys(v)
    return keys


async def _published_research(client, db_session, headers) -> str:
    company = Company(id=uuid.uuid4(), name="Thesis Test Industries", symbol="TTIND", exchange="NSE")
    db_session.add(company)
    await db_session.flush()
    resp = await client.post("/api/v1/research", json={
        "company_id": str(company.id), "research_type": "long_term", "title": "Can margins hold?",
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    rid = resp.json()["id"]
    resp = await client.patch(f"/api/v1/research/{rid}", json={
        "summary": "Margins hold if pricing power survives new entrants.",
        "business_model": "Sells branded industrial parts to OEMs.",
        "bear_case": "A price war compresses margins.",
        "risk_register": "Customer concentration.",
        "invalidation_conditions": "Gross margin below 30% for two quarters.",
        "conflict_disclosed": False, "position_disclosed": False, "research_date": "2026-10-01",
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"/api/v1/research/{rid}/sources",
                             json={"label": "Annual report FY26", "reference": "https://example.com/ar"}, headers=headers)
    assert resp.status_code == 201, resp.text
    resp = await client.post(f"/api/v1/research/{rid}/publish", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    return rid


# ---------------------------------------------------------------------------
# Discussion
# ---------------------------------------------------------------------------

async def test_discussion_create_read_reply_and_feed_filter(client, db_session):
    _, headers = await _member(client, db_session)
    post = await _post(client, headers, "How should we value high growth with weak cash flow?", "discussion")

    resp = await client.get(f"/api/v1/community/posts/{post['id']}")
    assert resp.status_code == 200 and resp.json()["post_type"] == "discussion"

    resp = await client.post(f"/api/v1/community/posts/{post['id']}/comments", json={"content": "Look at FCF conversion."},
                             headers=headers)
    assert resp.status_code == 201
    comment_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/community/comments/{comment_id}/replies", json={"content": "And capex intensity."},
                             headers=headers)
    assert resp.status_code == 201 and resp.json()["parent_comment_id"] == comment_id

    feed = (await client.get("/api/v1/community/posts?pillar=discussion")).json()
    assert post["id"] in [p["id"] for p in feed["items"]]
    questions = (await client.get("/api/v1/community/posts?pillar=question")).json()
    assert post["id"] not in [p["id"] for p in questions["items"]]


async def test_non_author_cannot_edit_or_delete_discussion(client, db_session):
    _, headers_a = await _member(client, db_session)
    post = await _post(client, headers_a, "Owner's post", "discussion")
    _, headers_b = await _member(client, db_session)
    assert (await client.patch(f"/api/v1/community/posts/{post['id']}", json={"content": "x"},
                               headers=headers_b)).status_code == 403
    assert (await client.delete(f"/api/v1/community/posts/{post['id']}", headers=headers_b)).status_code == 403


async def test_unverified_user_cannot_read_feed_or_post(client, db_session):
    _, headers = await _member(client, db_session)
    post = await _post(client, headers, "Verified-only content", "discussion")
    unverified = await _make_user(db_session)
    headers_u = await _login(client, unverified)
    assert (await client.get("/api/v1/community/posts")).status_code == 403
    assert (await client.get(f"/api/v1/community/posts/{post['id']}")).status_code == 403
    resp = await client.post("/api/v1/community/channels/general_discussion/posts",
                             json={"content": "hi", "post_type": "discussion"}, headers=headers_u)
    assert resp.status_code == 403


async def test_removed_post_is_not_readable_by_id_and_not_in_feed(client, db_session):
    _, headers = await _member(client, db_session)
    post = await _post(client, headers, "Soon removed", "discussion")
    assert (await client.delete(f"/api/v1/community/posts/{post['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/v1/community/posts/{post['id']}")).status_code == 404
    feed = (await client.get("/api/v1/community/posts")).json()
    assert post["id"] not in [p["id"] for p in feed["items"]]


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------

async def test_question_create_read_and_answer(client, db_session):
    _, headers_a = await _member(client, db_session)
    q = await _post(client, headers_a, "How do I read ROCE for a bank?", "question")
    _, headers_b = await _member(client, db_session)
    resp = await client.post(f"/api/v1/community/posts/{q['id']}/comments",
                             json={"content": "Banks use ROE/ROA instead."}, headers=headers_b)
    assert resp.status_code == 201
    detail = (await client.get(f"/api/v1/community/posts/{q['id']}")).json()
    assert detail["post_type"] == "question" and detail["comment_count"] == 1
    feed = (await client.get("/api/v1/community/posts?pillar=question")).json()
    assert q["id"] in [p["id"] for p in feed["items"]]
    # Answers can't be edited by someone else.
    answer_id = (await client.get(f"/api/v1/community/posts/{q['id']}/comments")).json()["items"][0]["id"]
    await _login(client, (await _member(client, db_session))[0])
    resp = await client.patch(f"/api/v1/community/comments/{answer_id}", json={"content": "x"},
                              headers={"X-CSRF-Token": client.cookies.get(settings.CSRF_COOKIE_NAME)})
    assert resp.status_code == 403


async def test_invalid_pillar_rejected(client, db_session):
    await _member(client, db_session)
    assert (await client.get("/api/v1/community/posts?pillar=premium")).status_code == 400


# ---------------------------------------------------------------------------
# Thesis
# ---------------------------------------------------------------------------

async def test_thesis_cannot_be_posted_directly_to_a_channel(client, db_session):
    _, headers = await _member(client, db_session)
    resp = await client.post("/api/v1/community/channels/general_discussion/posts",
                             json={"content": "My thesis", "post_type": "thesis"}, headers=headers)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "THESIS_REQUIRES_RESEARCH"


async def test_publish_thesis_from_research_appears_in_thesis_feed_with_snapshot(client, db_session):
    author, headers = await _member(client, db_session)
    rid = await _published_research(client, db_session, headers)
    resp = await client.post(f"/api/v1/research/{rid}/publish-to-community",
                             json={"summary": "Margins hold if pricing power survives."}, headers=headers)
    assert resp.status_code == 200, resp.text
    post_id = resp.json()["id"]

    # Re-sharing doesn't duplicate the thesis post.
    again = await client.post(f"/api/v1/research/{rid}/publish-to-community",
                              json={"summary": "again"}, headers=headers)
    assert again.status_code == 200 and again.json()["id"] == post_id
    count = (await db_session.execute(
        select(Post).where(Post.research_id == uuid.UUID(rid), Post.post_type == "thesis"))).scalars().all()
    assert len(count) == 1

    # Thesis contribution recorded exactly once.
    rows = (await db_session.execute(text(
        "SELECT COUNT(*) FROM contributions WHERE user_id = :u AND source_type = 'thesis_published'"
    ), {"u": str(author.id)})).scalar_one()
    assert rows == 1

    # Another verified member sees it in the Thesis pillar with its company ref.
    reader, reader_headers = await _member(client, db_session)
    feed = (await client.get("/api/v1/community/posts?pillar=thesis")).json()
    item = next(p for p in feed["items"] if p["id"] == post_id)
    assert item["thesis"]["company"]["symbol"] == "TTIND"

    snap = (await client.get(f"/api/v1/community/posts/{post_id}/thesis")).json()
    assert snap["sections"]["invalidation_conditions"] == "Gross margin below 30% for two quarters."
    assert snap["sources"][0]["label"] == "Annual report FY26"

    # Challenge the reasoning through the ordinary reply thread.
    resp = await client.post(f"/api/v1/community/posts/{post_id}/comments",
                             json={"content": "Prove-me-wrong: new entrant pricing data says otherwise."},
                             headers=reader_headers)
    assert resp.status_code == 201


async def test_thesis_snapshot_never_exposes_unpublished_edits_or_private_fields(client, db_session):
    _, headers = await _member(client, db_session)
    rid = await _published_research(client, db_session, headers)
    post_id = (await client.post(f"/api/v1/research/{rid}/publish-to-community",
                                 json={"summary": "s"}, headers=headers)).json()["id"]
    # Bypass the API to simulate a live-row change that never went through a
    # versioned publish: Community must still show the published snapshot.
    await db_session.execute(text("UPDATE research SET business_model = 'SECRET DRAFT TEXT' WHERE id = :r"), {"r": rid})
    await db_session.flush()

    await _member(client, db_session)
    snap = (await client.get(f"/api/v1/community/posts/{post_id}/thesis")).json()
    assert snap["sections"]["business_model"] == "Sells branded industrial parts to OEMs."
    assert "SECRET DRAFT TEXT" not in str(snap)
    assert not (_walk_keys(snap) & (PRIVATE_KEYS | {"author_id", "access_tier", "moderation_status"}))


async def test_thesis_hidden_when_research_no_longer_published(client, db_session):
    _, headers = await _member(client, db_session)
    rid = await _published_research(client, db_session, headers)
    post_id = (await client.post(f"/api/v1/research/{rid}/publish-to-community",
                                 json={"summary": "s"}, headers=headers)).json()["id"]
    await db_session.execute(text("UPDATE research SET moderation_status = 'removed' WHERE id = :r"), {"r": rid})
    await db_session.flush()
    await _member(client, db_session)
    assert (await client.get(f"/api/v1/community/posts/{post_id}/thesis")).status_code == 404
    assert (await client.get(f"/api/v1/community/posts/{post_id}")).json()["thesis"] is None


async def test_only_author_can_publish_research_to_community(client, db_session):
    _, headers = await _member(client, db_session)
    rid = await _published_research(client, db_session, headers)
    _, other_headers = await _member(client, db_session)
    resp = await client.post(f"/api/v1/research/{rid}/publish-to-community", json={"summary": "x"}, headers=other_headers)
    assert resp.status_code == 403


async def test_discussion_post_has_no_thesis_snapshot(client, db_session):
    _, headers = await _member(client, db_session)
    post = await _post(client, headers, "Just a discussion", "discussion")
    assert (await client.get(f"/api/v1/community/posts/{post['id']}/thesis")).status_code == 404


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------

async def test_public_post_and_comment_serializers_expose_no_private_identity(client, db_session):
    author, headers = await _member(client, db_session)
    post = await _post(client, headers, "Privacy check", "discussion")
    await client.post(f"/api/v1/community/posts/{post['id']}/comments", json={"content": "c"}, headers=headers)
    await _member(client, db_session)
    payloads = [
        (await client.get(f"/api/v1/community/posts/{post['id']}")).json(),
        (await client.get(f"/api/v1/community/posts/{post['id']}/comments")).json(),
        (await client.get("/api/v1/community/posts")).json(),
    ]
    for payload in payloads:
        assert not (_walk_keys(payload) & PRIVATE_KEYS)
        assert author.email not in str(payload)
        assert set(payload.get("author", {"id": 1, "username": 1}).keys()) <= {"id", "username"}


# ---------------------------------------------------------------------------
# Saved / reactions / Q-Points
# ---------------------------------------------------------------------------

async def test_saved_and_like_flags_and_removed_post_handling(client, db_session):
    author, headers_a = await _member(client, db_session)
    post = await _post(client, headers_a, "Save me", "discussion")
    _, headers_b = await _member(client, db_session)

    assert (await client.post("/api/v1/community/bookmarks", json={"post_id": post["id"]}, headers=headers_b)).status_code == 201
    assert (await client.post(f"/api/v1/community/post/{post['id']}/reactions", json={}, headers=headers_b)).status_code == 201
    detail = (await client.get(f"/api/v1/community/posts/{post['id']}")).json()
    assert detail["viewer_bookmarked"] is True and detail["viewer_reacted"] is True

    # Like credit is awarded once to the author, never twice for the same actor.
    await client.delete(f"/api/v1/community/post/{post['id']}/reactions", headers=headers_b)
    await client.post(f"/api/v1/community/post/{post['id']}/reactions", json={}, headers=headers_b)
    credits = (await db_session.execute(text(
        "SELECT COUNT(*) FROM contributions WHERE user_id = :u AND source_type = 'engagement_received' AND source_entity_id = :p"
    ), {"u": str(author.id), "p": post["id"]})).scalar_one()
    assert credits == 1

    # Author removes the post: Saved no longer shows its text; it can't be re-saved or liked.
    await _login(client, author)
    assert (await client.delete(f"/api/v1/community/posts/{post['id']}",
                                headers={"X-CSRF-Token": client.cookies.get(settings.CSRF_COOKIE_NAME)})).status_code == 204
    _, headers_c = await _member(client, db_session)
    assert (await client.post("/api/v1/community/bookmarks", json={"post_id": post["id"]}, headers=headers_c)).status_code == 404
    assert (await client.post(f"/api/v1/community/post/{post['id']}/reactions", json={}, headers=headers_c)).status_code == 404


async def test_saved_list_hides_removed_post_text(client, db_session):
    author, headers_a = await _member(client, db_session)
    post = await _post(client, headers_a, "Text that should disappear", "discussion")
    reader, headers_b = await _member(client, db_session)
    await client.post("/api/v1/community/bookmarks", json={"post_id": post["id"]}, headers=headers_b)
    await db_session.execute(text("UPDATE posts SET status = 'removed' WHERE id = :p"), {"p": post["id"]})
    await db_session.flush()
    saved = (await client.get("/api/v1/community/bookmarks")).json()
    assert saved["items"][0]["post_summary"] == "This post is no longer available."


async def test_self_comment_earns_no_contribution(client, db_session):
    author, headers = await _member(client, db_session)
    post = await _post(client, headers, "Mine", "question")
    await client.post(f"/api/v1/community/posts/{post['id']}/comments", json={"content": "self answer"}, headers=headers)
    n = (await db_session.execute(text(
        "SELECT COUNT(*) FROM contributions WHERE user_id = :u AND source_type = 'engagement_received'"
    ), {"u": str(author.id)})).scalar_one()
    assert n == 0
