"""Initial Research Brief (Research Phase 3) — orientation shown when a
Research Workspace opens, NOT an AI-generated or final investment report;
built purely from already-persisted Company data plus the research
question. No external calls, no live AI, no fabricated fields — anything
Qfinera does not actually have is listed explicitly under
`data_unavailable`, never silently omitted (silently omitting would look
like "there's nothing more to say" rather than "we don't have this yet")."""

# Static company data (name/symbol/exchange/sector/industry/description) is
# genuinely available via the existing Company record. These three are not —
# no live-market-data provider, no news/announcements feed, no financials
# ingestion exists anywhere in this codebase yet (confirmed by inspection,
# not assumed): each maps to one fixed, honest string, not a blank/null that
# a frontend might render as an empty section.
_NOT_CONNECTED = "Current information source not connected."

DATA_UNAVAILABLE_LABELS = {
    "current_market_data": "Current market data",
    "recent_company_information": "Recent company information",
    "financial_data": "Financial data",
}


def build_initial_brief(*, company: dict, research_question: str) -> dict:
    """Pure — no I/O, no DB, no network. `company` is the same dict shape
    `research/service.py::_load_author_and_company` already produces
    (id/name/symbol/exchange/sector/industry/description); missing optional
    fields (symbol/exchange/sector/industry/description all being nullable
    on Company) are passed through as None rather than defaulted to an
    invented value — the frontend is expected to render a None field as
    simply absent from the brief, not as a fabricated placeholder."""
    return {
        "company": {
            "name": company.get("name"),
            "symbol": company.get("symbol"),
            "exchange": company.get("exchange"),
            "sector": company.get("sector"),
            "industry": company.get("industry"),
        },
        "research_question": research_question,
        "company_context": {
            "description": company.get("description"),
        },
        "data_availability": {
            "current_market_data": _NOT_CONNECTED,
            "recent_company_information": _NOT_CONNECTED,
            "financial_data": _NOT_CONNECTED,
        },
    }
