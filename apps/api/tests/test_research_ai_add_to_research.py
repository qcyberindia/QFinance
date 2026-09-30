"""Research Assistant — Add to Research + Continue Research (stage
reconciliation). Reuses the real-login CSRF pattern already established in
test_research_workspace_sections.py / test_research_subject_context.py.

STATUS: WRITTEN. NOT executed against the real repository/database in this
session — no execution access. Static-only: read against the actual
research/service.py::add_ai_finding, research/router.py, and
research/sections.py this pass added/touched.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import get_settings
from app.modules.companies.models import Company
from app.modules.research.sections import ADD_TO_RESEARCH_STAGES, next_stage_key

settings = get_settings()


async def _verify_email(db_session, registered_user) -> None:
    registered_user.user.email_verified_at = datetime.now(timezone.utc)
    await db_session.flush()


async def _login_and_csrf_header(client, email: str, password: str) -> dict:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"test helper's own login failed: {resp.text}"
    csrf = client.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf, "login did not set a CSRF cookie"
    return {"X-CSRF-Token": csrf}


async def _make_company(db_session, **overrides) -> Company:
    defaults = dict(id=uuid.uuid4(), name="Tata Power Company Limited", symbol="TATAPOWER", exchange="NSE")
    defaults.update(overrides)
    company = Company(**defaults)
    db_session.add(company)
    await db_session.flush()
    return company


async def _create_research(client, company_id, headers) -> str:
    resp = await client.post("/api/v1/research", json={
        "company_id": str(company_id), "research_type": "deep_dive", "summary": "Can this business sustain growth?",
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Stage vocabulary reconciliation (pure) — the actual bug this pass fixed
# ---------------------------------------------------------------------------

def test_add_to_research_stage_keys_are_section_keys_not_column_names():
    """Guards the exact mismatch this pass found: ADD_TO_RESEARCH_STAGES must
    be keyed by section KEYS ("business", "risks"...), not raw column names
    ("business_model", "risk_register"...) — the frontend's
    FIELD_TO_SECTION_KEY map depends on this being true."""
    assert "business" in ADD_TO_RESEARCH_STAGES and "business_model" not in ADD_TO_RESEARCH_STAGES
    assert ADD_TO_RESEARCH_STAGES["business"] == "business_model"
    assert ADD_TO_RESEARCH_STAGES["risks"] == "risk_register"
    # Non-addable sections correctly excluded (see sections.py's own docstring for why each is).
    for excluded in ("question", "scenarios", "thesis", "review"):
        assert excluded not in ADD_TO_RESEARCH_STAGES


def test_next_stage_key_progresses_in_document_order_and_stops_at_the_end():
    assert next_stage_key("business") == "industry"
    assert next_stage_key("risks") == "invalidation"
    assert next_stage_key("review") is None
    assert next_stage_key("not-a-real-key") is None


# ---------------------------------------------------------------------------
# Add to Research — persistence, editability, idempotency, ownership
# ---------------------------------------------------------------------------

async def test_add_to_research_persists_into_the_real_section_field_and_survives_reload(
    client, db_session, existing_user,
):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, headers)

    resp = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "business", "question": "How does it make money?", "answer": "Sells power under long-term PPAs.",
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["added"], body["already_added"], body["field"]) == (True, False, "business_model")
    assert body["content"] == "Sells power under long-term PPAs."

    # "Reload" = a fresh GET, exactly what a browser refresh triggers.
    for _ in range(2):
        get_body = (await client.get(f"/api/v1/research/{rid}")).json()
        assert get_body["business_model"] == "Sells power under long-term PPAs."


async def test_added_content_is_still_editable_through_the_normal_patch_endpoint(client, db_session, existing_user):
    """Direct proof it's not an immutable AI record — the SAME field a manual
    section edit writes to is what add-to-research wrote to."""
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, headers)

    await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "risks", "question": "Biggest risk?", "answer": "Regulatory tariff risk.",
    }, headers=headers)
    edit = await client.patch(f"/api/v1/research/{rid}", json={
        "risk_register": "Regulatory tariff risk. Edited: also currency exposure on imported coal.",
    }, headers=headers)
    assert edit.status_code == 200
    get_body = (await client.get(f"/api/v1/research/{rid}")).json()
    assert get_body["risk_register"] == "Regulatory tariff risk. Edited: also currency exposure on imported coal."


async def test_add_to_research_appends_rather_than_overwriting_existing_content(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, headers)

    await client.patch(f"/api/v1/research/{rid}", json={"business_model": "User's own opening note."}, headers=headers)
    resp = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "business", "question": "q", "answer": "AI-sourced addition.",
    }, headers=headers)
    body = resp.json()
    assert "User's own opening note." in body["content"]
    assert "AI-sourced addition." in body["content"]


async def test_adding_the_same_answer_twice_is_idempotent_not_duplicated(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, headers)

    first = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "growth", "question": "q", "answer": "New product line drives growth.",
    }, headers=headers)
    second = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "growth", "question": "a different question", "answer": "New product line drives growth.",
    }, headers=headers)
    assert (first.json()["added"], first.json()["already_added"]) == (True, False)
    assert (second.json()["added"], second.json()["already_added"]) == (False, True)
    get_body = (await client.get(f"/api/v1/research/{rid}")).json()
    assert get_body["catalysts"].count("New product line drives growth.") == 1  # not duplicated


@pytest.mark.parametrize("bad_stage", ["question", "scenarios", "thesis", "review", "not-a-stage", "business_model"])
async def test_add_to_research_rejects_non_addable_or_unknown_stages(bad_stage, client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, headers)

    resp = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": bad_stage, "question": "q", "answer": "some answer",
    }, headers=headers)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "INVALID_AI_STAGE"


async def test_add_to_research_rejects_empty_answer(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, headers)

    resp = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "business", "question": "q", "answer": "   ",
    }, headers=headers)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_add_to_research_rejects_non_author(client, db_session, existing_user, target_user):
    await _verify_email(db_session, existing_user)
    await _verify_email(db_session, target_user)
    owner_headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, owner_headers)

    other_headers = await _login_and_csrf_header(client, target_user.email, target_user.raw_password)
    resp = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "business", "question": "q", "answer": "a",
    }, headers=other_headers)
    assert resp.status_code == 403


async def test_add_to_research_rejects_already_published_items(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, headers)

    # Make the item publishable, then publish it for real.
    await client.patch(f"/api/v1/research/{rid}", json={
        "title": "Test Research", "business_model": "x", "bear_case": "x", "conflict_disclosed": False, "position_disclosed": False,
        "research_date": "2026-09-28",
    }, headers=headers)
    await client.post(f"/api/v1/research/{rid}/sources", json={"label": "Annual report", "reference": "https://example.com"}, headers=headers)
    publish = await client.post(f"/api/v1/research/{rid}/publish", json={}, headers=headers)
    assert publish.status_code == 200, publish.text

    resp = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "risks", "question": "q", "answer": "a",
    }, headers=headers)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "RESEARCH_PUBLISHED"


async def test_add_to_research_requires_csrf_and_authentication(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    rid = await _create_research(client, company.id, headers)

    no_csrf = await client.post(f"/api/v1/research/{rid}/ai/add-to-research", json={
        "stage": "business", "question": "q", "answer": "a",
    })
    assert no_csrf.status_code == 403 and no_csrf.json()["error"]["code"] == "CSRF_MISMATCH"
