"""Research Subject / AI Context / Initial Brief — pure-logic + integration
tests, using the real fixtures established by `test_research_workspace_sections.py`.

Consolidated in this pass: there is now ONE context builder
(`app.modules.research.ai_context`); the earlier duplicate `context.py` was
retired to `context.py.disabled`.

STATUS: WRITTEN, NOT EXECUTED by me (no execution access). Not passing until
you re-run them.
"""
import uuid
from dataclasses import asdict

from app.modules.companies.models import Company
from app.modules.research.ai_context import build_research_ai_context, research_question_of
from app.modules.research.brief import build_initial_brief
from app.modules.research.models import Research
from tests.test_research_workspace_sections import _create_research, _login_and_csrf_header, _make_company, _verify_email

_FULL_COMPANY = {
    "id": "11111111-1111-1111-1111-111111111111", "name": "Tata Power Company Limited",
    "symbol": "TATAPOWER", "exchange": "NSE", "sector": "Utilities",
    "industry": "Power Generation", "description": "An Indian integrated power company.",
}
_SPARSE_COMPANY = {
    "id": "22222222-2222-2222-2222-222222222222", "name": "Newco Ltd",
    "symbol": None, "exchange": None, "sector": None, "industry": None, "description": None,
}


def _bare_research(**overrides) -> Research:
    """A Research ORM instance never added to any session — no DB needed."""
    defaults = dict(
        id=uuid.uuid4(), author_id=uuid.uuid4(), company_id=uuid.UUID(_FULL_COMPANY["id"]),
        research_type="deep_dive", industry=None, status="draft", current_version=0,
        title="Can Tata Power sustain long-term growth without significantly weakening returns?",
        summary="", business_quality=None, financial_snapshot=None, business_model="Sells power via long-term PPAs.",
        competitive_position=None, valuation_range=None, bull_case=None, base_case=None, bear_case=None,
        risk_register="Regulatory tariff risk.", catalysts=None, invalidation_conditions="Tariff cuts of 20%+.",
        management_notes="Diversified promoter group.", assumptions_outlook=None,
        conflict_disclosed=False, conflict_detail=None, position_disclosed=False, position_detail=None,
        research_date=None, published_at=None,
    )
    defaults.update(overrides)
    return Research(**defaults)


# ---------------------------------------------------------------------------
# Pure logic — the single AI context builder
# ---------------------------------------------------------------------------

def test_ai_context_includes_expected_subject_and_stock_fields():
    ctx = asdict(build_research_ai_context(_bare_research(), company=_FULL_COMPANY))
    assert ctx["subject_type"] == "STOCK"
    assert ctx["company_id"] == _FULL_COMPANY["id"]
    assert ctx["company_name"] == "Tata Power Company Limited"
    assert ctx["symbol"] == "TATAPOWER"
    assert ctx["exchange"] == "NSE"
    assert ctx["sector"] == "Utilities"
    assert ctx["industry"] == "Power Generation"
    assert ctx["research_question"] == "Can Tata Power sustain long-term growth without significantly weakening returns?"
    assert ctx["risks"] == "Regulatory tariff risk."
    assert ctx["invalidation_conditions"] == "Tariff cuts of 20%+."
    assert ctx["saved_findings"]["management_notes"] == "Diversified promoter group."
    assert ctx["user_notes"] == []  # no notes model exists; never faked


def test_research_question_prefers_edited_summary_over_creation_title():
    """Regression: Section 01 edits `summary` after creation, so a stale
    `title` must not win over it."""
    r = _bare_research(title="Original question at creation", summary="Refined question after editing Section 01")
    assert research_question_of(r) == "Refined question after editing Section 01"
    assert build_research_ai_context(r, company=_FULL_COMPANY).research_question == "Refined question after editing Section 01"


def test_research_question_falls_back_to_title_when_summary_empty():
    assert research_question_of(_bare_research(title="Only a title", summary="")) == "Only a title"


def test_ai_context_never_contains_api_keys_or_identity_fields():
    """Pins the exact key set so adding author_id/api_key/email fails a test."""
    ctx = asdict(build_research_ai_context(_bare_research(), company=_FULL_COMPANY))
    forbidden = {"api_key", "encrypted_api_key", "email", "username", "author_id",
                 "user_id", "password", "session", "token"}
    assert set(ctx.keys()) & forbidden == set()
    assert set(ctx.keys()) == {
        "research_id", "subject_type", "company_id", "company_name", "symbol", "exchange",
        "sector", "industry", "company_description", "research_question", "current_stage",
        "previous_questions", "saved_findings", "user_notes", "assumptions", "risks",
        "invalidation_conditions",
    }


def test_ai_context_handles_missing_optional_company_fields_without_crashing():
    ctx = build_research_ai_context(
        _bare_research(company_id=uuid.UUID(_SPARSE_COMPANY["id"])), company=_SPARSE_COMPANY,
    )
    assert ctx.symbol is None
    assert ctx.exchange is None
    assert ctx.sector is None


# ---------------------------------------------------------------------------
# Pure logic — Initial Research Brief
# ---------------------------------------------------------------------------

