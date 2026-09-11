"""Auth: registration, email verification, password reset, session invalidation.

STATUS: WRITTEN, NOT EXECUTED IN THIS SESSION. Converted from placeholder/skip
form (see work_memory.md for that history) to real integration tests against
`conftest.py`'s transactional-Postgres + isolated-Redis fixtures, once those
fixtures existed to support them — no `@pytest.mark.skip` remains in this file.
Every test exercises the real `app.main.app` over ASGI transport, the real
`auth_service`/`token_store`/`session_store` functions (never re-implemented or
mocked), and asserts against real database rows or real Redis state via the
same `db_session`/Redis client the app itself used during the request — not
duplicated application logic.

Run with (not run by this session — no execution access to the real host):
    cd apps/api && PYTHONPATH=. pytest -q tests/test_auth_flows.py -v
"""
import uuid

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.modules.analytics.models import Event
from app.modules.auth import token_store
from app.modules.auth.models import User
from app.modules.auth.session_store import get_session
from app.modules.users.models import Profile


async def _get_event(db_session, *, user_id, event_type) -> Event | None:
    result = await db_session.execute(
        select(Event).where(Event.user_id == user_id, Event.event_type == event_type)
    )
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

async def test_registration_creates_unverified_user(client, db_session):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "new.member@example.com", "password": "a-strong-enough-password",
        "name": "New Member", "username": "new_member",
    })
    assert resp.status_code == 201
    user_id = uuid.UUID(resp.json()["user_id"])

    user = await db_session.get(User, user_id)
    assert user is not None
    assert user.email_verified_at is None

    profile = await db_session.get(Profile, user_id)
    assert profile is not None
    assert profile.role_grants == ["FREE_MEMBER"]

    signup_event = await _get_event(db_session, user_id=user_id, event_type="signup")
    assert signup_event is not None


async def test_registration_rejects_duplicate_email(client, existing_user):
    resp = await client.post("/api/v1/auth/register", json={
        "email": existing_user.email, "password": "another-strong-password",
        "name": "Someone Else", "username": "someone_else_" + uuid.uuid4().hex[:8],
    })
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


async def test_registration_rejects_duplicate_username(client, existing_user_profile):
    resp = await client.post("/api/v1/auth/register", json={
        "email": f"different_{uuid.uuid4().hex[:8]}@example.com", "password": "another-strong-password",
        "name": "Someone Else", "username": existing_user_profile.username,
    })
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "USERNAME_TAKEN"


async def test_registration_rejects_short_password(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": f"shortpw_{uuid.uuid4().hex[:8]}@example.com", "password": "short",
        "name": "X", "username": "short_pw_user_" + uuid.uuid4().hex[:8],
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PASSWORD_TOO_SHORT"


async def test_registration_succeeds_even_when_email_delivery_unavailable(client, db_session, no_resend_api_key):
    """Direct regression test for the fix made in an earlier pass (see
    work_memory.md §K.3, fix 1): with no RESEND_API_KEY configured (this
    project's actual dev-environment default, forced explicitly here via the
    `no_resend_api_key` fixture rather than relying on ambient config),
    registration must still return 201 — the account is created and usable
    regardless of whether the verification email could be sent."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": f"no.email.needed.{uuid.uuid4().hex[:8]}@example.com", "password": "a-strong-enough-password",
        "name": "No Email", "username": "no_email_needed_" + uuid.uuid4().hex[:8],
    })
    assert resp.status_code == 201  # NOT 500, even though the email step could not complete


async def test_registration_succeeds_even_when_token_creation_raises(client, db_session, monkeypatch):
    """The SPECIFIC regression this fix targeted: a Redis error during
    create_verification_token() (not an EmailServiceError) must not propagate
    uncaught. Forces that exact failure via monkeypatch rather than actually
    taking Redis down, since a real outage isn't reproducible from a test."""
    from app.modules.auth import service as auth_service

    async def _boom(user_id):
        raise RuntimeError("simulated Redis outage during token creation")

    monkeypatch.setattr(auth_service, "create_verification_token", _boom)

    resp = await client.post("/api/v1/auth/register", json={
        "email": f"redis.down.{uuid.uuid4().hex[:8]}@example.com", "password": "a-strong-enough-password",
        "name": "Redis Down", "username": "redis_down_" + uuid.uuid4().hex[:8],
    })
    assert resp.status_code == 201  # account still created despite the simulated Redis failure


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

async def test_verification_success_sets_email_verified_at(client, db_session, unverified_user_with_token):
    resp = await client.post("/api/v1/auth/verify-email", json={"token": unverified_user_with_token.token})
    assert resp.status_code == 200
    assert resp.json() == {"verified": True}

    user = await db_session.get(User, unverified_user_with_token.id)
    assert user.email_verified_at is not None

    event = await _get_event(db_session, user_id=unverified_user_with_token.id, event_type="email_verified")
    assert event is not None


async def test_verification_rejects_invalid_token(client):
    resp = await client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


async def test_verification_rejects_expired_token(client, expired_verification_token):
    resp = await client.post("/api/v1/auth/verify-email", json={"token": expired_verification_token})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


async def test_verification_token_cannot_be_replayed(client, unverified_user_with_token):
    """GETDEL makes the token single-use — the second call with the same token
    must fail even though the first one succeeded."""
    token = unverified_user_with_token.token
    first = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert first.status_code == 200

    second = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

async def test_password_reset_request_always_returns_sent_true_for_existing_email(client, existing_user):
    resp = await client.post("/api/v1/auth/password-reset/request", json={"email": existing_user.email})
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}


