"""Company Master import + company search/retrieval + Research selection.

Pure-logic tests (parse / normalize / validate / filter / dedupe) need no
database. DB-backed tests use the existing `db_session` / `client` fixtures.
Every DB fixture uses a random token in names AND symbols, so nothing here can
collide with real rows that may already exist in the dev database (e.g. seeded
TCS / INFY), and searches are scoped to that token.

Company schema facts these tests are written against (read from
companies/models.py, not assumed): `name` NOT NULL, `exchange` NOT NULL and
CHECK-limited to NSE/BSE/OTHER_RECOGNIZED, `symbol`/`sector`/`industry`/
`description`/`website` nullable, no DB-level unique constraint on
(exchange, symbol) — which is exactly why idempotency is tested at the
importer level.

Already covered elsewhere and deliberately not duplicated here:
tests/test_research_subject_context.py — valid company accepted, unknown and
merged company rejected, GET /research/{id} returns company context, optional
company fields may be NULL, no author identity leakage.
"""
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.modules.companies.models import Company
from app.modules.companies.schemas import CompanyResponse
from scripts.import_nse_companies import (
    CompanyRecord, ImportFormatError, build_records, map_headers, read_rows, upsert_records,
)

settings = get_settings()


def _tok() -> str:
    return uuid.uuid4().hex[:8].upper()


# ---------------------------------------------------------------------------
# 1. Import validation / normalization / filtering / duplicates (pure logic)
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    "SYMBOL,NAME OF COMPANY, SERIES\n"
    "GOOD1,Good One Limited,EQ\n"
    ",No Symbol Limited,EQ\n"
    "NONAME,,EQ\n"
    "BAD!!,Bad Symbol Limited,EQ\n"
    "M&M,Mahindra & Mahindra Limited,EQ\n"
    "BAJAJ-AUTO,Bajaj Auto Limited,EQ\n"
    "GOOD1,Good One Duplicate Limited,EQ\n"
    "WARR1,Some Warrant,W\n"
)


def test_import_validation_counts_add_up_and_bad_rows_are_rejected(tmp_path):
    f = tmp_path / "master.csv"
    f.write_text(SAMPLE_CSV, encoding="utf-8")
    records, stats = build_records(read_rows(f), default_exchange="NSE", series_filter=("EQ", "BE"))

    assert stats.source_rows == 8
    assert stats.filtered_out == 1          # series "W" is not EQ/BE
    assert stats.invalid == 3               # missing symbol, missing name, malformed symbol
    assert stats.duplicates == 1            # GOOD1 repeated
    assert stats.valid_rows == 3
    assert stats.source_rows == stats.filtered_out + stats.invalid + stats.duplicates + stats.valid_rows
    assert {r.symbol for r in records} == {"GOOD1", "M&M", "BAJAJ-AUTO"}  # & and - are legal in NSE symbols
    assert all(r.exchange == "NSE" for r in records)
    assert stats.invalid_examples  # reported, so a bad file is diagnosable


def test_first_occurrence_wins_for_duplicate_symbols(tmp_path):
    f = tmp_path / "master.csv"
    f.write_text(SAMPLE_CSV, encoding="utf-8")
    records, _ = build_records(read_rows(f), default_exchange="NSE", series_filter=("EQ", "BE"))
    good1 = next(r for r in records if r.symbol == "GOOD1")
    assert good1.name == "Good One Limited"


def test_normalization_trims_whitespace_and_uppercases_symbol_and_exchange(tmp_path):
    f = tmp_path / "master.csv"
    f.write_text("SYMBOL,NAME OF COMPANY,EXCHANGE\n  tcs  ,  Tata   Consultancy\t Services  Ltd ,  nse \n", encoding="utf-8")
    records, stats = build_records(read_rows(f), default_exchange="BSE", series_filter=None)
    assert stats.valid_rows == 1
    assert records[0] == CompanyRecord(name="Tata Consultancy Services Ltd", symbol="TCS", exchange="NSE")


