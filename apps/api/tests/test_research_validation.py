"""Unit tests for the pure publish-validation function (no DB required).

STATUS: these specific assertions were actually executed against real Python
in an isolated sandbox during this session (a byte-for-byte copy of
validation.py's logic, not this exact file/path, since the sandbox has no
access to this real project). They passed. Re-running `pytest
apps/api/tests/test_research_validation.py` against this actual file, in this
actual repository, with the actual project's dependencies installed, has NOT
been done — see work_memory.md for the precise distinction. This file itself
has not been syntax-checked by a real interpreter in this exact location.
"""
import datetime

from app.modules.research.validation import PublishCandidate, validate_publish_readiness


def _valid_candidate(**overrides) -> PublishCandidate:
    base = dict(
        title="Reliance Q3 Supply Chain Review",
        summary="A short summary.",
        bear_case="Detailed bear case text.",
        conflict_disclosed=True,
        position_disclosed=False,
        research_date=datetime.date(2026, 8, 29),
        source_count=1,
    )
    base.update(overrides)
    return PublishCandidate(**base)


def test_fully_valid_candidate_has_no_errors():
    assert validate_publish_readiness(_valid_candidate()) == {}


def test_all_fields_missing_reports_all_seven():
    candidate = PublishCandidate(
        title=None, summary=None, bear_case=None,
        conflict_disclosed=None, position_disclosed=None, research_date=None, source_count=0,
    )
    errors = validate_publish_readiness(candidate)
    assert set(errors.keys()) == {
        "title", "summary", "bear_case", "sources", "conflict_disclosed", "position_disclosed", "research_date",
    }


def test_placeholder_title_and_empty_summary_rejected():
    candidate = _valid_candidate(title="Untitled research", summary="")
    errors = validate_publish_readiness(candidate)
    assert "title" in errors
    assert "summary" in errors


def test_explicit_false_disclosure_is_not_an_error():
    """SRC-004 — an explicit 'No' must be treated as answered, not missing."""
    candidate = _valid_candidate(conflict_disclosed=False, position_disclosed=False)
    errors = validate_publish_readiness(candidate)
    assert "conflict_disclosed" not in errors
    assert "position_disclosed" not in errors


def test_whitespace_only_bear_case_rejected():
    candidate = _valid_candidate(bear_case="   ")
    errors = validate_publish_readiness(candidate)
    assert "bear_case" in errors


def test_zero_sources_rejected():
    candidate = _valid_candidate(source_count=0)
    errors = validate_publish_readiness(candidate)
    assert "sources" in errors


def test_reports_all_failures_at_once_not_just_first():
    """API Spec §7.3.1: 'names every missing requirement at once, not just
    the first one found' — a single failing candidate with 3 problems must
    surface all 3, not stop at the first."""
    candidate = _valid_candidate(bear_case=None, source_count=0, research_date=None)
    errors = validate_publish_readiness(candidate)
    assert set(errors.keys()) == {"bear_case", "sources", "research_date"}
