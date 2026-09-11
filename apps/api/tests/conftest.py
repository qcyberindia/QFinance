"""Shared pytest fixtures for integration tests requiring a real PostgreSQL
database and Redis instance — auto-discovered by pytest for every test module
in this directory (no explicit import needed in test files).

DESIGN, STATED EXPLICITLY:

Database isolation: each test gets its own outer transaction on a dedicated
connection, with the `AsyncSession` created using
`join_transaction_mode="create_savepoint"` (SQLAlchemy 2.x). This means the
application's OWN `db.commit()` calls (register(), login(), verify_email(),
confirm_password_reset(), etc. all call `db.commit()` for real, unmodified) only
release/re-open a SAVEPOINT — they do NOT commit the outer transaction. At
teardown, the outer transaction is always rolled back, so nothing written by
any test is ever permanently persisted to the developer's real `qfinance`
database, regardless of how many times application code itself calls commit()
during the test. This lets tests exercise the actual, unmodified service/router
commit behavior rather than needing every service function to be rewritten to
accept an externally-managed session.

This intentionally uses the SAME `DATABASE_URL` as development (there is no
separate test database configured anywhere in this project — confirmed by
searching for `.env*`/`conftest.py`/`TEST_DATABASE_URL` before writing this
file: none exist). If a separate test database is ever provisioned, set the
`TEST_DATABASE_URL` environment variable and this file will use it instead —
supported below without requiring this file to change again.

Redis isolation: `REDIS_URL` is forced to logical DB 15 (`.../15`) BEFORE any
`app.*` module is imported, because `session_store.py` and `token_store.py`
each create their Redis client at MODULE IMPORT TIME from a cached
`get_settings()` call — overriding `REDIS_URL` after import would have no
effect on those already-created clients. DB 15 is flushed before and after
every test. This never touches whatever the developer's real dev Redis (DB 0,
the application's actual default) has in it — confirmed by reading
`core/config.py`'s default (`redis://localhost:6379/0`) before choosing 15.
If Redis is unreachable, that is a genuine, real failure this file does not
hide — tests will fail with a real connection error, not skip silently.

WRITTEN, NOT EXECUTED IN THIS SESSION — no tool available here can reach the
real PostgreSQL/Redis instances the founder's host has. Every fixture below
is designed to be correct against a real SQLAlchemy 2.x/asyncpg/redis-py
stack, but has not itself been run.
"""
import os

# CRITICAL — must happen before any `import app.*` anywhere in this process,
# including via pytest's own test-collection import of test_auth_flows.py.
# pytest imports conftest.py before collecting sibling test files, so this
# line executing first is guaranteed by pytest's own import order, not by
# fixture ordering (fixtures run far too late for this — the module-level
# Redis clients in session_store.py/token_store.py are already constructed
# the moment those modules are first imported, which happens at test-file
# collection time via `from app.modules.auth import service as auth_service`
# inside a test file, well before any fixture executes).
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.main as main_module
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import generate_session_token, hash_password
from app.modules.auth import service as auth_service
from app.modules.auth import token_store
from app.modules.auth.models import User
from app.modules.auth.session_store import _redis as session_redis
from app.modules.auth.session_store import create_session
from app.modules.users.models import Profile

settings = get_settings()
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", settings.DATABASE_URL)