def test_exchange_column_is_validated_and_default_exchange_applies_when_absent(tmp_path):
    f = tmp_path / "master.csv"
    f.write_text("SYMBOL,NAME OF COMPANY,EXCHANGE\nAAA,Alpha Limited,nse\nBBB,Beta Limited,NASDAQ\n", encoding="utf-8")
    records, stats = build_records(read_rows(f), default_exchange="NSE", series_filter=None)
    assert [r.symbol for r in records] == ["AAA"]
    assert stats.invalid == 1

    g = tmp_path / "noex.csv"
    g.write_text("SYMBOL,NAME OF COMPANY\nCCC,Gamma Limited\n", encoding="utf-8")
    records, _ = build_records(read_rows(g), default_exchange="nse", series_filter=None)
    assert records[0].exchange == "NSE"


def test_series_filter_all_keeps_everything(tmp_path):
    f = tmp_path / "master.csv"
    f.write_text("SYMBOL,NAME OF COMPANY,SERIES\nAAA,Alpha Limited,EQ\nBBB,Beta Limited,SM\nCCC,Gamma Limited,N1\n", encoding="utf-8")
    _, default_stats = build_records(read_rows(f), default_exchange="NSE", series_filter=("EQ", "BE"))
    assert default_stats.valid_rows == 1 and default_stats.filtered_out == 2
    _, all_stats = build_records(read_rows(f), default_exchange="NSE", series_filter=None)
    assert all_stats.valid_rows == 3 and all_stats.filtered_out == 0


def test_missing_optional_columns_leave_sector_industry_description_null(tmp_path):
    f = tmp_path / "master.csv"
    f.write_text("SYMBOL,NAME OF COMPANY\nAAA,Alpha Limited\n", encoding="utf-8")
    records, _ = build_records(read_rows(f), default_exchange="NSE", series_filter=None)
    assert (records[0].sector, records[0].industry, records[0].description) == (None, None, None)


def test_utf8_bom_and_json_sources_are_supported(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_bytes(b"\xef\xbb\xbf" + b"SYMBOL,NAME OF COMPANY\nAAA,Alpha Limited\n")
    records, _ = build_records(read_rows(bom), default_exchange="NSE", series_filter=None)
    assert records[0].symbol == "AAA"

    js = tmp_path / "master.json"
    js.write_text(json.dumps([{"Symbol": "BBB", "Name of Company": "Beta Limited", "Series": "EQ"}]), encoding="utf-8")
    records, _ = build_records(read_rows(js), default_exchange="NSE", series_filter=("EQ",))
    assert records[0].symbol == "BBB"


def test_unrecognised_headers_fail_loudly_and_show_what_was_found():
    with pytest.raises(ImportFormatError) as exc:
        map_headers(["foo", "bar"])
    assert "foo" in str(exc.value) and "bar" in str(exc.value)


# ---------------------------------------------------------------------------
# 2/3. Idempotent, duplicate-safe upsert into the EXISTING companies table
# ---------------------------------------------------------------------------

async def _count(db, **filters) -> int:
    stmt = select(func.count()).select_from(Company)
    for k, v in filters.items():
        stmt = stmt.where(getattr(Company, k) == v)
    return (await db.execute(stmt)).scalar_one()


async def test_upsert_inserts_then_second_run_changes_nothing(db_session):
    t = _tok()
    records = [
        CompanyRecord(name=f"Zzq{t} Alpha Limited", symbol=f"ZA{t}", exchange="NSE"),
        CompanyRecord(name=f"Zzq{t} Beta Limited", symbol=f"ZB{t}", exchange="NSE"),
    ]
    first = await upsert_records(db_session, records)
    assert (first.inserted, first.updated, first.unchanged) == (2, 0, 0)

    second = await upsert_records(db_session, records)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 2)  # idempotent

    assert await _count(db_session, symbol=f"ZA{t}") == 1
    assert await _count(db_session, symbol=f"ZB{t}") == 1


async def test_official_name_replaces_existing_name_for_same_symbol(db_session):
    t = _tok()
    db_session.add(Company(id=uuid.uuid4(), name=f"Zzq{t} Old Name", symbol=f"ZN{t}", exchange="NSE"))
    await db_session.flush()

    stats = await upsert_records(db_session, [CompanyRecord(name=f"Zzq{t} Official Name Ltd", symbol=f"ZN{t}", exchange="NSE")])
    assert (stats.inserted, stats.updated) == (0, 1)
    row = (await db_session.execute(select(Company).where(Company.symbol == f"ZN{t}"))).scalar_one()
    assert row.name == f"Zzq{t} Official Name Ltd"