async def test_password_reset_request_returns_sent_true_for_nonexistent_email_too(client):
    """API Spec §1.5's explicit privacy requirement — must not leak whether an
    email is registered via a different response shape/status code."""
    resp = await client.post("/api/v1/auth/password-reset/request",
                              json={"email": "definitely.not.registered@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}


async def test_password_reset_request_succeeds_even_when_email_delivery_unavailable(
    client, existing_user, no_resend_api_key,
):
    resp = await client.post("/api/v1/auth/password-reset/request", json={"email": existing_user.email})
    assert resp.status_code == 200  # NOT 500


async def test_password_reset_confirm_rejects_invalid_token(client):
    resp = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": "not-a-real-token", "new_password": "a-perfectly-fine-new-password",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


async def test_password_reset_confirm_rejects_expired_token(client, expired_reset_token):
    resp = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": expired_reset_token, "new_password": "a-perfectly-fine-new-password",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


async def test_password_reset_confirm_rejects_weak_new_password_without_consuming_token(
    client, valid_reset_token,
):
    """The documented ordering guarantee: policy validation happens BEFORE token
    consumption, so a weak-password attempt doesn't burn a valid, still-usable
    token — the same token must still work on a retry with a strong password."""
    weak_resp = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": valid_reset_token, "new_password": "short",
    })
    assert weak_resp.status_code == 400
    assert weak_resp.json()["error"]["code"] == "PASSWORD_TOO_SHORT"

    retry_resp = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": valid_reset_token, "new_password": "a-perfectly-fine-new-password",
    })
    assert retry_resp.status_code == 200  # same token, still valid


async def test_password_reset_confirm_succeeds_and_changes_password(client, db_session, valid_reset_token, target_user):
    resp = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": valid_reset_token, "new_password": "a-perfectly-fine-new-password",
    })
    assert resp.status_code == 200
    assert resp.json() == {"reset": True}

    await db_session.refresh(target_user.user)
    assert not verify_password(target_user.raw_password, target_user.user.password_hash)
    assert verify_password("a-perfectly-fine-new-password", target_user.user.password_hash)


async def test_password_reset_token_cannot_be_replayed(client, valid_reset_token):
    first = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": valid_reset_token, "new_password": "first-new-password-here",
    })
    assert first.status_code == 200

    second = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": valid_reset_token, "new_password": "second-attempted-password",
    })
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


async def test_password_reset_invalidates_all_existing_sessions(
    client, db_session, target_user, target_user_two_active_sessions, valid_reset_token,
):
    """AD-03's revocation-friendly design — every session for this user, from
    any device, must stop working after a password reset."""
    session_a_headers, session_b_headers = target_user_two_active_sessions

    pre_check_a = await client.get("/api/v1/auth/session", headers=session_a_headers)
    assert pre_check_a.status_code == 200  # sanity: session A works before reset

    reset_resp = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": valid_reset_token, "new_password": "a-perfectly-fine-new-password",
    })
    assert reset_resp.status_code == 200

    post_check_a = await client.get("/api/v1/auth/session", headers=session_a_headers)
    assert post_check_a.status_code == 401  # session A now dead

    post_check_b = await client.get("/api/v1/auth/session", headers=session_b_headers)
    assert post_check_b.status_code == 401  # session B also dead


async def test_password_reset_does_not_emit_an_unsupported_event_type(client, db_session, valid_reset_token, target_user):
    """The `events` table's CHECK constraint does not include a password-reset
    event type at all (verified directly against analytics/models.py's
    _EVENT_TYPES) — confirms the implementation correctly does NOT attempt to
    emit one (which would violate the CHECK constraint and roll back the
    whole successful password change)."""
    count_before = (await db_session.execute(
        select(Event).where(Event.user_id == target_user.id)
    )).scalars().all()

    resp = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": valid_reset_token, "new_password": "a-perfectly-fine-new-password",
    })
    assert resp.status_code == 200

    count_after = (await db_session.execute(
        select(Event).where(Event.user_id == target_user.id)
    )).scalars().all()
    assert len(count_after) == len(count_before)  # no new events row


# ---------------------------------------------------------------------------
# Login gating on suspension
# ---------------------------------------------------------------------------

async def test_suspended_account_cannot_log_in(client, suspended_user):
    resp = await client.post("/api/v1/auth/login", json={
        "email": suspended_user.email, "password": suspended_user.raw_password,
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_SUSPENDED"
