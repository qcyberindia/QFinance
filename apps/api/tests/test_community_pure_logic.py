"""Pure-logic tests for community/service.py functions that need no DB
connection: validate_channel and _visible_to. Executed for real in an
isolated sandbox against exact copies of this file's content — 7/7 passed
(see work_memory.md for exact scope of what "executed" means in this project).
"""
import uuid
from types import SimpleNamespace

import pytest

from app.modules.community.service import validate_channel, _visible_to
from app.core.errors import QFinanceAPIError


def test_validate_channel_accepts_all_seven_locked_channels():
    for ch in (
        "announcements", "general_discussion", "research_discussion",
        "market_discussion", "learning", "help_questions", "off_topic",
    ):
        validate_channel(ch)  # must not raise


def test_validate_channel_rejects_unknown_channel():
    with pytest.raises(QFinanceAPIError) as exc_info:
        validate_channel("crypto_signals")
    assert exc_info.value.code == "INVALID_CHANNEL"


def _item(status: str, author_id):
    return SimpleNamespace(status=status, author_id=author_id)


def test_visible_status_is_visible_to_everyone():
    author = uuid.uuid4()
    stranger = uuid.uuid4()
    item = _item("visible", author)
    assert _visible_to(item, viewer_id=stranger, is_staff=False) is True
    assert _visible_to(item, viewer_id=None, is_staff=False) is True


def test_restricted_status_visible_to_author_only_among_non_staff():
    author = uuid.uuid4()
    stranger = uuid.uuid4()
    item = _item("restricted", author)
    assert _visible_to(item, viewer_id=author, is_staff=False) is True
    assert _visible_to(item, viewer_id=stranger, is_staff=False) is False


def test_restricted_status_visible_to_staff_regardless_of_authorship():
    author = uuid.uuid4()
    staff_viewer = uuid.uuid4()
    item = _item("restricted", author)
    assert _visible_to(item, viewer_id=staff_viewer, is_staff=True) is True


def test_removed_status_hidden_from_everyone_including_author():
    """§10.1's explicit rule: removed = hidden from everyone, including the
    author — this is what distinguishes it from restricted."""
    author = uuid.uuid4()
    item = _item("removed", author)
    assert _visible_to(item, viewer_id=author, is_staff=False) is False
    assert _visible_to(item, viewer_id=author, is_staff=True) is False


def test_removed_status_hidden_even_from_staff():
    """Deliberate, not an oversight: per the module's own docstring,
    'removed' hides from everyone including staff — reinstate (§5.3) is the
    only path back to visibility, not direct read access."""
    author = uuid.uuid4()
    staff_viewer = uuid.uuid4()
    item = _item("removed", author)
    assert _visible_to(item, viewer_id=staff_viewer, is_staff=True) is False