async def test_legacy_row_without_symbol_is_adopted_not_duplicated(db_session):
    """Rows created before the `symbol` column existed (e.g. the old dev seed)
    have symbol NULL; the import must adopt them, not add a second row."""
    t = _tok()
    db_session.add(Company(id=uuid.uuid4(), name=f"Zzq{t} Legacy Limited", symbol=None, exchange="NSE", sector="Utilities"))
    await db_session.flush()

    stats = await upsert_records(db_session, [CompanyRecord(name=f"zzq{t} legacy limited", symbol=f"ZL{t}", exchange="NSE")])
    assert (stats.inserted, stats.updated) == (0, 1)
    rows = (await db_session.execute(select(Company).where(Company.name.ilike(f"zzq{t} legacy%")))).scalars().all()
    assert len(rows) == 1
    assert rows[0].symbol == f"ZL{t}"
    assert rows[0].sector == "Utilities"  # untouched


async def test_optional_fields_only_fill_nulls_and_never_overwrite_or_null(db_session):
    t = _tok()
    db_session.add(Company(id=uuid.uuid4(), name=f"Zzq{t} Fill Limited", symbol=f"ZF{t}", exchange="NSE",
                           sector="Utilities", industry=None, description=None))
    await db_session.flush()

    # Source disagrees on sector (must NOT overwrite), supplies industry (fills NULL), supplies no description.
    stats = await upsert_records(db_session, [CompanyRecord(
        name=f"Zzq{t} Fill Limited", symbol=f"ZF{t}", exchange="NSE", sector="Something Else", industry="Power",
    )])
    assert stats.updated == 1
    row = (await db_session.execute(select(Company).where(Company.symbol == f"ZF{t}"))).scalar_one()
    assert (row.sector, row.industry, row.description) == ("Utilities", "Power", None)

    # A later source with NO sector/industry must never null out existing values.
    await upsert_records(db_session, [CompanyRecord(name=f"Zzq{t} Fill Limited", symbol=f"ZF{t}", exchange="NSE")])
    await db_session.refresh(row)
    assert (row.sector, row.industry) == ("Utilities", "Power")


async def test_admin_merged_company_is_respected_and_left_alone(db_session):
    t = _tok()
    target = Company(id=uuid.uuid4(), name=f"Zzq{t} Target Limited", symbol=f"ZT{t}", exchange="NSE")
    db_session.add(target)
    await db_session.flush()
    merged = Company(id=uuid.uuid4(), name=f"Zzq{t} Merged Old Limited", symbol=f"ZM{t}", exchange="NSE", is_merged_into=target.id)
    db_session.add(merged)
    await db_session.flush()

    stats = await upsert_records(db_session, [CompanyRecord(name=f"Zzq{t} Renamed Limited", symbol=f"ZM{t}", exchange="NSE")])
    assert (stats.inserted, stats.updated, stats.skipped_merged) == (0, 0, 1)
    await db_session.refresh(merged)
    assert merged.name == f"Zzq{t} Merged Old Limited"  # not renamed, not resurrected as a new live row
    assert await _count(db_session, symbol=f"ZM{t}") == 1


# ---------------------------------------------------------------------------
# 4/5/10. Company search + retrieval through the EXISTING API; no leakage
# ---------------------------------------------------------------------------

async def _seed_search_fixture(db_session, t: str) -> dict:
    power = Company(id=uuid.uuid4(), name=f"Zzq{t} Power Company Limited", symbol=f"ZP{t}", exchange="NSE",
                    sector="Utilities", industry="Power")
    consult = Company(id=uuid.uuid4(), name=f"Zzq{t} Consultancy Services Limited", symbol=f"ZC{t}", exchange="NSE")
    ticker_only = Company(id=uuid.uuid4(), name="Completely Unrelated Name Limited", symbol=f"QQ{t}", exchange="NSE")
    for c in (power, consult, ticker_only):
        db_session.add(c)
    await db_session.flush()
    return {"power": power, "consult": consult, "ticker_only": ticker_only}


async def test_search_by_name_returns_real_rows_with_symbol_and_exchange(client, db_session):
    t = _tok()
    rows = await _seed_search_fixture(db_session, t)
    resp = await client.get(f"/api/v1/companies?search=zzq{t.lower()}")  # also proves case-insensitivity
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    names = [i["name"] for i in body["items"]]
    assert names == sorted(names)  # deterministic ordering by name
    by_id = {i["id"]: i for i in body["items"]}
    power = by_id[str(rows["power"].id)]
    assert (power["symbol"], power["exchange"]) == (f"ZP{t}", "NSE")


