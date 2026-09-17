"""DB-free regression tests proving the public-profile real-name/email/
private-data leak (PRD V2 §4.7) cannot recur.

Per explicit review feedback on an earlier version of this file: source-text
matching (`inspect.getsource()` scanning for column names) was replaced with
a genuine BEHAVIORAL test — a real FastAPI request through the actual router,
against a fake database session engineered to simulate the exact regression
scenario (a row that DOES carry real-name-shaped data), asserting the actual
HTTP JSON response cannot contain it. This tests the real last line of
defense (`response_model=PublicProfileResponse` filtering at serialization
time), not today's query text, which could drift without this test noticing.

STATUS: see work_memory.md for the exact EXECUTED/NOT-EXECUTED boundary —
genuinely run in an isolated sandbox, not the real host (no real Postgres/git
execution access exists in any tool available in this session).
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.modules.profile.schemas import PublicProfileResponse

FORBIDDEN_FIELD_NAMES = {
    "name", "full_name", "real_name", "display_name", "email",
    "journal", "journal_entries", "draft", "drafts",
    "broker", "access_token", "kite_user_id", "broker_connection",
    "portfolio", "holdings", "positions",
    "saved", "saved_posts", "bookmarks",
}


# ---------------------------------------------------------------------------
# Schema-level tests — unchanged, still valid: these assert the actual HTTP
# response contract, since FastAPI serializes strictly against this model.
# ---------------------------------------------------------------------------

def test_public_profile_response_schema_has_no_forbidden_fields():
    field_names = set(PublicProfileResponse.model_fields.keys())
    leaked = field_names & FORBIDDEN_FIELD_NAMES
    assert not leaked, f"PublicProfileResponse exposes forbidden field(s): {leaked}"


def test_public_profile_response_schema_only_has_expected_public_fields():
    allowed = {"username", "bio", "published_posts_count", "published_theses_count",
               "contribution_points", "recent_posts"}
    field_names = set(PublicProfileResponse.model_fields.keys())
    assert field_names == allowed, (
        f"PublicProfileResponse fields changed: expected exactly {allowed}, got {field_names}. "
        "If this is an intentional new public field, update this test's allow-list deliberately."
    )


# ---------------------------------------------------------------------------
# Behavioral test — a real HTTP request through the real router, against a
# fake DB session engineered to return real-name-shaped data, proving the
# response_model boundary actually strips it even if the query regressed.
# ---------------------------------------------------------------------------

class _FakeResult:
    """Mimics the subset of SQLAlchemy's Result object profile/service.py
    actually calls: .first(), .scalar_one(), .all()."""
    def __init__(self, first=None, scalar=None, all_rows=None):
        self._first, self._scalar, self._all = first, scalar, all_rows or []

    def first(self):
        return self._first

    def scalar_one(self):
        return self._scalar

    def all(self):
        return self._all


class _FakeDB:
    """A fake AsyncSession whose .execute() returns, in order, results for:
    (1) the profiles lookup — engineered to carry a `.name` attribute the
        real query does NOT select today, simulating exactly the regression
        this test exists to catch: if a future change re-adds `name` to the
        SELECT list, this fake row would carry it through, and this test
        proves the HTTP response still could not leak it;
    (2) published_posts_count, (3) published_theses_count,
    (4) contribution_points, (5) recent_posts.
    """
    def __init__(self):
        self._call_index = 0

    async def execute(self, *args, **kwargs):
        self._call_index += 1
        if self._call_index == 1:
            # Simulates a regressed query that (hypothetically) also selected
            # `name` — the row object below deliberately HAS a `.name`
            # attribute with a real-looking value, exactly what a real
            # SQLAlchemy Row would carry if `SELECT user_id, bio, name` were
            # ever reintroduced.
            fake_row = SimpleNamespace(
                user_id=uuid.uuid4(), bio="Long-term investor.", name="Priya Sharma (REAL NAME)",
            )
            return _FakeResult(first=fake_row)
        if self._call_index in (2, 3):
            return _FakeResult(scalar=3)
        if self._call_index == 4:
            return _FakeResult(scalar=42)
        return _FakeResult(all_rows=[
            SimpleNamespace(id=uuid.uuid4(), post_type="thesis", content="Why I own X.",
                             created_at=datetime.now(timezone.utc)),
        ])


@pytest.fixture
def profile_app():
    """Builds a minimal, real FastAPI app containing ONLY the real
    profile.router — not the full application graph (which needs Postgres/
    Redis dependencies this sandbox doesn't have) — with get_db overridden to
    yield the fake DB above. This is a real ASGI app and a real HTTP request
    cycle, not a direct Python function call, so it genuinely exercises
    FastAPI's response_model serialization step."""
    from fastapi import FastAPI

    from app.core.db import get_db
    from app.modules.profile.router import router as profile_router

    app = FastAPI()
    app.include_router(profile_router, prefix="/api/v1")

    async def _fake_get_db():
        yield _FakeDB()

    app.dependency_overrides[get_db] = _fake_get_db
    return app


def test_public_profile_http_response_cannot_leak_real_name_even_if_row_has_it(profile_app):
    """THE behavioral regression test: even when the underlying (fake) DB row
    carries a real-name-shaped attribute — simulating a future regressed
    query — the actual serialized HTTP JSON response must not contain it."""
    client = TestClient(profile_app)
    resp = client.get("/api/v1/profile/investor_4821")

    assert resp.status_code == 200
    body = resp.json()

    assert "name" not in body
    assert "email" not in body
    assert "Priya Sharma" not in resp.text  # the real name never appears anywhere in the raw response text either
    assert body["username"] == "investor_4821"
    assert body["bio"] == "Long-term investor."
