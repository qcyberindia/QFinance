"""Moderation business logic — API Specification V1 §5 (MOD-001-005),
Architecture §10.1/AD-08, Database Schema V1 §15/§16/§18.
WRITTEN, NOT EXECUTED — no real database has been reached in this session.

GENUINE LOCKED-DOCUMENT CONTRADICTION, NOT SILENTLY RECONCILED (per explicit
instruction): API Specification V1 §5.3 allows `action: "reinstate"` on
`POST /moderation/queue/{report_id}/action` — a report-tied endpoint. But
Database Schema V1 §15's `reports.resolution_action` CHECK constraint only
permits `('approved','edited','restricted','removed','member_suspended')` —
there is no `'reinstated'` value. `moderation_actions.action` (§16), by
contrast, DOES permit `'reinstate'`. This means a `reinstate` action taken
via the queue-action endpoint can be recorded correctly in
`moderation_actions` (the authoritative audit trail, per Architecture §10.1's
own explicit statement that `moderation_actions` — not
`reports.resolution_action` — is "the source of truth") but CANNOT set
`reports.resolution_action` to any value describing what actually happened,
since every value the CHECK constraint permits is wrong for a reinstate.

Resolution taken here, preserving existing locked behavior rather than
guessing which document is "right": for a `reinstate` action, this module
still resolves the report (`status='resolved'`, `resolved_by`, `resolved_at`
are set — the complaint IS handled) but leaves `resolution_action` as `NULL`
rather than writing an inaccurate value or violating the CHECK constraint.
The accurate record of what happened lives in `moderation_actions.action =
'reinstate'`, exactly as Architecture §10.1 says it should for any
discrepancy between the two tables. This is flagged in work_memory.md as an
unresolved specification contradiction requiring a founder decision (either
add `'reinstated'` to the DB CHECK, or clarify that `reinstate` is only ever
meant to be invoked outside the report-resolution flow) — not fixed here by
altering a locked, approved document.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.errors import NotFound, QFinanceAPIError
from app.modules.auth import service as auth_service
from app.modules.community import service as community_service
from app.modules.moderation.models import ModerationAction, ModerationRule, Report
from app.modules.research import service as research_service

VALID_REPORT_TARGET_TYPES = ("post", "comment", "research")
VALID_ACTIONS = ("approve", "edit", "restrict", "remove", "reinstate")

# API Spec §5.3's own error scenario: "if e.g. action='suspend_member' is sent
# with target_type='post'". Given §5.3's request schema restricts `action` to
# the 5-value VALID_ACTIONS set above (never 'suspend_member'/'reinstate_member',
# which are server-set-only on §5.4/§5.5), this specific scenario is currently
# unreachable through the actual request schema — kept here anyway as
# defense-in-depth / future-proofing, per the spec explicitly naming this error
# code as required. All 5 of VALID_ACTIONS currently apply uniformly to all 3
# report target types (post/comment/research) except EDIT_UNSUPPORTED_FOR below.
EDIT_UNSUPPORTED_FOR_TARGET_TYPES = ("research",)

# post/comment "normal" (un-restricted/removed) status value differs from
# research's — see community vs research moderation_status vocabularies.
_NORMAL_STATE_BY_TARGET_TYPE = {"post": "visible", "comment": "visible", "research": "active"}

_RESOLUTION_ACTION_BY_ACTION = {
    "approve": "approved",
    "edit": "edited",
    "restrict": "restricted",
    "remove": "removed",
    # 'reinstate' intentionally absent — see module docstring.
}


async def _load_reporter(db: AsyncSession, reporter_id: uuid.UUID) -> dict:
    row = (await db.execute(
        text("SELECT user_id, name, username FROM profiles WHERE user_id = :uid"), {"uid": str(reporter_id)},
    )).first()
    return ({"id": str(row.user_id), "name": row.name, "username": row.username} if row
            else {"id": str(reporter_id), "name": None, "username": None})


async def _target_exists(db: AsyncSession, *, target_type: str, target_id: uuid.UUID) -> bool:
    """MOD-001 report validation — mirrors the same application-level
    existence check Architecture AD-13 requires for every polymorphic-target
    table in this codebase (reactions, and now reports)."""
    try:
        if target_type == "post":
            await community_service.get_post_or_404(db, target_id)
        elif target_type == "comment":
            await community_service.get_comment_or_404(db, target_id)
        elif target_type == "research":
            await research_service.get_research_or_404(db, target_id)
        else:
            return False
        return True
    except NotFound:
        return False


async def create_report(db: AsyncSession, *, reporter_id: uuid.UUID, target_type: str,
                         target_id: uuid.UUID, reason: str) -> Report:
    """§5.1, MOD-001, COMM-007. No duplicate/spam-prevention rule is
    implemented — neither the PRD nor the API/DB spec defines one (no unique
    constraint on `reports` for reporter+target, unlike e.g. `reactions`'
    explicit `ux_reactions_unique`), so none is invented here per the
    standing 'do not invent behavior' instruction. A member can report the
    same content more than once; each report is queued independently."""
    if target_type not in VALID_REPORT_TARGET_TYPES:
        raise QFinanceAPIError(
            "INVALID_TARGET_TYPE", f"target_type must be one of {VALID_REPORT_TARGET_TYPES}.", 400,
        )
    if not reason or not reason.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "A reason is required.", 400, fields={"reason": "required"})
    if not await _target_exists(db, target_type=target_type, target_id=target_id):
        raise NotFound(f"{target_type.capitalize()} not found.")

    report = Report(
        id=uuid.uuid4(), reporter_id=reporter_id, target_type=target_type,
        target_id=target_id, reason=reason, status="open",
    )
    db.add(report)
    await db.commit()
    return report


async def get_report_or_404(db: AsyncSession, report_id: uuid.UUID) -> Report:
    report = await db.get(Report, report_id)
    if report is None:
        raise NotFound("Report not found.")
    return report


async def list_queue(db: AsyncSession, *, status: str = "open", page: int, page_size: int) -> tuple[list[dict], int]:
    """§5.2. Default filter status='open' per the spec's exact wording."""
    total = (await db.execute(
        select(func.count()).select_from(Report).where(Report.status == status)
    )).scalar_one()
    rows = (await db.execute(
        select(Report).where(Report.status == status)
        .order_by(Report.created_at.asc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    items = []
    for r in rows:
        reporter = await _load_reporter(db, r.reporter_id)
        items.append({
            "id": str(r.id), "reporter": reporter, "target_type": r.target_type,
            "target_id": str(r.target_id), "reason": r.reason, "created_at": r.created_at,
        })
    return items, total


async def _apply_target_state_change(db: AsyncSession, *, target_type: str, target_id: uuid.UUID,
                                      action: str, edit_content: str | None) -> tuple[str | None, str]:
    """Returns (previous_state, new_state). For 'approve', previous == new
    (no content-state change — only the report itself resolves). Uses the
    non-committing apply_* helpers on community/research service modules so
    this whole operation (plus the ModerationAction insert, Report update,
    and audit_logs write in take_action below) commits exactly once, per
    Architecture §10.1's 'all four writes commit together or not at all'
    transactional requirement."""
    if action == "approve":
        # No state change — read current state for both previous/new.
        if target_type == "post":
            post = await community_service.get_post_or_404(db, target_id)
            return post.status, post.status
        if target_type == "comment":
            comment = await community_service.get_comment_or_404(db, target_id)
            return comment.status, comment.status
        research = await research_service.get_research_or_404(db, target_id)
        return research.moderation_status, research.moderation_status

    if action == "edit":
        if target_type in EDIT_UNSUPPORTED_FOR_TARGET_TYPES:
            raise QFinanceAPIError(
                "EDIT_UNSUPPORTED_FOR_TARGET_TYPE",
                "The 'edit' moderation action is not defined for research items in this MVP contract "
                "(research has no single free-text content field analogous to a post/comment's `content`; "
                "editing a specific Q-RESEARCH field is an authoring action, not a moderation one). "
                "Use 'restrict'/'remove'/'reinstate' for research, or 'approve' to dismiss.",
                400,
            )
        if not edit_content or not edit_content.strip():
            raise QFinanceAPIError(
                "VALIDATION_ERROR", "edit_content is required for the 'edit' action.", 400,
                fields={"edit_content": "required"},
            )
        if target_type == "post":
            post = await community_service.get_post_or_404(db, target_id)
            previous = post.content
            await community_service.apply_moderator_edit_to_post(db, post_id=target_id, new_content=edit_content)
            return previous, edit_content
        comment = await community_service.get_comment_or_404(db, target_id)
        previous = comment.content
        await community_service.apply_moderator_edit_to_comment(db, comment_id=target_id, new_content=edit_content)
        return previous, edit_content

    # restrict / remove / reinstate
    if action == "reinstate":
        new_status = _NORMAL_STATE_BY_TARGET_TYPE[target_type]
    else:
        new_status = action + "ed" if action == "restrict" else "removed"  # 'restricted' / 'removed'

    if target_type == "post":
        previous = await community_service.apply_moderation_status_to_post(db, post_id=target_id, new_status=new_status)
    elif target_type == "comment":
        previous = await community_service.apply_moderation_status_to_comment(
            db, comment_id=target_id, new_status=new_status,
        )
    else:
        previous = await research_service.apply_moderation_status(db, research_id=target_id, new_status=new_status)
    return previous, new_status


async def take_action(db: AsyncSession, *, report_id: uuid.UUID, actor_id: uuid.UUID,
                       action: str, reason: str | None, edit_content: str | None) -> ModerationAction:
    """§5.3, MOD-002. Single atomic transaction: (a) target state update,
    (b) moderation_actions insert, (c) reports resolution update,
    (d) audit_logs write — committed once at the end of this function, never
    partially. See module docstring for the reinstate/resolution_action
    contradiction this function deliberately does not paper over."""
    if action not in VALID_ACTIONS:
        raise QFinanceAPIError("INVALID_ACTION", f"action must be one of {VALID_ACTIONS}.", 400)

    report = await get_report_or_404(db, report_id)
    if report.status != "open":
        raise QFinanceAPIError("REPORT_ALREADY_RESOLVED", "This report has already been resolved.", 400)
    if report.target_type not in VALID_REPORT_TARGET_TYPES:
        # Defensive — the DB CHECK on reports.target_type already prevents this.
        raise QFinanceAPIError(
            "INVALID_ACTION_FOR_TARGET_TYPE",
            f"No valid moderation action exists for target_type={report.target_type!r}.", 400,
        )

    previous_state, new_state = await _apply_target_state_change(
        db, target_type=report.target_type, target_id=report.target_id, action=action, edit_content=edit_content,
    )

    moderation_action = ModerationAction(
        id=uuid.uuid4(), moderator_id=actor_id, target_type=report.target_type, target_id=report.target_id,
        action=action, report_id=report.id, previous_state=previous_state, new_state=new_state, reason=reason,
    )
    db.add(moderation_action)

    report.resolution_action = _RESOLUTION_ACTION_BY_ACTION.get(action)  # None for 'reinstate' — see docstring
    report.resolved_by = actor_id
    report.resolved_at = datetime.now(timezone.utc)
    report.status = "resolved"

    await write_audit_log(
        db, actor_id=actor_id, action_type=f"moderation.{action}",
        target_entity_type=report.target_type, target_entity_id=report.target_id,
        before_state={"status": previous_state}, after_state={"status": new_state}, reason=reason,
    )

    await db.commit()
    return moderation_action


async def suspend_member(db: AsyncSession, *, actor_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> str:
    """§5.4, MOD-004/ADMIN-004. Not tied to a report — a direct staff action."""
    if not reason or not reason.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "A reason is required.", 400, fields={"reason": "required"})

    previous_state = await auth_service.suspend_user(db, user_id=user_id)

    db.add(ModerationAction(
        id=uuid.uuid4(), moderator_id=actor_id, target_type="member", target_id=user_id,
        action="suspend_member", report_id=None, previous_state=previous_state, new_state="suspended", reason=reason,
    ))
    await write_audit_log(
        db, actor_id=actor_id, action_type="moderation.suspend_member",
        target_entity_type="member", target_entity_id=user_id,
        before_state={"status": previous_state}, after_state={"status": "suspended"}, reason=reason,
    )
    await db.commit()
    return "suspended"


async def reinstate_member(db: AsyncSession, *, actor_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """§5.5 — reverse of suspend_member."""
    previous_state = await auth_service.reinstate_user(db, user_id=user_id)

    db.add(ModerationAction(
        id=uuid.uuid4(), moderator_id=actor_id, target_type="member", target_id=user_id,
        action="reinstate_member", report_id=None, previous_state=previous_state, new_state="active", reason=None,
    ))
    await write_audit_log(
        db, actor_id=actor_id, action_type="moderation.reinstate_member",
        target_entity_type="member", target_entity_id=user_id,
        before_state={"status": previous_state}, after_state={"status": "active"},
    )
    await db.commit()
    return "active"


async def list_actions(db: AsyncSession, *, target_type: str | None, target_id: uuid.UUID | None,
                        page: int, page_size: int) -> tuple[list[ModerationAction], int]:
    """§5.6. No MODERATOR-vs-ADMIN partial-access restriction is specified
    for this endpoint (unlike the separate §10.7 admin audit-log endpoint,
    which explicitly restricts MODERATOR to `actor_id = self`) — MODERATOR
    sees full moderation history here, per the spec's plain reading."""
    stmt = select(ModerationAction)
    count_stmt = select(func.count()).select_from(ModerationAction)
    if target_type:
        stmt = stmt.where(ModerationAction.target_type == target_type)
        count_stmt = count_stmt.where(ModerationAction.target_type == target_type)
    if target_id:
        stmt = stmt.where(ModerationAction.target_id == target_id)
        count_stmt = count_stmt.where(ModerationAction.target_id == target_id)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(ModerationAction.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), total


# ---------------------------------------------------------------------------
# moderation_rules (§5.7-5.10, OD-08)
# ---------------------------------------------------------------------------

VALID_SEVERITIES = ("low", "medium", "high")


async def list_rules(db: AsyncSession) -> list[ModerationRule]:
    rows = (await db.execute(select(ModerationRule).order_by(ModerationRule.created_at.desc()))).scalars().all()
    return list(rows)


async def create_rule(db: AsyncSession, *, actor_id: uuid.UUID, phrase: str, severity: str) -> ModerationRule:
    """§5.8. `action` is never client-settable — always server-set to
    'flag_for_review', matching the DB's own hard CHECK constraint (AD-05)."""
    if not phrase or not phrase.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "phrase cannot be empty.", 400, fields={"phrase": "required"})
    if severity not in VALID_SEVERITIES:
        raise QFinanceAPIError("INVALID_SEVERITY", f"severity must be one of {VALID_SEVERITIES}.", 400)
    rule = ModerationRule(
        id=uuid.uuid4(), phrase=phrase, severity=severity, enabled=True,
        action="flag_for_review", created_by=actor_id,
    )
    db.add(rule)
    await db.commit()
    return rule


async def get_rule_or_404(db: AsyncSession, rule_id: uuid.UUID) -> ModerationRule:
    rule = await db.get(ModerationRule, rule_id)
    if rule is None:
        raise NotFound("Moderation rule not found.")
    return rule


async def patch_rule(db: AsyncSession, *, rule_id: uuid.UUID, enabled: bool | None,
                      severity: str | None) -> ModerationRule:
    """§5.9. `phrase`/`action` are immutable after creation, per the spec's
    explicit wording — not accepted here even if a caller sent them."""
    rule = await get_rule_or_404(db, rule_id)
    if enabled is not None:
        rule.enabled = enabled
    if severity is not None:
        if severity not in VALID_SEVERITIES:
            raise QFinanceAPIError("INVALID_SEVERITY", f"severity must be one of {VALID_SEVERITIES}.", 400)
        rule.severity = severity
    await db.commit()
    return rule


async def delete_rule(db: AsyncSession, *, rule_id: uuid.UUID) -> None:
    """§5.10 — hard delete is acceptable here (configuration, not user
    content or audit trail), per the spec's explicit note."""
    rule = await get_rule_or_404(db, rule_id)
    await db.delete(rule)
    await db.commit()
