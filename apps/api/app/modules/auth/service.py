"""
Auth business logic — API Specification V1 §1 (AUTH-001-009).
Framework-agnostic where practical (Architecture Principle 4 — testable without
the route layer); route handlers in router.py delegate here.
WRITTEN, NOT EXECUTED — this has not been run against a real database in this session.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, QFinanceAPIError
from app.core.config import get_settings
from app.core.security import hash_password, validate_password_policy, verify_password
from app.integrations.email_service import send_password_reset_email, send_verification_email
from app.modules.analytics.models import emit_event
from app.modules.auth.models import User
from app.modules.auth.session_store import create_session, destroy_all_sessions_for_user
from app.modules.auth.token_store import (
    consume_password_reset_token, consume_verification_token,
    create_password_reset_token, create_verification_token,
)
from app.modules.users.models import Profile

logger = logging.getLogger("qfinance.auth")
settings = get_settings()


async def register(db: AsyncSession, *, email: str, password: str, name: str, username: str) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        raise QFinanceAPIError("EMAIL_ALREADY_REGISTERED", "This email is already registered.", 409)

    existing_username = (await db.execute(select(Profile).where(Profile.username == username))).scalar_one_or_none()
    if existing_username is not None:
        raise QFinanceAPIError("USERNAME_TAKEN", "This username is already taken.", 409)

    policy_error = validate_password_policy(password)
    if policy_error:
        raise QFinanceAPIError("PASSWORD_TOO_SHORT", policy_error, 400)

    user = User(id=uuid.uuid4(), email=email, password_hash=hash_password(password))
    db.add(user)
    await db.flush()  # populate user.id before FK reference below

    profile = Profile(user_id=user.id, name=name, username=username, role_grants=["FREE_MEMBER"])
    db.add(profile)

    await emit_event(db, user_id=user.id, event_type="signup")
    await db.commit()

    # AUTH-001 — "triggers EmailService verification email." Deliberately OUTSIDE
    # the transaction above and wrapped so it can never fail registration itself:
    # the account is real and usable (module-01A's README/PRD note nothing about
    # verification being required to log in, only to reach Verified-tier endpoints)
    # the moment the commit above succeeds: an email-send hiccup is a real but
    # non-fatal problem, not a reason to roll back a successful account creation.
    #
    # BUG FIX (this audit pass): the original code only caught `EmailServiceError`,
    # but `create_verification_token()` is a Redis call, not an EmailService call —
    # a Redis connection error there is NOT an EmailServiceError and would have
    # propagated uncaught, turning an already-committed, successful registration
    # into a misleading 500 response to the caller (the account WOULD exist, but
    # the client would be told registration failed). Broadened to catch any
    # exception from this whole "create token + send email" step as equally
    # non-fatal to the registration response — the account creation above has
    # already committed regardless of what happens here.
    try:
        token = await create_verification_token(user.id)
        verification_link = f"{settings.FRONTEND_BASE_URL}/verify-email?token={token}"
        send_verification_email(to_email=user.email, verification_link=verification_link)
    except Exception as e:  # noqa: BLE001 — deliberately broad, see comment above
        logger.warning("Verification token/email step failed for user %s: %s", user.id, e)

    return user


async def login(db: AsyncSession, *, email: str, password: str) -> tuple[User, str]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    # Deliberately identical error for wrong-email vs wrong-password (API Spec §1.3).
    if user is None or not verify_password(password, user.password_hash):
        raise QFinanceAPIError("INVALID_CREDENTIALS", "Incorrect email or password.", 401)
    if user.status == "suspended":
        raise QFinanceAPIError("ACCOUNT_SUSPENDED", "This account has been suspended.", 403)

    user.last_login_at = datetime.now(timezone.utc)
    await emit_event(db, user_id=user.id, event_type="login")
    await db.commit()

    session_token = await create_session(user.id)
    return user, session_token


async def logout(session_token: str) -> None:
    from app.modules.auth.session_store import destroy_session
    await destroy_session(session_token)


async def verify_email(db: AsyncSession, *, token: str) -> None:
    """API Spec §1.2 (AUTH-002). Sets `email_verified_at`, emits `email_verified`
    event. Token is consumed (deleted from Redis) whether or not it resolves to a
    valid, still-existing user — a token that pointed at a since-deleted account
    should not remain replayable."""
    user_id = await consume_verification_token(token)
    if user_id is None:
        raise QFinanceAPIError("TOKEN_INVALID_OR_EXPIRED", "This verification link is invalid or has expired.", 400)

    user = await db.get(User, user_id)
    if user is None:
        # Token was valid but the account no longer exists (deleted between
        # registration and click) — same public error, no account-existence leak.
        raise QFinanceAPIError("TOKEN_INVALID_OR_EXPIRED", "This verification link is invalid or has expired.", 400)

    user.email_verified_at = datetime.now(timezone.utc)
    await emit_event(db, user_id=user.id, event_type="email_verified")
    await db.commit()


async def request_password_reset(db: AsyncSession, *, email: str) -> None:
    """API Spec §1.5 (AUTH-005). Always returns None/succeeds regardless of whether
    the email exists — this function must NEVER raise for "email not found," per
    the spec's explicit privacy requirement (the router always returns `200 {sent:
    true}` regardless of what happens in here). No token is created and no email is
    sent for a non-existent address — that's the actual privacy mechanism (an
    attacker timing the response or looking for a different status code learns
    nothing either way, since this function takes the same code path and returns
    the same way in both cases from the router's perspective)."""
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        return None

    # BUG FIX (this audit pass): same class of issue as register()'s fix above —
    # `create_password_reset_token()` is a Redis call, not caught by
    # `except EmailServiceError`. This function's contract is "must never raise
    # for email not found," and by extension should not surface an infra hiccup
    # here as a request failure either — broadened accordingly.
    try:
        token = await create_password_reset_token(user.id)
        reset_link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={token}"
        send_password_reset_email(to_email=user.email, reset_link=reset_link)
    except Exception as e:  # noqa: BLE001 — deliberately broad, see comment above
        logger.warning("Password reset token/email step failed for user %s: %s", user.id, e)
    return None


async def confirm_password_reset(db: AsyncSession, *, token: str, new_password: str) -> None:
    """API Spec §1.6 (AUTH-005/006). Order matters: password policy is validated
    BEFORE the token is consumed, so a request with a valid token but a weak new
    password fails without burning the (single-use) token — the user can retry with
    a better password using the same link. Only once the password itself is
    acceptable does this consume the token and, on success, invalidate every
    existing session for that user (AD-03's revocation-friendly design — forces
    re-login everywhere, a deliberate security default after a password reset)."""
    policy_error = validate_password_policy(new_password)
    if policy_error:
        raise QFinanceAPIError("PASSWORD_TOO_SHORT", policy_error, 400)

    user_id = await consume_password_reset_token(token)
    if user_id is None:
        raise QFinanceAPIError("TOKEN_INVALID_OR_EXPIRED", "This reset link is invalid or has expired.", 400)

    user = await db.get(User, user_id)
    if user is None:
        raise QFinanceAPIError("TOKEN_INVALID_OR_EXPIRED", "This reset link is invalid or has expired.", 400)

    user.password_hash = hash_password(new_password)
    await db.commit()

    # BUG FIX (this audit pass): the original code called this unwrapped, after
    # the commit above. destroy_all_sessions_for_user() is a Redis SCAN loop —
    # if Redis is unreachable, this raised uncaught, turning an already-successful,
    # already-committed password change into a misleading 500 response (the
    # password WOULD be changed, but the client would be told the reset failed,
    # potentially prompting a confusing retry). The primary operation (the
    # password change) has already succeeded and committed by this point;
    # failing to revoke old sessions is a secondary security hardening step,
    # not the operation's success criterion — logged as a warning, not raised.
    try:
        await destroy_all_sessions_for_user(user.id)
    except Exception as e:  # noqa: BLE001 — deliberately broad, see comment above
        logger.warning("Failed to revoke existing sessions for user %s after password reset: %s", user.id, e)


VALID_USER_STATUSES = ("active", "suspended", "deleted")


async def suspend_user(db: AsyncSession, *, user_id: uuid.UUID) -> str:
    """MOD-004/ADMIN-004 (API Spec §5.4). Used by moderation/service.py's
    take_action as one leg of a single atomic transaction (see
    community/service.py's apply_moderation_status_to_post docstring for the
    full non-committing-helper rationale shared by all three modules'
    equivalents of this function). Does not kill existing sessions: not
    needed, since core/deps.py's get_current_user already re-checks
    `user.status != 'active'` fresh from the DB on every request, so an
    existing session becomes unusable on the caller's very next request
    regardless — no separate session-revocation step is required for the
    'immediate effect' MOD-004/ADMIN-004 acceptance criteria describes."""
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    previous_state = user.status
    user.status = "suspended"
    await db.flush()
    return previous_state


async def reinstate_user(db: AsyncSession, *, user_id: uuid.UUID) -> str:
    """Reverse of suspend_user (API Spec §5.5)."""
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    previous_state = user.status
    user.status = "active"
    await db.flush()
    return previous_state
