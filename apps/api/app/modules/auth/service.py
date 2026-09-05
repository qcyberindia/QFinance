"""
Auth business logic — API Specification V1 §1 (AUTH-001-009).
Framework-agnostic where practical (Architecture Principle 4 — testable without
the route layer); route handlers in router.py delegate here.
WRITTEN, NOT EXECUTED — this has not been run against a real database in this session.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, QFinanceAPIError
from app.core.security import hash_password, validate_password_policy, verify_password
from app.modules.analytics.models import emit_event
from app.modules.auth.models import User
from app.modules.auth.session_store import create_session, destroy_all_sessions_for_user
from app.modules.users.models import Profile

# In-memory/Redis-backed verification & reset token stores would live here in a
# full implementation (short-TTL Redis keys, same pattern as session_store.py).
# Not implemented in this pass — flagged in the final report, not silently assumed done.


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

    # TODO(not implemented this pass): generate verification token, call EmailService.
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


async def request_password_reset(db: AsyncSession, *, email: str) -> None:
    # Always returns success regardless of whether the email exists (API Spec §1.5) —
    # this function intentionally never raises for "email not found."
    # TODO(not implemented this pass): generate reset token, call EmailService.
    return None


async def confirm_password_reset(db: AsyncSession, *, token: str, new_password: str) -> None:
    # TODO(not implemented this pass): resolve token -> user_id via Redis-backed store.
    policy_error = validate_password_policy(new_password)
    if policy_error:
        raise QFinanceAPIError("PASSWORD_TOO_SHORT", policy_error, 400)
    raise QFinanceAPIError("TOKEN_INVALID_OR_EXPIRED", "This reset link is invalid or has expired.", 400)


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
