"""Tests for the three Research contract fixes (2026-09-01):
  A. FTS query construction (build_research_search_sql) — pure, no DB needed.
  B. include_moderated authorization gating — pure boolean logic, no DB needed.
  C. Library/search response shape (author/company nesting) is exercised
     indirectly via _library_item/_preview_item's dict shape, without a DB,
     by checking the functions build the expected keys from a stub object.

STATUS: these exact assertions were actually executed against real Python in
an isolated sandbox during this session (byte-for-byte copies of
service.py/models.py's logic in this file's exact form, not this file at
this exact path, since the sandbox has no access to this real project). All
21 tests in the sandbox's tests/ directory (this file's tests plus
test_research_validation.py) passed. Re-running
`pytest apps/api/tests/test_research_search_and_moderation.py` against this
actual file, in this actual repository, with this project's actual
dependencies installed, has NOT been done — see work_memory.md for the exact
scope of "executed" vs "written". No real PostgreSQL/Redis is reachable in
either environment, so nothing requiring a live DB is exercised here — those
paths remain in test_research_integration.py, still skip-marked.
"""
import uuid
from datetime import datetime, timezone

from app.modules.research.service import _preview_item, build_research_search_sql
from app.modules.research.models import Research


# ---------------------------------------------------------------------------
# A. FTS query construction
# ---------------------------------------------------------------------------

def test_search_sql_uses_tsvector_on_title_and_business_model():
    sql = build_research_search_sql("SELECT r.id")
    assert "to_tsvector('english', coalesce(r.title, '') || ' ' || coalesce(r.business_model, ''))" in sql
    assert "plainto_tsquery('english', :q)" in sql


def test_search_sql_uses_tsvector_on_company_name():
    sql = build_research_search_sql("SELECT r.id")
    assert "to_tsvector('english', c.name) @@ plainto_tsquery('english', :q)" in sql


def test_search_sql_tag_matching_is_ilike_not_tsvector():
    """No FTS index exists for research_tags in any locked document — tag
    matching must stay a direct ILIKE, not a tsvector expression."""
    sql = build_research_search_sql("SELECT r.id")
    assert "rt.tag ILIKE :like_q" in sql
    tag_clause_start = sql.index("rt.tag")
    assert "to_tsvector" not in sql[max(0, tag_clause_start - 20):tag_clause_start]


def test_search_sql_default_filters_to_active_moderation_status():
    sql = build_research_search_sql("SELECT r.id")
    assert "r.moderation_status = 'active'" in sql


def test_search_sql_include_moderated_drops_the_moderation_filter():
    sql = build_research_search_sql("SELECT r.id", include_moderated=True)
    assert "r.moderation_status = 'active'" not in sql
    # Published-only filter must remain even with include_moderated=True —
    # this flag only relaxes the moderation dimension, never the publish gate.
    assert "r.status = 'published'" in sql


def test_search_sql_always_filters_to_published_status():
    for flag in (True, False):
        sql = build_research_search_sql("SELECT r.id", include_moderated=flag)
        assert "r.status = 'published'" in sql


def test_search_sql_select_clause_is_injected_verbatim():
    sql = build_research_search_sql("SELECT COUNT(DISTINCT r.id)")
    assert sql.startswith("SELECT COUNT(DISTINCT r.id) FROM research r")


# ---------------------------------------------------------------------------
# B. include_moderated authorization gating (the exact rule used in both
#    list_library and search_research: `include_moderated and is_staff`)
# ---------------------------------------------------------------------------

def _effective_include_moderated(include_moderated: bool, is_staff: bool) -> bool:
    """Mirrors the exact expression in service.py's list_library/search_research
    so the authorization truth table can be verified in isolation."""
    return include_moderated and is_staff


def test_non_staff_flag_has_no_effect():
    assert _effective_include_moderated(include_moderated=True, is_staff=False) is False


def test_staff_without_flag_gets_default_filtered_view():
    assert _effective_include_moderated(include_moderated=False, is_staff=True) is False


def test_staff_with_flag_gets_moderated_content_included():
    assert _effective_include_moderated(include_moderated=True, is_staff=True) is True


def test_neither_flag_nor_staff_is_false():
    assert _effective_include_moderated(include_moderated=False, is_staff=False) is False


def test_ordinary_member_cannot_bypass_moderation_via_query_string():
    """Direct regression test for the exact concern raised: a non-staff caller
    passing ?include_moderated=true in the query string must not see
    restricted/removed research. Simulated by constructing the SQL with the
    *effective* (gated) flag, never the raw client-supplied one."""
    raw_client_flag = True  # what an ordinary member could put in the query string
    is_staff = False
    effective = _effective_include_moderated(raw_client_flag, is_staff)
    sql = build_research_search_sql("SELECT r.id", include_moderated=effective)
    assert "r.moderation_status = 'active'" in sql  # filter still applied


# ---------------------------------------------------------------------------
# C. Library/search response shape — nested author/company objects
# ---------------------------------------------------------------------------

def _make_research_stub(**overrides) -> Research:
    r = Research(
        id=uuid.uuid4(), author_id=uuid.uuid4(), company_id=uuid.uuid4(),
        research_type="deep_dive", status="published", moderation_status="active",
        access_tier="core", title="A title", summary="A summary", current_version=1,
    )
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


def test_preview_item_nests_author_object_not_flat_id():
    r = _make_research_stub()
    author = {"id": str(r.author_id), "name": "Ananya K.", "username": "ananya_k"}
    item = _preview_item(r, author)
    assert item["author"] == author
    assert "author_id" not in item


def test_preview_item_marks_preview_true_and_core_tier():
    r = _make_research_stub()
    item = _preview_item(r, {"id": str(r.author_id), "name": None, "username": None})
    assert item["preview"] is True
    assert item["access_tier"] == "core"
