"""Company Master importer — loads a LOCAL exchange security-master file into
the EXISTING `companies` table (the Qfinera Company Registry).

PURPOSE / BOUNDARY: `companies` only identifies a company (name, symbol,
exchange, and sector/industry/description when a source reliably provides
them). It is NOT a market-data or financial-data store — this script never
writes prices, market cap, financials, or news, and there is no column for
them. ISIN is deliberately not stored: `companies` has no ISIN column, and
adding one needs a migration, which is out of scope for this task.

SOURCE: designed for NSE's official "All EQUITIES" list (EQUITY_L.csv,
published by NSE; series `EQ` = common stock per NSE's own data
documentation). The script takes a LOCAL FILE on purpose: the application
never depends on an external website at runtime and this script never
scrapes one — download the file yourself from NSE, then point --file at it.
Header matching is alias-based (see HEADER_ALIASES) because I could not
verify the exact header row of a real file in the session that wrote this;
if name/symbol columns cannot be identified the script stops and prints the
headers it actually found rather than guessing.

USAGE (from apps/api):
    ./.venv/bin/python scripts/import_nse_companies.py --file /path/EQUITY_L.csv
    ./.venv/bin/python -m scripts.import_nse_companies --file /path/EQUITY_L.csv --dry-run

  --exchange NSE        exchange to assign when the file has no exchange column
  --series EQ,BE        series to keep (default EQ,BE); "ALL" disables the filter
  --dry-run             do everything, print the report, then roll back

IDEMPOTENT: identity is (exchange, symbol). Re-running never creates a
duplicate. Existing rows are matched, in order, by (exchange, symbol), then
by (exchange, case-insensitive name) among rows whose symbol is still NULL
(adopts legacy rows created before the symbol column existed, e.g. from the
older dev seed). NEVER deletes. Rows archived by an admin merge
(`is_merged_into`) are respected and left alone. Optional fields
(sector/industry/description) are only ever FILLED when the row's value is
NULL — an existing value is never overwritten and never nulled.

NOTE: `companies` has no DB-level unique constraint on (exchange, symbol),
so uniqueness is enforced here in application logic. Two importers running
concurrently could still race; run one at a time.

WRITTEN. Pure logic is covered by tests/test_company_master_import.py.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    # Allow `python scripts/import_nse_companies.py` (not just `-m`): put
    # apps/api on sys.path so `app.*` imports resolve.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.modules.companies.models import Company  # noqa: E402
from app.modules.companies.schemas import VALID_EXCHANGES  # noqa: E402

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name of company", "name of the company", "company name", "security name", "company", "name"),
    "symbol": ("symbol", "trading symbol", "ticker", "scrip", "scrip symbol"),
    "series": ("series",),
    "exchange": ("exchange",),
    "sector": ("sector",),
    "industry": ("industry",),
    "description": ("description",),
}

DEFAULT_SERIES = ("EQ", "BE")
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-_.]*$")  # NSE symbols include & and - (e.g. M&M, BAJAJ-AUTO)
MAX_NAME_LEN = 300
MAX_SYMBOL_LEN = 40


class ImportFormatError(Exception):
    """The file could not be understood at all (e.g. no recognisable name/symbol columns)."""


@dataclass(frozen=True)
class CompanyRecord:
    name: str
    symbol: str
    exchange: str
    sector: str | None = None
    industry: str | None = None
    description: str | None = None


@dataclass
class ImportStats:
    source_rows: int = 0
    filtered_out: int = 0  # dropped by --series (not an error)
    invalid: int = 0
    duplicates: int = 0  # repeated (exchange, symbol) inside the source file
    valid_rows: int = 0  # unique, valid, in-scope records handed to the upsert
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_merged: int = 0  # matched an admin-merged (archived) company — left alone
    db_duplicates: int = 0  # pre-existing DB rows already sharing (exchange, symbol) — warning only
    invalid_examples: list[str] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return self.unchanged + self.skipped_merged + self.filtered_out

    def report(self) -> str:
        lines = [
            f"source rows        : {self.source_rows}",
            f"filtered (series)  : {self.filtered_out}",
            f"invalid            : {self.invalid}",
            f"duplicates in file : {self.duplicates}",
            f"valid rows         : {self.valid_rows}",
            f"inserted           : {self.inserted}",
            f"updated            : {self.updated}",
            f"skipped            : {self.skipped} "
            f"(unchanged {self.unchanged}, merged/archived {self.skipped_merged}, filtered {self.filtered_out})",
        ]
        if self.db_duplicates:
            lines.append(f"WARNING            : {self.db_duplicates} pre-existing DB rows share an (exchange, symbol); "
                         f"first-created row was used")
        for ex in self.invalid_examples[:5]:
            lines.append(f"  invalid example  : {ex}")
        return "\n".join(lines)


# ----------------------------------------------------------------------------
# Pure logic — no database, no network
# ----------------------------------------------------------------------------

def _norm_header(h: str) -> str:
    return re.sub(r"[\s_]+", " ", (h or "").strip().lower())


def normalize_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def normalize_symbol(value: str | None) -> str:
    return normalize_whitespace(value).upper()


def normalize_exchange(value: str | None) -> str:
    return normalize_whitespace(value).upper()


def map_headers(headers: list[str]) -> dict[str, str]:
    """canonical field -> the file's actual header. Raises ImportFormatError if
    name or symbol cannot be identified (the file is not what we think it is)."""
    normalized = {_norm_header(h): h for h in headers}
    mapping: dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canonical] = normalized[alias]
                break
    missing = [f for f in ("name", "symbol") if f not in mapping]
    if missing:
        raise ImportFormatError(
            f"Could not identify required column(s) {missing}. Headers found in the file: {headers}"
        )
    return mapping


def read_rows(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise ImportFormatError("JSON source must be a list of objects.")
        return [{str(k): "" if v is None else str(v) for k, v in row.items()} for row in data]
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ImportFormatError("File has no header row.")
        return [dict(row) for row in reader]


def build_records(
    rows: list[dict[str, str]], *, default_exchange: str, series_filter: tuple[str, ...] | None,
) -> tuple[list[CompanyRecord], ImportStats]:
    """Normalize -> validate -> filter -> dedupe. Pure: no I/O."""
    stats = ImportStats(source_rows=len(rows))
    if not rows:
        return [], stats
    mapping = map_headers(list(rows[0].keys()))
    default_ex = normalize_exchange(default_exchange)
    seen: set[tuple[str, str]] = set()
    records: list[CompanyRecord] = []

    for idx, row in enumerate(rows, start=2):  # start=2: header is line 1
        def get(field_name: str) -> str:
            col = mapping.get(field_name)
            return normalize_whitespace(row.get(col)) if col else ""

        if series_filter is not None and "series" in mapping:
            if get("series").upper() not in series_filter:
                stats.filtered_out += 1
                continue

        name, symbol = get("name"), normalize_symbol(get("symbol"))
        exchange = normalize_exchange(get("exchange")) or default_ex

        problem = None
        if not name:
            problem = "missing name"
        elif len(name) > MAX_NAME_LEN:
            problem = f"name longer than {MAX_NAME_LEN} chars"
        elif not symbol:
            problem = "missing symbol"
        elif len(symbol) > MAX_SYMBOL_LEN or not SYMBOL_RE.match(symbol):
            problem = f"malformed symbol {symbol!r}"
        elif exchange not in VALID_EXCHANGES:
            problem = f"exchange {exchange!r} not one of {sorted(VALID_EXCHANGES)}"
        if problem:
            stats.invalid += 1
            if len(stats.invalid_examples) < 5:
                stats.invalid_examples.append(f"line {idx}: {problem}")
            continue

        key = (exchange, symbol)
        if key in seen:
            stats.duplicates += 1
            continue
        seen.add(key)
        records.append(CompanyRecord(
            name=name, symbol=symbol, exchange=exchange,
            sector=get("sector") or None, industry=get("industry") or None,
            description=get("description") or None,
        ))

    stats.valid_rows = len(records)
    return records, stats


# ----------------------------------------------------------------------------
# Database upsert — flushes only; the caller owns commit/rollback
# ----------------------------------------------------------------------------

async def upsert_records(db, records: list[CompanyRecord], stats: ImportStats | None = None) -> ImportStats:
    """Upsert into the existing `companies` table. Never deletes. Flushes but
    does NOT commit (caller decides — enables --dry-run and test isolation)."""
    stats = stats or ImportStats(valid_rows=len(records))
    if not records:
        return stats

    exchanges = {r.exchange for r in records}
    existing = (await db.execute(
        select(Company).where(Company.exchange.in_(exchanges), Company.deleted_at.is_(None))
        .order_by(Company.created_at, Company.id)
    )).scalars().all()

    by_symbol: dict[tuple[str, str], Company] = {}
    legacy_by_name: dict[tuple[str, str], Company] = {}  # symbol still NULL
    for c in existing:
        if c.symbol:
            key = (c.exchange, c.symbol.strip().upper())
            if key in by_symbol:
                stats.db_duplicates += 1  # keep the first-created row
            else:
                by_symbol[key] = c
        else:
            legacy_by_name.setdefault((c.exchange, normalize_whitespace(c.name).lower()), c)

    for rec in records:
        row = by_symbol.get((rec.exchange, rec.symbol))
        if row is None:
            legacy = legacy_by_name.get((rec.exchange, rec.name.lower()))
            if legacy is not None:
                row = legacy
                row.symbol = rec.symbol  # adopt a pre-symbol-column row instead of duplicating it
                legacy_by_name.pop((rec.exchange, rec.name.lower()), None)
                by_symbol[(rec.exchange, rec.symbol)] = row
                stats.updated += 1
                _fill_optional(row, rec)
                continue

        if row is None:
            new_row = Company(
                id=uuid.uuid4(), name=rec.name, symbol=rec.symbol, exchange=rec.exchange,
                sector=rec.sector, industry=rec.industry, description=rec.description,
            )
            db.add(new_row)
            by_symbol[(rec.exchange, rec.symbol)] = new_row
            stats.inserted += 1
            continue

        if row.is_merged_into is not None:
            stats.skipped_merged += 1
            continue

        changed = False
        if row.name != rec.name:  # exchange-official name is authoritative for name
            row.name = rec.name
            changed = True
        changed = _fill_optional(row, rec) or changed
        if changed:
            stats.updated += 1
        else:
            stats.unchanged += 1

    await db.flush()
    return stats


def _fill_optional(row: Company, rec: CompanyRecord) -> bool:
    """Fill sector/industry/description ONLY when the row's value is NULL."""
    changed = False
    for attr in ("sector", "industry", "description"):
        incoming = getattr(rec, attr)
        if incoming and not getattr(row, attr):
            setattr(row, attr, incoming)
            changed = True
    return changed


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _parse_series(value: str) -> tuple[str, ...] | None:
    if value.strip().upper() == "ALL":
        return None
    return tuple(s.strip().upper() for s in value.split(",") if s.strip())


async def run(path: Path, *, exchange: str, series: tuple[str, ...] | None, dry_run: bool) -> ImportStats:
    from app.core.db import AsyncSessionLocal  # imported lazily: pure-logic users never need a DB

    rows = read_rows(path)
    records, stats = build_records(rows, default_exchange=exchange, series_filter=series)
    async with AsyncSessionLocal() as db:
        await upsert_records(db, records, stats)
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a local exchange company-master file into `companies`.")
    parser.add_argument("--file", required=True, type=Path, help="local CSV (or JSON list) source file")
    parser.add_argument("--exchange", default="NSE", help="exchange when the file has no exchange column (default NSE)")
    parser.add_argument("--series", default=",".join(DEFAULT_SERIES),
                        help='comma-separated series to keep (default "EQ,BE"; "ALL" disables filtering)')
    parser.add_argument("--dry-run", action="store_true", help="run everything, print report, roll back")
    args = parser.parse_args(argv)

    if not args.file.is_file():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 2
    try:
        stats = asyncio.run(run(args.file, exchange=args.exchange, series=_parse_series(args.series),
                                dry_run=args.dry_run))
    except ImportFormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(("DRY RUN (rolled back)\n" if args.dry_run else "") + stats.report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
