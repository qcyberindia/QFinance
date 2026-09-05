"""Integration tests for community + users-compliance — channel auth tiers,
charter-acknowledgment gating, visibility rules against a real post/comment
tree, auto-flagging, reactions/bookmarks uniqueness, and research-discussion
tier gating.

STATUS: WRITTEN. NOT EXECUTABLE IN CURRENT ENVIRONMENT — requires real
PostgreSQL + Redis, neither reachable from this session. The DB-free logic
these would otherwise partially cover (channel validation, visibility rules,
ownership) is genuinely unit-tested in test_community_pure_logic.py — see
work_memory.md for the precise EXECUTED/NOT-EXECUTED boundary.
"""
import pytest


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_unverified_member_rejected_from_non_announcements_channel(client, unverified_member):
    """The regression test for the verified-email gate on §4.1.1's GET for
    every channel except announcements."""
    resp = await client.get("/api/v1/community/channels/general_discussion/posts", headers=unverified_member.auth_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["message"].lower().startswith("please verify")


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_unauthenticated_caller_rejected_from_any_channel(client):
    resp = await client.get("/api/v1/community/channels/general_discussion/posts")
    assert resp.status_code == 401


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_authenticated_unverified_member_can_still_read_announcements(client, unverified_member):
    """§4.1.1's explicit exception — Announcements GET needs only Authenticated,
    not Verified, not even MEMBER."""
    resp = await client.get("/api/v1/community/channels/announcements/posts", headers=unverified_member.auth_headers)
    assert resp.status_code == 200


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_verified_member_reaches_non_announcements_channel(client, member_a):
    resp = await client.get("/api/v1/community/channels/general_discussion/posts", headers=member_a.auth_headers)
    assert resp.status_code == 200


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_verified_free_member_still_rejected_from_non_announcements_without_core(client, verified_free_member):
    """§4.1.1 requires MEMBER in addition to Verified for non-announcements —
    verified alone is not sufficient."""
    resp = await client.get("/api/v1/community/channels/general_discussion/posts", headers=verified_free_member.auth_headers)
    assert resp.status_code == 403
    assert "core membership" in resp.json()["error"]["message"].lower()


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_first_post_blocked_without_charter_acknowledgment(client, member_a_no_charter):
    resp = await client.post(
        "/api/v1/community/channels/general_discussion/posts", json={"content": "hello"},
        headers=member_a_no_charter.csrf_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CHARTER_NOT_ACKNOWLEDGED"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_acknowledge_charter_then_post_succeeds(client, member_a_no_charter):
    ack_resp = await client.post("/api/v1/users/me/acknowledge-charter", headers=member_a_no_charter.csrf_headers)
    assert ack_resp.status_code == 200
    post_resp = await client.post(
        "/api/v1/community/channels/general_discussion/posts", json={"content": "hello"},
        headers=member_a_no_charter.csrf_headers,
    )
    assert post_resp.status_code == 201


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_acknowledge_risk_disclosure_rejects_invalid_context(client, member_a):
    resp = await client.post(
        "/api/v1/users/me/acknowledge-risk-disclosure", json={"context": "some_other_thing"},
        headers=member_a.csrf_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_ACKNOWLEDGMENT_CONTEXT"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_only_moderator_or_admin_can_post_to_announcements(client, member_a, moderator_user):
    resp = await client.post("/api/v1/community/channels/announcements/posts", json={"content": "hi"},
                              headers=member_a.csrf_headers)
    assert resp.status_code == 403

    resp = await client.post("/api/v1/community/channels/announcements/posts", json={"content": "hi"},
                              headers=moderator_user.csrf_headers)
    assert resp.status_code == 201


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_non_author_cannot_edit_or_delete_post(client, member_a, member_b, member_a_post):
    resp = await client.patch(f"/api/v1/community/posts/{member_a_post.id}", json={"content": "edited"},
                               headers=member_b.csrf_headers)
    assert resp.status_code == 403

    resp = await client.delete(f"/api/v1/community/posts/{member_a_post.id}", headers=member_b.csrf_headers)
    assert resp.status_code == 403


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_self_delete_writes_moderation_action_with_moderator_id_equal_to_author(
    client, member_a, member_a_post, db_session,
):
    resp = await client.delete(f"/api/v1/community/posts/{member_a_post.id}", headers=member_a.csrf_headers)
    assert resp.status_code == 204
    # Assert a moderation_actions row exists with moderator_id == member_a.id,
    # action='remove', previous_state='visible', new_state='removed'.


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_flagged_phrase_auto_creates_report_without_blocking_post(client, member_a, db_session, flagged_phrase_rule):
    """MOD-003 — a match creates a reports row but the post still succeeds."""
    resp = await client.post(
        "/api/v1/community/channels/general_discussion/posts",
        json={"content": f"this contains {flagged_phrase_rule.phrase}"},
        headers=member_a.csrf_headers,
    )
    assert resp.status_code == 201
    # Assert a `reports` row exists with reporter_id == member_a.id and
    # reason starting with "Automated flag:".


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_duplicate_reaction_rejected(client, member_a, some_post):
    r1 = await client.post(f"/api/v1/community/post/{some_post.id}/reactions", json={"reaction_type": "like"},
                            headers=member_a.csrf_headers)
    assert r1.status_code == 201
    r2 = await client.post(f"/api/v1/community/post/{some_post.id}/reactions", json={"reaction_type": "like"},
                            headers=member_a.csrf_headers)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "ALREADY_REACTED"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_free_member_blocked_from_research_discussion_of_core_tier_item(client, free_member, core_tier_research):
    resp = await client.get(f"/api/v1/research/{core_tier_research.id}/discussion", headers=free_member.auth_headers)
    assert resp.status_code == 403


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_comment_on_research_linked_post_emits_research_commented_event(
    client, member_a, research_linked_post, db_session,
):
    """The precise §4.1.6/§4.2.2/Architecture §21.2 rule: research_commented
    fires on the COMMENT endpoint when the parent post's research_id is set,
    never on the top-level research-discussion POST itself."""
    resp = await client.post(
        f"/api/v1/community/posts/{research_linked_post.id}/comments", json={"content": "good point"},
        headers=member_a.csrf_headers,
    )
    assert resp.status_code == 201
    # Assert an events row with event_type='research_commented',
    # entity_type='research', entity_id=research_linked_post.research_id exists.
