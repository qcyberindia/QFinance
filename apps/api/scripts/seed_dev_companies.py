"""DEVELOPMENT ONLY — small reference seed for the Company Registry.

This is NOT the production data path. Production/real coverage comes from
`scripts/import_nse_companies.py` loading an official NSE security-master
file. This seed exists only so a fresh local database has a handful of real,
well-known NSE-listed companies to select in the Research -> Start Research
-> Stock flow before you have downloaded the real file.

It deliberately REUSES the importer's upsert (`upsert_records`) rather than
carrying its own copy of the logic, so the two mechanisms share one identity
rule — (exchange, symbol) — and can be run in any order, any number of times,
without creating duplicates. (The previous version of this script matched on
(name, exchange); an official import matching on (exchange, symbol) could
then have created a second row for the same company.)

Static identity fields only: name, symbol, exchange, and a broad sector/
industry label. NO prices, NO financials, NO market data. The sector/industry
labels below are broad public classifications written from general
knowledge, not read from an authoritative feed — treat them as placeholders
for development. Because the importer only fills NULL optional fields and
never overwrites, a later official import that supplies sector/industry will
not clobber these, and these will not clobber an already-populated value.

USAGE (from apps/api):
    ./.venv/bin/python scripts/seed_dev_companies.py
"""
import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import AsyncSessionLocal  # noqa: E402
from scripts.import_nse_companies import CompanyRecord, upsert_records  # noqa: E402

# symbol, name, sector, industry — real NSE-listed companies (exchange = NSE).
_DEV_SEED = [
    ("RELIANCE", "Reliance Industries Limited", "Energy", "Oil, Gas & Consumable Fuels / Retail / Telecom"),
    ("TCS", "Tata Consultancy Services Limited", "Information Technology", "IT Services & Consulting"),
    ("HDFCBANK", "HDFC Bank Limited", "Financial Services", "Private Sector Bank"),
    ("INFY", "Infosys Limited", "Information Technology", "IT Services & Consulting"),
    ("ICICIBANK", "ICICI Bank Limited", "Financial Services", "Private Sector Bank"),
    ("SBIN", "State Bank of India", "Financial Services", "Public Sector Bank"),
    ("TATAMOTORS", "Tata Motors Limited", "Automobile", "Automobiles"),
    ("TATAPOWER", "Tata Power Company Limited", "Utilities", "Power Generation & Distribution"),
    ("BHARTIARTL", "Bharti Airtel Limited", "Telecommunication", "Telecom Services"),
    ("ITC", "ITC Limited", "Fast Moving Consumer Goods", "Diversified FMCG"),
    ("LT", "Larsen & Toubro Limited", "Construction", "Diversified Engineering & Construction"),
    ("HINDUNILVR", "Hindustan Unilever Limited", "Fast Moving Consumer Goods", "Diversified FMCG"),
    ("WIPRO", "Wipro Limited", "Information Technology", "IT Services & Consulting"),
]

DEV_SEED_RECORDS = [
    CompanyRecord(name=name, symbol=symbol, exchange="NSE", sector=sector, industry=industry)
    for symbol, name, sector, industry in _DEV_SEED
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        stats = await upsert_records(db, DEV_SEED_RECORDS)
        await db.commit()
    print("DEVELOPMENT ONLY seed (not production data).")
    print(stats.report())


if __name__ == "__main__":
    asyncio.run(seed())