# ---------------------------------------------------------------------------
# Core isolation fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Function-scoped (not session-scoped) engine/connection, deliberately:
    async engines built on asyncpg bind their connections to the event loop
    active when they were created, and pytest-asyncio's default loop handling
    is per-test-function — a session-scoped engine risks a 'bound to a
    different event loop' error on the second test. Function-scoping costs a
    fresh connection per test but avoids that entire class of flakiness."""
    engine = create_async_engine(_TEST_DATABASE_URL)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)

    async def _override_get_db():
        yield session

    main_module.app.dependency_overrides[get_db] = _override_get_db
    try:
        yield session
    finally:
        main_module.app.dependency_overrides.pop(get_db, None)
        await session.close()
        await trans.rollback()  # always rolled back — nothing this test did is kept
        await conn.close()
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _isolated_test_redis():
    """Runs for EVERY test in this directory (autouse), not just auth's —
    flushes only logical DB 15 (see module docstring), never DB 0."""
    await session_redis.flushdb()
    yield
    await session_redis.flushdb()


@pytest_asyncio.fixture
async def client(db_session):
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def no_resend_api_key(monkeypatch):
    """Forces the dev-safe EmailService skip path regardless of what the real
    host's environment/.env might otherwise set — explicit, not relying on
    the ambient default."""
    from app.integrations import email_service
    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", None)


# ---------------------------------------------------------------------------
# User factories — built on the REAL application service functions
# (auth_service.register/login), not hand-rolled SQL, so these fixtures
# exercise the same code path the tests are meant to be testing around,
# per the explicit "do not duplicate implementation logic" instruction.
# ---------------------------------------------------------------------------

class _RegisteredUser:
    """Convenience wrapper carrying both the DB row and the raw password
    (needed for login tests — the real User model only stores the hash)."""
    def __init__(self, user: User, raw_password: str):
        self.user = user
        self.id = user.id
        self.email = user.email
        self.raw_password = raw_password

    def __getattr__(self, name):
        return getattr(self.user, name)


async def _make_user(db_session, *, email=None, password="a-strong-enough-password",
                      name="Test User", username=None) -> _RegisteredUser:
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    username = username or f"user_{uuid.uuid4().hex[:12]}"
    user = await auth_service.register(db_session, email=email, password=password, name=name, username=username)
    return _RegisteredUser(user, password)


@pytest_asyncio.fixture
async def existing_user(db_session) -> _RegisteredUser:
    return await _make_user(db_session)


@pytest_asyncio.fixture
async def existing_user_profile(db_session, existing_user) -> Profile:
    return await db_session.get(Profile, existing_user.id)


@pytest_asyncio.fixture
async def target_user(db_session) -> _RegisteredUser:
    """Separate fixture name from `existing_user` purely for test readability
    in the password-reset tests (`target_user` reads more naturally as 'the
    account being reset' than 'existing_user' does) — same factory underneath."""
    return await _make_user(db_session)


@pytest_asyncio.fixture
async def suspended_user(db_session) -> _RegisteredUser:
    ru = await _make_user(db_session)
    ru.user.status = "suspended"
    await db_session.flush()
    return ru


@pytest_asyncio.fixture
async def unverified_user_with_token(db_session, existing_user) -> _RegisteredUser:
    """Adds a real, valid verification token (via the actual token_store
    function, not a hand-built Redis key) for `existing_user`, who is
    unverified by default straight out of registration."""
    token = await token_store.create_verification_token(existing_user.id)
    existing_user.token = token
    return existing_user


@pytest_asyncio.fixture
async def expired_verification_token(db_session, existing_user) -> str:
    """A REAL token that has REALLY expired via Redis TTL — not merely a
    fabricated/never-existed string (that scenario is already covered by
    test_verification_rejects_invalid_token). Bypasses token_store's normal
    24h TTL with an intentionally tiny one, then waits it out for real."""
    raw_token = "expired-" + uuid.uuid4().hex
    await session_redis.set(f"qf:verify_email:{raw_token}", str(existing_user.id), px=50)
    await asyncio.sleep(0.15)
    return raw_token


@pytest_asyncio.fixture
async def valid_reset_token(db_session, target_user) -> str:
    return await token_store.create_password_reset_token(target_user.id)


@pytest_asyncio.fixture
async def expired_reset_token(db_session, target_user) -> str:
    raw_token = "expired-" + uuid.uuid4().hex
    await session_redis.set(f"qf:password_reset:{raw_token}", str(target_user.id), px=50)
    await asyncio.sleep(0.15)
    return raw_token


@pytest_asyncio.fixture
async def target_user_two_active_sessions(db_session, target_user):
    """Two independent, real Redis-backed session tokens for the SAME user —
    simulates two devices — via the actual `create_session()` function, then
    exposes each as a raw `Cookie` header dict so the shared `client` fixture
    (a single AsyncClient/cookie-jar) can present either one explicitly on a
    per-request basis, since the test needs to check both independently
    rather than having them overwrite each other in one shared cookie jar."""
    token_a = await create_session(target_user.id)
    token_b = await create_session(target_user.id)
    headers_a = {"Cookie": f"{settings.SESSION_COOKIE_NAME}={token_a}"}
    headers_b = {"Cookie": f"{settings.SESSION_COOKIE_NAME}={token_b}"}
    return headers_a, headers_b
