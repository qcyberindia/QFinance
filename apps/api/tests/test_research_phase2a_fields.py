"""Phase 2A — real, DB-backed tests proving the 8 wired field groups
(business_model, competitive_position, financial_snapshot, catalysts,
valuation_range, bull_case/base_case/bear_case, risk_register,
invalidation_conditions) genuinely persist and retrieve through the existing
PATCH/GET /research/{id} endpoints, plus cross-user ownership rejection.

Built on the real conftest.py harness (db_session/client fixtures,
transaction-per-test isolation, real Redis DB 15) — not skip-marked, since
this conftest is a genuine, ready-to-run harness.

STATUS: WRITTEN, NOT EXECUTED IN THIS SESSION.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import get_settings
from app.modules.auth import service as auth_service
from app.modules.companies.models import Company

settings = get_settings()


async def _verified_client_headers(db_session, client, *, email=None, name="Researcher", username=None):
    """Registers a real user via the actual auth_service.register() code path,
    marks them verified directly on the ORM row (no email-token round trip
    needed for this test's purpose), then performs a REAL POST /auth/login.

    CSRF FIX (this pass): this helper previously built a session cookie by
    calling create_session() directly, bypassing the login endpoint
    entirely. That produced a valid SESSION cookie but never set a CSRF
    cookie at all — the real CSRF double-submit cookie (core/security.py::
    generate_csrf_token) is only ever issued inside auth/router.py::login's
    response. Every mutating call in this file's tests then failed
    CSRF_MISMATCH (403) at core/deps.py::require_csrf before ever reaching
    the research endpoint under test (confirmed by a real, executed pytest
    run). Fixed by performing a real login instead — the same code path a
    real client actually uses — and reading both cookies back off the
    shared `client`'s own cookie jar (httpx captures Set-Cookie
    automatically), rather than reconstructing them by hand.
    """
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    username = username or f"researcher_{uuid.uuid4().hex[:12]}"
    password = "a-strong-enough-password"
    user = await auth_service.register(
        db_session, email=email, password=password, name=name, username=username,
    )
    user.email_verified_at = datetime.now(timezone.utc)
    await db_session.flush()

    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200, f"test helper's own login failed: {login_resp.text}"
    session_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
    csrf_cookie = client.cookies.get(settings.CSRF_COOKIE_NAME)
    assert session_cookie and csrf_cookie, "login did not set the expected cookies — a real contract change, not a test bug"

    # A single headers dict, safe to pass to EVERY request type (GET/POST/
    # PATCH) unchanged at every call site below — GET simply ignores the
    # extra X-CSRF-Token header, so no call site needs to branch on method.
    headers = {
        "Cookie": f"{settings.SESSION_COOKIE_NAME}={session_cookie}; {settings.CSRF_COOKIE_NAME}={csrf_cookie}",
        "X-CSRF-Token": csrf_cookie,
    }
    return user, headers


async def _make_company(db_session) -> Company:
    company = Company(id=uuid.uuid4(), name="Test Co", exchange="NSE")
    db_session.add(company)
    await db_session.flush()
    return company


@pytest.mark.asyncio
async def test_all_eight_phase2a_field_groups_persist_and_retrieve(db_session, client):
    """Core Phase 2A contract: PATCH each field, then GET confirms every one
    of the 8 field groups round-trips through the real HTTP layer."""
    user, headers = await _verified_client_headers(db_session, client)
    company = await _make_company(db_session)

    create_resp = await client.post(
        "/api/v1/research", json={"company_id": str(company.id), "research_type": "deep_dive"}, headers=headers,
    )
    assert create_resp.status_code == 201
    research_id = create_resp.json()["id"]

    field_values = {
        "business_model": "Sells enterprise SaaS via annual subscriptions.",
        "competitive_position": "Differentiated by switching costs and integrations.",
        "financial_snapshot": "Revenue +18% YoY, operating margin flat.",
        "catalysts": "New product line launching Q4; expanding into two new markets.",
        "valuation_range": "18-22x forward earnings based on peer comparables.",
        "bull_case": "Margin expansion as new product line scales.",
        "base_case": "Steady 15% revenue growth, flat margins.",
        "bear_case": "Competitive pricing pressure compresses margins.",
        "risk_register": "Customer concentration risk; regulatory risk in core market.",
        "invalidation_conditions": "Revenue growth falls below 8% for two consecutive quarters.",
    }

    patch_resp = await client.patch(f"/api/v1/research/{research_id}", json=field_values, headers=headers)
    assert patch_resp.status_code == 200

    get_resp = await client.get(f"/api/v1/research/{research_id}", headers=headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    for field, expected_value in field_values.items():
        assert body[field] == expected_value, f"{field} did not round-trip correctly"


@pytest.mark.asyncio
async def test_each_field_group_can_also_be_patched_independently(db_session, client):
    """Guards against a regression where only a full-payload PATCH works —
    the real UI saves ONE field at a time, per section, not all 8 at once."""
    user, headers = await _verified_client_headers(db_session, client)
    company = await _make_company(db_session)

    create_resp = await client.post(
        "/api/v1/research", json={"company_id": str(company.id), "research_type": "deep_dive"}, headers=headers,
    )
    research_id = create_resp.json()["id"]

    fields_to_check = [
        "business_model", "competitive_position", "financial_snapshot", "catalysts",
        "valuation_range", "bull_case", "base_case", "bear_case",
        "risk_register", "invalidation_conditions",
    ]
    for field in fields_to_check:
        value = f"Independent update for {field}"
        resp = await client.patch(f"/api/v1/research/{research_id}", json={field: value}, headers=headers)
        assert resp.status_code == 200, f"independent PATCH of {field} failed"

        get_resp = await client.get(f"/api/v1/research/{research_id}", headers=headers)
        assert get_resp.json()[field] == value, f"{field} not persisted after independent PATCH"


@pytest.mark.asyncio
async def test_cross_user_cannot_patch_anothers_draft(db_session, client):
    """Ownership enforcement — a second user attempting to PATCH another's
    draft must be rejected. Uses business_model as the representative field;
    all 8 fields share the identical _require_author dispatch path."""
    owner, owner_headers = await _verified_client_headers(db_session, client, name="Owner")
    other, other_headers = await _verified_client_headers(db_session, client, name="Other")
    company = await _make_company(db_session)

    create_resp = await client.post(
        "/api/v1/research", json={"company_id": str(company.id), "research_type": "deep_dive"}, headers=owner_headers,
    )
    research_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/research/{research_id}", json={"business_model": "Hijacked content"}, headers=other_headers,
    )
    assert resp.status_code == 403

    get_resp = await client.get(f"/api/v1/research/{research_id}", headers=owner_headers)
    assert get_resp.json()["business_model"] != "Hijacked content"


@pytest.mark.asyncio
async def test_cross_user_cannot_view_anothers_private_draft(db_session, client):
    """Ownership boundary applies to reads too — a non-author gets 404 on an
    unpublished draft."""
    owner, owner_headers = await _verified_client_headers(db_session, client, name="Owner")
    other, other_headers = await _verified_client_headers(db_session, client, name="Other")
    company = await _make_company(db_session)

    create_resp = await client.post(
        "/api/v1/research", json={"company_id": str(company.id), "research_type": "deep_dive"}, headers=owner_headers,
    )
    research_id = create_resp.json()["id"]
    await client.patch(f"/api/v1/research/{research_id}", json={"business_model": "Private content"}, headers=owner_headers)

    resp = await client.get(f"/api/v1/research/{research_id}", headers=other_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_empty_and_whitespace_only_fields_persist_exactly_as_sent(db_session, client):
    """Backend-side confirmation of the completeness contract's data
    assumption (frontend logic tested separately in
    lib/research-progress.test.mjs): a field saved as whitespace-only is
    retrievable as such, not silently trimmed/coerced server-side — proving
    the frontend's `.trim().length > 0` completeness check has real,
    correctly-empty data to evaluate."""
    user, headers = await _verified_client_headers(db_session, client)
    company = await _make_company(db_session)

    create_resp = await client.post(
        "/api/v1/research", json={"company_id": str(company.id), "research_type": "deep_dive"}, headers=headers,
    )
    research_id = create_resp.json()["id"]

    await client.patch(f"/api/v1/research/{research_id}", json={"risk_register": "   \n  "}, headers=headers)

    get_resp = await client.get(f"/api/v1/research/{research_id}", headers=headers)
    assert get_resp.json()["risk_register"] == "   \n  "
