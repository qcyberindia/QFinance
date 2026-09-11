"""DB-free unit tests for moderation/service.py's and moderation/models.py's
pure, deterministic pieces — the constant vocabularies and lookup tables that
drive `take_action`'s branching, without needing a database to exercise them.

These import the REAL production objects from `app.modules.moderation.service`
and `app.modules.moderation.models` — not reimplementations. The DB-touching
parts of `take_action`/`create_report`/etc. are NOT covered here; they remain
integration-only (no test_moderation_integration.py exists yet — a genuine
gap, flagged in work_memory.md, not silently covered by this file pretending
to be more than it is).

STATUS: see work_memory.md for the exact EXECUTED/NOT-EXECUTED boundary.
"""
from app.modules.moderation.models import MODERATION_ACTION_TARGET_TYPES, MODERATION_ACTIONS, REPORT_TARGET_TYPES
from app.modules.moderation.service import (
    EDIT_UNSUPPORTED_FOR_TARGET_TYPES,
    VALID_ACTIONS,
    VALID_REPORT_TARGET_TYPES,
    VALID_SEVERITIES,
    _NORMAL_STATE_BY_TARGET_TYPE,
    _RESOLUTION_ACTION_BY_ACTION,
)


# ---------------------------------------------------------------------------
# Vocabulary constants match the locked API Spec §5 / DB Schema CHECK constraints
# ---------------------------------------------------------------------------

def test_valid_actions_match_api_spec_five_client_settable_actions():
    """§5.3's request schema restricts `action` to exactly these 5 —
    'suspend_member'/'reinstate_member' are server-set-only via the separate
    §5.4/§5.5 endpoints, never accepted here."""
    assert set(VALID_ACTIONS) == {"approve", "edit", "restrict", "remove", "reinstate"}


def test_valid_report_target_types_match_reports_table_check_constraint():
    """Must match the exact CHECK constraint on `reports.target_type` in
    0001_initial_schema.py — verified by direct migration inspection before
    writing this test, not assumed."""
    assert set(VALID_REPORT_TARGET_TYPES) == {"post", "comment", "research"}
    assert set(REPORT_TARGET_TYPES) == {"post", "comment", "research"}


def test_moderation_action_target_types_include_member_for_suspend_actions():
    """Unlike `reports.target_type`, `moderation_actions.target_type` also
    permits 'member' — the only target_type used by suspend/reinstate
    member actions, which are never tied to a report."""
    assert set(MODERATION_ACTION_TARGET_TYPES) == {"post", "comment", "research", "member"}


def test_moderation_actions_vocabulary_matches_db_check_constraint_exactly():
    """Must match `ck_mod_actions_action` in the migration exactly — the full
    7-value vocabulary (5 report-tied + 2 member-only), not just the 5 a
    client can request via §5.3."""
    assert set(MODERATION_ACTIONS) == {
        "approve", "edit", "restrict", "remove", "reinstate", "suspend_member", "reinstate_member",
    }


def test_valid_severities_match_moderation_rules_check_constraint():
    assert set(VALID_SEVERITIES) == {"low", "medium", "high"}


# ---------------------------------------------------------------------------
# The reinstate/resolution_action contradiction — direct regression test on
# the exact real dict this module's docstring describes handling it with.
# ---------------------------------------------------------------------------

def test_four_of_five_actions_map_to_a_valid_reports_resolution_action():
    """The 4 actions that ARE representable in reports.resolution_action's
    CHECK constraint must map to exactly the right value."""
    assert _RESOLUTION_ACTION_BY_ACTION["approve"] == "approved"
    assert _RESOLUTION_ACTION_BY_ACTION["edit"] == "edited"
    assert _RESOLUTION_ACTION_BY_ACTION["restrict"] == "restricted"
    assert _RESOLUTION_ACTION_BY_ACTION["remove"] == "removed"


def test_reinstate_is_deliberately_absent_from_the_resolution_action_map():
    """THE regression test for the documented, unresolved spec contradiction:
    'reinstate' has no valid `reports.resolution_action` CHECK-constraint
    value (the constraint only permits approved/edited/restricted/removed/
    member_suspended). `.get('reinstate')` must return None — this is what
    lets `take_action` write `resolution_action = None` instead of either
    crashing on a CHECK violation or silently writing a wrong value like
    'approved'. If this test ever starts failing because someone added a
    'reinstate' entry to this dict, it means either (a) the locked DB Schema
    was amended to add a 'reinstated' CHECK value with founder authorization,
    and this dict was correctly updated to match, or (b) someone tried to
    paper over the contradiction without that authorization — case (b) must
    not happen silently, which is exactly why this test exists."""
    assert "reinstate" not in _RESOLUTION_ACTION_BY_ACTION
    assert _RESOLUTION_ACTION_BY_ACTION.get("reinstate") is None


def test_resolution_action_map_has_no_entry_for_member_only_actions():
    """suspend_member/reinstate_member never go through take_action's
    report-resolution path at all (they're not in VALID_ACTIONS, and are
    handled by the separate suspend_member/reinstate_member service
    functions, which never touch `reports`) — confirming they're absent here
    too, for the same reason as 'reinstate'."""
    assert "suspend_member" not in _RESOLUTION_ACTION_BY_ACTION
    assert "reinstate_member" not in _RESOLUTION_ACTION_BY_ACTION


# ---------------------------------------------------------------------------
# Content-type-specific vocabularies
# ---------------------------------------------------------------------------

def test_normal_state_differs_between_post_comment_and_research():
    """posts/comments use 'visible' as their non-moderated state; research
    uses 'active' — two different vocabularies for the same underlying
    concept, per Architecture §10.1's explicit per-content-type state table.
    A reinstate action must resolve to the CORRECT word for the target type,
    not a single hardcoded value."""
    assert _NORMAL_STATE_BY_TARGET_TYPE["post"] == "visible"
    assert _NORMAL_STATE_BY_TARGET_TYPE["comment"] == "visible"
    assert _NORMAL_STATE_BY_TARGET_TYPE["research"] == "active"


def test_edit_action_unsupported_only_for_research():
    """Research has no single free-text content field analogous to a
    post/comment's `content` column — 'edit' is only meaningful for
    post/comment targets."""
    assert EDIT_UNSUPPORTED_FOR_TARGET_TYPES == ("research",)
    assert "post" not in EDIT_UNSUPPORTED_FOR_TARGET_TYPES
    assert "comment" not in EDIT_UNSUPPORTED_FOR_TARGET_TYPES
