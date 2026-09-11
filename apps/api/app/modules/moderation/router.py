"""Moderation routes — API Specification V1 §5. WRITTEN, NOT EXECUTED."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_profile, require_csrf, require_role
from app.modules.moderation import service
from app.modules.moderation.schemas import (
    MemberActionResponse, ModerationActionListResponse, ModerationRuleCreateRequest, ModerationRulePatchRequest,
    ModerationRuleResponse, QueueListResponse, ReportCreateRequest, ReportCreateResponse, SuspendMemberRequest,
    TakeActionRequest, TakeActionResponse,
)
from app.modules.users.models import Profile

router = APIRouter(prefix="/moderation", tags=["moderation"])

_STAFF_ROLES = ("MODERATOR", "ADMIN", "SUPER_ADMIN")


@router.post("/reports", response_model=ReportCreateResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_report(
    body: ReportCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
):
    """§5.1, COMM-007, MOD-001 — requires MEMBER (reporting is a Core-gated
    community interaction, same tier as posting/commenting)."""
    report = await service.create_report(
        db, reporter_id=profile.user_id, target_type=body.target_type,
        target_id=uuid.UUID(body.target_id), reason=body.reason,
    )
    return ReportCreateResponse(id=str(report.id))


@router.get("/queue", response_model=QueueListResponse)
async def list_queue(
    status: str = Query(default="open"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role(*_STAFF_ROLES)),
):
    """§5.2 — MODERATOR/ADMIN/SUPER_ADMIN only."""
    items, total = await service.list_queue(db, status=status, page=page, page_size=page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/queue/{report_id}/action", response_model=TakeActionResponse, dependencies=[Depends(require_csrf)])
async def take_action(
    report_id: uuid.UUID,
    body: TakeActionRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role(*_STAFF_ROLES)),
):
    """§5.3, MOD-002 — MODERATOR/ADMIN/SUPER_ADMIN only. See moderation/service.py
    module docstring for the reinstate/resolution_action contradiction this
    endpoint's underlying logic deliberately does not paper over."""
    moderation_action = await service.take_action(
        db, report_id=report_id, actor_id=profile.user_id,
        action=body.action, reason=body.reason, edit_content=body.edit_content,
    )
    return TakeActionResponse(moderation_action_id=str(moderation_action.id), new_state=moderation_action.new_state)


@router.post("/members/{user_id}/suspend", response_model=MemberActionResponse, dependencies=[Depends(require_csrf)])
async def suspend_member(
    user_id: uuid.UUID,
    body: SuspendMemberRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role(*_STAFF_ROLES)),
):
    """§5.4, MOD-004/ADMIN-004."""
    status_value = await service.suspend_member(db, actor_id=profile.user_id, user_id=user_id, reason=body.reason)
    return MemberActionResponse(user_id=str(user_id), status=status_value)


@router.post("/members/{user_id}/reinstate", response_model=MemberActionResponse, dependencies=[Depends(require_csrf)])
async def reinstate_member(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role(*_STAFF_ROLES)),
):
    """§5.5."""
    status_value = await service.reinstate_member(db, actor_id=profile.user_id, user_id=user_id)
    return MemberActionResponse(user_id=str(user_id), status=status_value)


@router.get("/actions", response_model=ModerationActionListResponse)
async def list_actions(
    target_type: str | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role(*_STAFF_ROLES)),
):
    """§5.6 — no MODERATOR-vs-ADMIN partial restriction here, see service.py docstring."""
    rows, total = await service.list_actions(
        db, target_type=target_type, target_id=target_id, page=page, page_size=page_size,
    )
    items = [
        {
            "id": str(a.id), "moderator_id": str(a.moderator_id), "target_type": a.target_type,
            "target_id": str(a.target_id), "action": a.action,
            "report_id": str(a.report_id) if a.report_id else None,
            "previous_state": a.previous_state, "new_state": a.new_state,
            "reason": a.reason, "created_at": a.created_at,
        }
        for a in rows
    ]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/rules", response_model=list[ModerationRuleResponse])
async def list_rules(
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("ADMIN", "SUPER_ADMIN")),
):
    """§5.7 — ADMIN/SUPER_ADMIN only, per OD-08 (admin-configurable)."""
    rules = await service.list_rules(db)
    return [ModerationRuleResponse.model_validate(r) for r in rules]


@router.post("/rules", response_model=ModerationRuleResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_rule(
    body: ModerationRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("ADMIN", "SUPER_ADMIN")),
):
    """§5.8."""
    rule = await service.create_rule(db, actor_id=profile.user_id, phrase=body.phrase, severity=body.severity)
    return ModerationRuleResponse.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=ModerationRuleResponse, dependencies=[Depends(require_csrf)])
async def patch_rule(
    rule_id: uuid.UUID,
    body: ModerationRulePatchRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("ADMIN", "SUPER_ADMIN")),
):
    """§5.9."""
    rule = await service.patch_rule(db, rule_id=rule_id, enabled=body.enabled, severity=body.severity)
    return ModerationRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("ADMIN", "SUPER_ADMIN")),
):
    """§5.10."""
    await service.delete_rule(db, rule_id=rule_id)
