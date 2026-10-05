"""Profile Control Center — own profile, edit, Saved, Q-Points and privacy,
against the real app + database (conftest.py rolled-back savepoints)."""
from sqlalchemy import text

from app.core.config import get_settings
from app.modules.contributions import service as contributions_service
from tests.conftest import _make_user
from tests.test_community_pillars_integration import _login, _member, _post, _walk_keys

settings = get_settings()
SECRET_KEYS = {"password_hash", "access_token", "role_grants", "kite_user_id", "api_key", "encrypted_api_key"}


async def _username(db_session, user) -> str:
    return (await db_session.execute(
        text("SELECT username FROM profiles WHERE user_id = :u"), {"u": str(user.id)})).scalar_one()


# ---------------------------------------------------------------------------
# Own profile
# ---------------------------------------------------------------------------

async def test_own_profile_requires_authentication(client):
    assert (await client.get("/api/v1/users/me/profile")).status_code == 401
    assert (await client.patch("/api/v1/users/me/profile", json={"bio": "x"})).status_code in (401, 403)


async def test_own_profile_returns_private_account_fields_only_to_self(client, db_session):
    user, _ = await _member(client, db_session)
    body = (await client.get("/api/v1/users/me/profile")).json()
    assert body["email"] == user.email and body["email_verified"] is True
    assert body["name"] and body["username"] == await _username(db_session, user)
    assert body["contribution_points"] == 0 and body["joined_at"]
    assert not (_walk_keys(body) & SECRET_KEYS) and "id" not in body and "user_id" not in body


async def test_update_profile_fields_and_public_profile_reflects_public_ones_only(client, db_session):
    user, headers = await _member(client, db_session)
    resp = await client.patch("/api/v1/users/me/profile", json={
        "name": "Private Real Name", "username": "renamed_member_01", "bio": "Long-term investor.",
        "experience_level": "intermediate",
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["username"] == "renamed_member_01" and body["bio"] == "Long-term investor."
    assert body["experience_level"] == "intermediate" and body["name"] == "Private Real Name"

    public = await client.get("/api/v1/profile/renamed_member_01")
    assert public.status_code == 200
    assert public.json()["bio"] == "Long-term investor." and public.json()["joined_at"]
    assert "Private Real Name" not in public.text and user.email not in public.text
    assert not (_walk_keys(public.json()) & (SECRET_KEYS | {"email", "name", "experience_level"}))


async def test_update_requires_csrf(client, db_session):
    await _member(client, db_session)
    assert (await client.patch("/api/v1/users/me/profile", json={"bio": "no csrf"})).status_code == 403


async def test_update_validation(client, db_session):
    _, headers = await _member(client, db_session)
    resp = await client.patch("/api/v1/users/me/profile", json={
        "name": "", "username": "no spaces!", "bio": "x" * 501, "experience_level": "expert",
    }, headers=headers)
    assert resp.status_code == 400
    assert set(resp.json()["error"]["fields"]) == {"name", "username", "bio", "experience_level"}


async def test_username_must_be_unique_case_insensitively(client, db_session):
    other = await _make_user(db_session, username="Taken_Name")
    _, headers = await _member(client, db_session)
    resp = await client.patch("/api/v1/users/me/profile", json={"username": "taken_name"}, headers=headers)
    assert resp.status_code == 400 and "username" in resp.json()["error"]["fields"]
    assert other  # still owns it


async def test_email_and_roles_cannot_be_changed_through_profile(client, db_session):
    user, headers = await _member(client, db_session)
    for field, value in (("email", "attacker@example.com"), ("role_grants", ["ADMIN"]), ("user_id", "x")):
        resp = await client.patch("/api/v1/users/me/profile", json={field: value}, headers=headers)
        assert resp.status_code == 422, field
    roles = (await db_session.execute(
        text("SELECT role_grants FROM profiles WHERE user_id = :u"), {"u": str(user.id)})).scalar_one()
    assert roles == ["FREE_MEMBER"]


async def test_user_cannot_edit_or_read_another_users_private_profile(client, db_session):
    victim, _ = await _member(client, db_session)
    victim_username = await _username(db_session, victim)
    attacker, headers = await _member(client, db_session)
    # The only editable profile is the session's own; there is no id to point at someone else.
    await client.patch("/api/v1/users/me/profile", json={"bio": "attacker bio"}, headers=headers)
    victim_bio = (await db_session.execute(
        text("SELECT bio FROM profiles WHERE user_id = :u"), {"u": str(victim.id)})).scalar_one()
    assert victim_bio is None
    assert (await client.get("/api/v1/users/me/profile")).json()["email"] == attacker.email
    assert (await client.get(f"/api/v1/users/me/profile?user_id={victim.id}")).json()["email"] == attacker.email
    public = (await client.get(f"/api/v1/profile/{victim_username}")).text
    assert victim.email not in public


# ---------------------------------------------------------------------------
# Saved
# ---------------------------------------------------------------------------

async def test_saved_lists_only_my_bookmarks_with_type_and_hides_removed_content(client, db_session):
    _, headers_a = await _member(client, db_session)
    question = await _post(client, headers_a, "A question worth saving", "question")
    removed = await _post(client, headers_a, "Secret text that gets removed", "discussion")

    _, headers_b = await _member(client, db_session)
    for p in (question, removed):
        assert (await client.post("/api/v1/community/bookmarks", json={"post_id": p["id"]}, headers=headers_b)).status_code == 201
    await db_session.execute(text("UPDATE posts SET status = 'removed' WHERE id = :p"), {"p": removed["id"]})
    await db_session.flush()

    items = {i["post_id"]: i for i in (await client.get("/api/v1/community/bookmarks")).json()["items"]}
    assert items[question["id"]]["post_type"] == "question" and items[question["id"]]["available"] is True
    assert items[removed["id"]]["available"] is False and items[removed["id"]]["post_type"] is None
    assert "Secret text" not in str(items)

    await _member(client, db_session)  # a third member sees none of B's saved items
    assert (await client.get("/api/v1/community/bookmarks")).json()["items"] == []


# ---------------------------------------------------------------------------
# Q-Points
# ---------------------------------------------------------------------------

async def test_q_points_are_per_user_and_never_monetary(client, db_session):
    author, headers_a = await _member(client, db_session)
    post = await _post(client, headers_a, "Earn points", "discussion")
    _, headers_b = await _member(client, db_session)
    await client.post(f"/api/v1/community/post/{post['id']}/reactions", json={}, headers=headers_b)

    mine = (await client.get("/api/v1/credits/me")).json()  # B's own (empty) history
    assert mine["points"] == 0 and mine["entries"] == []

    await _login(client, author)
    theirs = (await client.get("/api/v1/credits/me")).json()
    assert theirs["points"] == contributions_service.POINTS_BY_SOURCE["engagement_received"]
    assert not (_walk_keys(theirs) & {"balance_paise", "amount_paise", "paise", "balance", "currency"})
    assert (await client.get("/api/v1/users/me/profile")).json()["contribution_points"] == theirs["points"]
    ledger = (await db_session.execute(
        text("SELECT COUNT(*) FROM credit_ledger WHERE user_id = :u"), {"u": str(author.id)})).scalar_one()
    assert ledger == 0