async def test_search_matches_symbol_even_when_name_does_not_contain_it(client, db_session):
    t = _tok()
    rows = await _seed_search_fixture(db_session, t)
    resp = await client.get(f"/api/v1/companies?search=QQ{t}")
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()["items"]] == [str(rows["ticker_only"].id)]


async def test_search_with_no_match_returns_empty_list_not_an_error(client):
    resp = await client.get(f"/api/v1/companies?search=nothing-matches-{_tok()}")
    assert resp.status_code == 200
    assert resp.json()["items"] == [] and resp.json()["total"] == 0


async def test_page_size_is_bounded(client):
    assert (await client.get("/api/v1/companies?page_size=101")).status_code == 422


async def test_merged_companies_are_excluded_from_search(client, db_session):
    t = _tok()
    target = Company(id=uuid.uuid4(), name=f"Zzq{t} Live Limited", symbol=f"ZV{t}", exchange="NSE")
    db_session.add(target)
    await db_session.flush()
    db_session.add(Company(id=uuid.uuid4(), name=f"Zzq{t} Archived Limited", symbol=f"ZX{t}", exchange="NSE", is_merged_into=target.id))
    await db_session.flush()
    resp = await client.get(f"/api/v1/companies?search=zzq{t.lower()}")
    assert [i["id"] for i in resp.json()["items"]] == [str(target.id)]


async def test_get_company_by_id_and_unknown_id(client, db_session):
    t = _tok()
    rows = await _seed_search_fixture(db_session, t)
    ok = await client.get(f"/api/v1/companies/{rows['power'].id}")
    assert ok.status_code == 200
    assert ok.json()["symbol"] == f"ZP{t}"
    assert (await client.get(f"/api/v1/companies/{uuid.uuid4()}")).status_code == 404


async def test_company_api_exposes_only_public_registry_fields(client, db_session):
    t = _tok()
    await _seed_search_fixture(db_session, t)
    resp = await client.get(f"/api/v1/companies?search=zzq{t.lower()}")
    allowed = set(CompanyResponse.model_fields)
    for item in resp.json()["items"]:
        assert set(item) <= allowed
        assert not any(bad in k.lower() for k in item for bad in ("email", "password", "token", "secret", "key"))
    # The registry stores identity only — no market or financial fields exist to leak.
    assert not any(k in allowed for k in ("price", "market_cap", "revenue", "eps", "pe"))


# ---------------------------------------------------------------------------
# 6. Import -> search -> select -> Start Research -> workspace context
# ---------------------------------------------------------------------------

async def test_imported_company_can_be_selected_for_research_and_is_returned_with_context(client, db_session, existing_user):
    t = _tok()
    await upsert_records(db_session, [CompanyRecord(name=f"Zzq{t} Power Company Limited", symbol=f"ZP{t}", exchange="NSE")])

    # exactly what the picker does: search the backend, take the real id from the result
    found = (await client.get(f"/api/v1/companies?search=zzq{t.lower()}")).json()["items"]
    assert len(found) == 1
    company_id = found[0]["id"]

    existing_user.user.email_verified_at = datetime.now(timezone.utc)
    await db_session.flush()
    login = await client.post("/api/v1/auth/login", json={"email": existing_user.email, "password": existing_user.raw_password})
    assert login.status_code == 200, login.text
    headers = {"X-CSRF-Token": client.cookies.get(settings.CSRF_COOKIE_NAME)}

    question = "How does this company's business mix affect its long-term growth?"
    created = await client.post("/api/v1/research", json={
        "company_id": company_id, "research_type": "deep_dive", "title": question, "summary": question,
    }, headers=headers)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]

    for _ in range(2):  # second GET stands in for a browser refresh
        body = (await client.get(f"/api/v1/research/{rid}")).json()
        assert body["company_id"] == company_id
        assert body["summary"] == question
        assert (body["company"]["name"], body["company"]["symbol"], body["company"]["exchange"]) == (
            f"Zzq{t} Power Company Limited", f"ZP{t}", "NSE")
        assert body["company"]["sector"] is None and body["company"]["industry"] is None  # source had none: NULL, not invented
