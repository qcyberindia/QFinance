"""Publish-time validation (RES-004/005/006, QRES-003, SRC-001/003, AD-04, AD-17).

Deliberately a pure function with no DB/ORM/FastAPI dependency, per Architecture
Principle 4 ("business logic separable from framework") — this lets the core
compliance rule be unit-tested in complete isolation from a running database,
and is shared verbatim by both `POST /research/{id}/publish` (7.3.1, first
publish or re-publish) and `PATCH /research/{id}` on an already-published item
(7.1.4, AD-17) so the two endpoints cannot silently drift apart.

WRITTEN. Unit-tested directly (see apps/api/tests/test_research_validation.py) —
this specific function, and only this function, has actually been executed
against real Python in this session (see work_memory.md for the exact scope
of what "executed" means here).
"""
from dataclasses import dataclass
from typing import Any

from app.modules.research.models import PLACEHOLDER_SUMMARY, PLACEHOLDER_TITLE


@dataclass
class PublishCandidate:
    """Minimal shape validate_publish_readiness needs — either a real `Research`
    ORM row or a plain proposed-state object (7.1.4 validates a *proposed*
    post-edit state before writing anything, so this intentionally isn't typed
    as the ORM model directly)."""
    title: str | None
    summary: str | None
    bear_case: str | None
    conflict_disclosed: bool | None
    position_disclosed: bool | None
    research_date: Any
    source_count: int


def validate_publish_readiness(candidate: PublishCandidate) -> dict[str, str]:
    """Returns a dict of {field_name: reason} for every failing requirement —
    empty dict means publish-ready. Never returns after the first failure
    (API Spec §7.3.1: "names every missing requirement at once, not just the
    first one found")."""
    errors: dict[str, str] = {}

    if not candidate.title or candidate.title == PLACEHOLDER_TITLE:
        errors["title"] = "required before publish"
    if not candidate.summary or candidate.summary == PLACEHOLDER_SUMMARY:
        errors["summary"] = "required before publish"
    if not candidate.bear_case or not candidate.bear_case.strip():
        errors["bear_case"] = "required before publish"  # QRES-003
    if candidate.source_count < 1:
        errors["sources"] = "at least one source required"  # SRC-001
    if candidate.conflict_disclosed is None:
        errors["conflict_disclosed"] = "must be explicitly answered (Yes/No)"  # SRC-003/004
    if candidate.position_disclosed is None:
        errors["position_disclosed"] = "must be explicitly answered (Yes/No)"  # SRC-003/004
    if candidate.research_date is None:
        errors["research_date"] = "required before publish"

    return errors
