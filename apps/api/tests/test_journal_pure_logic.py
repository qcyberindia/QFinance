"""Real, DB-free tests for journal/service.py's pure validation logic.
STATUS: EXECUTED IN SANDBOX ONLY (6/6 passed, exact copy of this file's
content, isolated container — no real host/Postgres/Redis involved). NOT run
against this actual file/path.
"""
import pytest

from app.modules.journal.service import _validate_content, _validate_entry_type
from app.core.errors import QFinanceAPIError


def test_valid_entry_types_accepted():
    for t in ("decision", "reasoning", "observation", "note"):
        _validate_entry_type(t)  # must not raise


def test_invalid_entry_type_rejected():
    with pytest.raises(QFinanceAPIError) as exc:
        _validate_entry_type("hot_tip")
    assert exc.value.code == "INVALID_ENTRY_TYPE"


def test_empty_content_rejected():
    with pytest.raises(QFinanceAPIError) as exc:
        _validate_content("")
    assert exc.value.code == "VALIDATION_ERROR"


def test_whitespace_only_content_rejected():
    with pytest.raises(QFinanceAPIError):
        _validate_content("   ")


def test_valid_content_accepted():
    _validate_content("Bought 10 shares because of strong Q3 guidance.")  # must not raise


def test_overlong_content_rejected():
    with pytest.raises(QFinanceAPIError) as exc:
        _validate_content("x" * 10001)
    assert exc.value.fields == {"content": "too_long"}
