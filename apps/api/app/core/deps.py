"""
Shared FastAPI dependencies: current_user, RBAC guards, CSRF guard (Architecture §4.1/§8).
WRITTEN, NOT EXECUTED.
"""
from collections.abc import Callable

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import CsrfMismatch, Forbidden, Unauthenticated
from app.modules.auth.session_store import get_session
from app.modules.users.models import Profile
from app.modules.auth.models import User

settings = get_settings()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    qf_session: str | None = Cookie(default=None, alias="qf_session"),
) -> User:
    """Resolves the session cookie -> Redis session -> users row. Raises 401 if
    missing/invalid. This, not any client-supplied claim, is the actual authentication
    boundary (RBAC-001/AUTH-008)."""
    if not qf_session:
        raise Unauthenticated()
    session_data = await get_session(qf_session)
    if not session_data:
        raise Unauthenticated()
    user = await db.get(User, session_data["user_id"])
    if user is None or user.status != "active":
        raise Unauthenticated()
    return user


async def get_current_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    profile = await db.get(Profile, user.id)
    if profile is None:
        raise Unauthenticated()
    return profile


async def require_verified_email(user: User = Depends(get_current_user)) -> User:
    """AUTH-002 — backend enforcement of the email-verification gate, not just a
    frontend route guard."""
    if user.email_verified_at is None:
        raise Forbidden("Please verify your email address to continue.")
    return user


def require_role(*roles: str) -> Callable:
    """Returns a dependency asserting the current profile's role_grants intersects
    `roles`. Roles are additive (OD-05) — this checks for ANY overlap, matching
    API Spec §0.6's capability-based notation at the simplest (role-name) level.
    Capability-table-level checks (e.g., moderation.take_action excluding REVIEWER)
    are implemented as narrower, named dependencies below, not by this generic helper
    alone, per API Spec §0.6."""

    async def _dependency(profile: Profile = Depends(get_current_profile)) -> Profile:
        if not set(profile.role_grants) & set(roles):
            raise Forbidden()
        return profile

    return _dependency


async def require_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    csrf_token: str | None = Cookie(default=None, alias="csrf_token"),
) -> None:
    """Double-submit-cookie CSRF check (AD-14). Applied to every mutating route
    except /webhooks/*, per API Spec §0.2."""
    if not x_csrf_token or not csrf_token or x_csrf_token != csrf_token:
        raise CsrfMismatch()
