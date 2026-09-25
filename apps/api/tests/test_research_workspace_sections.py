"""Research Workspace — real, executable integration tests proving the
workspace's free-text section fields (business_model, competitive_position,
financial_snapshot, catalysts, valuation_range, bull_case/base_case/bear_case,
risk_register, invalidation_conditions, and — added in the
Research-Section-completion pass, see alembic/versions/
0007_research_management_and_assumptions.py — management_notes,
assumptions_outlook) can genuinely be persisted and retrieved through the
EXISTING `PATCH`/`GET /research/{id}` endpoints. The two newest fields are a
genuinely new, additive-only schema change (documented in that migration);
every other field already existed before this pass.

Unlike `test_research_integration.py` (still all `@pytest.mark.skip`,
referencing fixtures that don't exist anywhere in the real `conftest.py`),
this file uses ONLY the real fixtures that actually exist (`db_session`,
`client`, `existing_user`, `target_user`) and is NOT skip-marked.

CSRF/AUTH FIX (this pass): a real, executed pytest run against this file
showed every mutating call failing `CSRF_MISMATCH` (403) at
core/deps.py::require_csrf. Root cause was actually two stacked gaps, not
one:
  1. No test here ever authenticated the shared `client` at all before
     calling `_create_research()` — no login, no session cookie, nothing.
  2. Even where a login DID happen (`test_non_author_cannot_patch_another_
     users_research`'s explicit `/auth/login` call for `target_user`), the
     CSRF cookie that login sets was never re-sent as the required
     `X-CSRF-Token` HEADER on the following mutating request — cookies and
     headers are deliberately two different channels in a double-submit
     CSRF scheme (core/deps.py::require_csrf checks that the HEADER value
     matches the COOKIE value; the cookie alone, even though httpx's client
     jar sends it automatically, is not sufficient by itself).
Fixed by adding `_login_and_csrf_header()` below, which performs a REAL
`POST /auth/login` (the actual production code path that issues both
cookies — auth/router.py::login) and returns the CSRF value as a header
dict ready to spread into any mutating call. GET calls need nothing further
since the shared `client`'s cookie jar already carries both cookies
automatically after login. No auth/CSRF *application* semantics were
touched — only how these tests obtain and present credentials.

STATUS: WRITTEN. NOT executed against this real repository/database in this
session — no execution access to the real host. The CSRF/auth fix above is
based on a real, pasted pytest failure from an execution the user performed
themselves; the fix itself has not been re-run by me. Do not treat as
passing until the user re-runs it.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import get_settings
from app.modules.companies.models import Company

settings = get_settings()


async def _verify_email(db_session, registered_user) -> None:
    """`require_verified_profile` (research create/patch's actual auth gate)
    requires `email_verified_at IS NOT NULL`. `existing_user`/`target_user`
    register via the real `auth_service.register()`, which creates an
    unverified user by design (AUTH-001) — this helper marks it verified
    directly on the already-loaded ORM object sharing this test's
    `db_session`, rather than re-implementing the verify-email token flow
    (already covered by test_auth_flows.py)."""
    registered_user.user.email_verified_at = datetime.now(timezone.utc)
    await db_session.flush()


async def _make_company(db_session) -> Company:
    company = Company(id=uuid.uuid4(), name="Test Co", exchange="NSE")
    db_session.add(company)
    await db_session.flush()
    return company


async def _login_and_csrf_header(client, email: str, password: str) -> dict:
    """Real POST /auth/login — sets `qf_session` + the CSRF cookie onto this
    test's shared `client` jar automatically (both Set-Cookie values from
    auth/router.py::login are captured by httpx's AsyncClient on its own).
    GET calls on this same client need nothing further. Mutating calls
    (POST/PATCH/DELETE) still need the CSRF value re-sent as a HEADER
    (core/deps.py::require_csrf — double-submit; the cookie alone never
    satisfies it, by design), which is what this returns, ready to spread
    into any mutating call's `headers=`."""
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"test helper's own login failed: {resp.text}"
    csrf = client.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf, "login did not set a CSRF cookie — a real contract change, not a test bug"
    return {"X-CSRF-Token": csrf}


async def _create_research(client, company_id, headers) -> str:
    resp = await client.post("/api/v1/research", json={
        "company_id": str(company_id), "research_type": "deep_dive",
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_verified_user_can_create_and_retrieve_own_research(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    research_id = await _create_research(client, company.id, headers)

    resp = await client.get(f"/api/v1/research/{research_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


async def test_unverified_user_cannot_create_research(client, db_session, existing_user):
    """Deliberately does NOT call _verify_email — logging in still succeeds
    (auth_service.login() has no verified-email check; only require_
    verified_profile, on the research-create route itself, does), so this
    now correctly exercises the intended 403 (unverified) rather than an
    incidental 403 (CSRF), which is what the un-fixed helper produced
    before this pass regardless of which reason the test's docstring/name
    actually meant to cover."""
    company = await _make_company(db_session)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    resp = await client.post("/api/v1/research", json={
        "company_id": str(company.id), "research_type": "deep_dive",
    }, headers=headers)
    assert resp.status_code == 403


async def test_non_author_cannot_patch_another_users_research(client, db_session, existing_user, target_user):
    await _verify_email(db_session, existing_user)
    await _verify_email(db_session, target_user)
    company = await _make_company(db_session)

    owner_headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    research_id = await _create_research(client, company.id, owner_headers)

    # Logging in as target_user refreshes the SAME shared client's cookie
    # jar to target_user's session — this is the actual identity the next
    # request authenticates as; owner_headers above is now stale for auth
    # purposes (its Cookie header was never re-sent here, only used for the
    # create call above), which is exactly what this test needs to exercise.
    other_headers = await _login_and_csrf_header(client, target_user.email, target_user.raw_password)

    resp = await client.patch(f"/api/v1/research/{research_id}", json={
        "business_model": "Attempted takeover of someone else's research.",
    }, headers=other_headers)
    assert resp.status_code == 403


@pytest.mark.parametrize("field,value", [
    ("business_model", "Sells B2B SaaS via annual subscriptions."),
    ("competitive_position", "Differentiated by switching costs; three major competitors."),
    ("financial_snapshot", "Revenue +18% YoY, operating margin expanded 200bps."),
    ("catalysts", "New product line launching Q2; potential market share gain."),
    ("valuation_range", "18-22x forward earnings, based on peer comparables."),
    ("risk_register", "Customer concentration: top 3 clients are 40% of revenue."),
    ("invalidation_conditions", "Revenue growth falling below 10% for two consecutive quarters."),
    ("management_notes", "Founder-CEO, 12% insider ownership, no recent insider selling."),
    ("assumptions_outlook", "Assumes gross margin holds above 40% through FY27."),
])
async def test_patch_and_get_round_trip_for_each_section_field(
    client, db_session, existing_user, field, value,
):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    research_id = await _create_research(client, company.id, headers)

    patch_resp = await client.patch(f"/api/v1/research/{research_id}", json={field: value}, headers=headers)
    assert patch_resp.status_code == 200, patch_resp.text

    get_resp = await client.get(f"/api/v1/research/{research_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()[field] == value


async def test_bull_base_bear_all_three_persist_independently(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    research_id = await _create_research(client, company.id, headers)

    resp = await client.patch(f"/api/v1/research/{research_id}", json={
        "bull_case": "Margin expansion continues, multiple re-rates upward.",
        "base_case": "Steady growth in line with the last 3 years.",
        "bear_case": "Competitive pressure compresses margins.",
    }, headers=headers)
    assert resp.status_code == 200

    get_resp = await client.get(f"/api/v1/research/{research_id}")
    body = get_resp.json()
    assert body["bull_case"] == "Margin expansion continues, multiple re-rates upward."
    assert body["base_case"] == "Steady growth in line with the last 3 years."
    assert body["bear_case"] == "Competitive pressure compresses margins."


async def test_patching_one_field_does_not_clear_another(client, db_session, existing_user):
    """Direct regression test for the exact bug class Phase 2A's 'partial
    PATCH' contract exists to prevent — saving Section 02 must not silently
    blank out Section 10's already-saved content."""
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    research_id = await _create_research(client, company.id, headers)

    await client.patch(f"/api/v1/research/{research_id}", json={"risk_register": "Regulatory risk noted."}, headers=headers)
    await client.patch(f"/api/v1/research/{research_id}", json={"business_model": "Sells hardware."}, headers=headers)

    get_resp = await client.get(f"/api/v1/research/{research_id}")
    body = get_resp.json()
    assert body["risk_register"] == "Regulatory risk noted."
    assert body["business_model"] == "Sells hardware."


async def test_empty_string_is_a_valid_persisted_value_not_ignored(client, db_session, existing_user):
    """Guards against a subtle real bug: if the service layer ever treated
    `""` as `None`/`not provided` (falsy-check instead of `is not None`),
    a user clearing a section's content would silently fail to save the
    clear."""
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    research_id = await _create_research(client, company.id, headers)

    await client.patch(f"/api/v1/research/{research_id}", json={"catalysts": "Initial growth driver note."}, headers=headers)
    clear_resp = await client.patch(f"/api/v1/research/{research_id}", json={"catalysts": ""}, headers=headers)
    assert clear_resp.status_code == 200

    get_resp = await client.get(f"/api/v1/research/{research_id}")
    assert get_resp.json()["catalysts"] == ""