def test_initial_brief_structure_and_content():
    brief = build_initial_brief(company=_FULL_COMPANY, research_question="Can Tata Power sustain long-term growth?")
    assert brief["company"]["name"] == "Tata Power Company Limited"
    assert brief["company"]["symbol"] == "TATAPOWER"
    assert brief["research_question"] == "Can Tata Power sustain long-term growth?"
    assert brief["company_context"]["description"] == _FULL_COMPANY["description"]
    assert brief["data_availability"]["current_market_data"] == "Current information source not connected."
    assert brief["data_availability"]["financial_data"] == "Current information source not connected."


def test_initial_brief_never_fabricates_missing_optional_fields():
    brief = build_initial_brief(company=_SPARSE_COMPANY, research_question="Is Newco a buy?")
    assert brief["company"]["symbol"] is None
    assert brief["company"]["exchange"] is None
    assert brief["company_context"]["description"] is None


# ---------------------------------------------------------------------------
# Integration — Research Subject persistence + GET response shape
# ---------------------------------------------------------------------------

async def test_create_stock_research_with_valid_company_persists_company_id(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    research_id = await _create_research(client, company.id, headers)

    resp = await client.get(f"/api/v1/research/{research_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_id"] == str(company.id)
    assert body["company"]["id"] == str(company.id)


async def test_create_research_with_invalid_company_id_is_rejected(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    resp = await client.post("/api/v1/research", json={
        "company_id": str(uuid.uuid4()), "research_type": "deep_dive",
    }, headers=headers)
    assert resp.status_code == 404


async def test_research_question_persists_as_title(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    question = "Can Tata Power sustain long-term growth without significantly weakening returns?"
    resp = await client.post("/api/v1/research", json={
        "company_id": str(company.id), "research_type": "deep_dive", "title": question, "summary": question,
    }, headers=headers)
    assert resp.status_code == 201
    get_resp = await client.get(f"/api/v1/research/{resp.json()['id']}")
    assert get_resp.json()["title"] == question


async def test_brief_reflects_question_edited_in_section_01(client, db_session, existing_user):
    """Regression for the stale-question bug: Section 01 edits `summary`, and
    the brief must follow it rather than keep showing the creation title."""
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    resp = await client.post("/api/v1/research", json={
        "company_id": str(company.id), "research_type": "deep_dive",
        "title": "Original question", "summary": "Original question",
    }, headers=headers)
    research_id = resp.json()["id"]
    await client.patch(f"/api/v1/research/{research_id}", json={"summary": "Refined question"}, headers=headers)

    body = (await client.get(f"/api/v1/research/{research_id}")).json()
    assert body["brief"]["research_question"] == "Refined question"


async def test_get_research_returns_full_company_context(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = Company(id=uuid.uuid4(), name="Tata Power Company Limited", symbol="TATAPOWER",
                      exchange="NSE", sector="Utilities", industry="Power Generation")
    db_session.add(company)
    await db_session.flush()
    research_id = await _create_research(client, company.id, headers)

    body = (await client.get(f"/api/v1/research/{research_id}")).json()
    assert body["company"]["name"] == "Tata Power Company Limited"
    assert body["company"]["symbol"] == "TATAPOWER"
    assert body["company"]["exchange"] == "NSE"
    assert body["company"]["sector"] == "Utilities"
    assert body["company"]["industry"] == "Power Generation"


async def test_get_research_response_never_leaks_real_identity(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    research_id = await _create_research(client, company.id, headers)

    resp = await client.get(f"/api/v1/research/{research_id}")
    assert existing_user.email not in resp.text
    assert "username" not in resp.json()
    assert "password" not in resp.text.lower()


async def test_missing_optional_company_fields_do_not_break_get_response(client, db_session, existing_user):
    """`exchange` is NOT NULL (CHECK: NSE/BSE/OTHER_RECOGNIZED) so it is always
    supplied; symbol/sector/industry/description are the genuinely optional ones."""
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = Company(id=uuid.uuid4(), name="Bare Minimum Ltd", exchange="NSE")
    db_session.add(company)
    await db_session.flush()
    research_id = await _create_research(client, company.id, headers)

    resp = await client.get(f"/api/v1/research/{research_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["company"]["name"] == "Bare Minimum Ltd"
    assert body["company"]["symbol"] is None
    assert body["brief"]["company"]["symbol"] is None


async def test_workspace_reload_retains_company_and_question(client, db_session, existing_user):
    await _verify_email(db_session, existing_user)
    headers = await _login_and_csrf_header(client, existing_user.email, existing_user.raw_password)
    company = await _make_company(db_session)
    research_id = await _create_research(client, company.id, headers)
    await client.patch(f"/api/v1/research/{research_id}", json={"title": "Can Test Co sustain its moat?"}, headers=headers)

    first = await client.get(f"/api/v1/research/{research_id}")
    second = await client.get(f"/api/v1/research/{research_id}")
    assert first.json()["company_id"] == second.json()["company_id"] == str(company.id)
    assert first.json()["title"] == second.json()["title"] == "Can Test Co sustain its moat?"
