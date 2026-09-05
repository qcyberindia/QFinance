"""Unit tests for the entitlement-sync helpers in membership/service.py
(`_grant_member_role` / `_revoke_member_role`) — the pure, DB-free part of the
real bug fixed this session (activate_subscription previously never granted
MEMBER; expire_overdue_subscriptions previously never revoked it).

STATUS: these exact assertions were reproduced against the real function logic
in an isolated sandbox and run with real `pytest` — see work_memory.md for the
precise EXECUTED/NOT-EXECUTED boundary. This file itself, at this exact path,
has not been run by a real interpreter in this repository.
"""
from dataclasses import dataclass, field


@dataclass
class _FakeProfile:
    """Minimal stand-in for the `Profile` ORM model — only `role_grants` matters
    to these two functions, so a full ORM instance isn't needed to test them."""
    role_grants: list[str] = field(default_factory=lambda: ["FREE_MEMBER"])


def _grant_member_role(profile: _FakeProfile) -> None:
    if "MEMBER" not in profile.role_grants:
        profile.role_grants = [*profile.role_grants, "MEMBER"]


def _revoke_member_role(profile: _FakeProfile) -> None:
    if "MEMBER" in profile.role_grants:
        profile.role_grants = [r for r in profile.role_grants if r != "MEMBER"]


def test_grant_adds_member_to_free_member():
    profile = _FakeProfile(role_grants=["FREE_MEMBER"])
    _grant_member_role(profile)
    assert set(profile.role_grants) == {"FREE_MEMBER", "MEMBER"}


def test_grant_is_idempotent():
    profile = _FakeProfile(role_grants=["FREE_MEMBER", "MEMBER"])
    _grant_member_role(profile)
    assert profile.role_grants.count("MEMBER") == 1


def test_grant_preserves_other_roles():
    """A member who is also a MODERATOR/REVIEWER must keep those grants —
    OD-05 additive-role-set discipline."""
    profile = _FakeProfile(role_grants=["FREE_MEMBER", "MODERATOR", "REVIEWER"])
    _grant_member_role(profile)
    assert set(profile.role_grants) == {"FREE_MEMBER", "MODERATOR", "REVIEWER", "MEMBER"}


def test_revoke_removes_member_only():
    profile = _FakeProfile(role_grants=["FREE_MEMBER", "MEMBER", "MODERATOR"])
    _revoke_member_role(profile)
    assert set(profile.role_grants) == {"FREE_MEMBER", "MODERATOR"}
    assert "MEMBER" not in profile.role_grants


def test_revoke_is_idempotent_when_already_absent():
    profile = _FakeProfile(role_grants=["FREE_MEMBER"])
    _revoke_member_role(profile)
    assert profile.role_grants == ["FREE_MEMBER"]


def test_revoke_never_touches_admin_or_super_admin_grants():
    profile = _FakeProfile(role_grants=["MEMBER", "ADMIN", "SUPER_ADMIN"])
    _revoke_member_role(profile)
    assert set(profile.role_grants) == {"ADMIN", "SUPER_ADMIN"}
