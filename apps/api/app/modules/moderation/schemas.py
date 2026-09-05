"""Moderation module schemas — API Specification V1 §5. WRITTEN, NOT EXECUTED."""
from datetime import datetime

from pydantic import BaseModel

VALID_REPORT_TARGET_TYPES = ("post", "comment", "research")
VALID_ACTIONS = ("approve", "edit", "restrict", "remove", "reinstate")


class ReportCreateRequest(BaseModel):
    target_type: str
    target_id: str
    reason: str


class ReportCreateResponse(BaseModel):
    id: str


class ReporterRef(BaseModel):
    id: str
    name: str | None = None
    username: str | None = None


class QueueItem(BaseModel):
    id: str
    reporter: ReporterRef
    target_type: str
    target_id: str
    reason: str
    created_at: datetime


class QueueListResponse(BaseModel):
    items: list[QueueItem]
    page: int
    page_size: int
    total: int


class TakeActionRequest(BaseModel):
    action: str
    reason: str | None = None
    edit_content: str | None = None


class TakeActionResponse(BaseModel):
    moderation_action_id: str
    new_state: str


class SuspendMemberRequest(BaseModel):
    reason: str


class MemberActionResponse(BaseModel):
    user_id: str
    status: str


class ModerationActionItem(BaseModel):
    id: str
    moderator_id: str
    target_type: str
    target_id: str
    action: str
    report_id: str | None
    previous_state: str | None
    new_state: str
    reason: str | None
    created_at: datetime


class ModerationActionListResponse(BaseModel):
    items: list[ModerationActionItem]
    page: int
    page_size: int
    total: int


class ModerationRuleCreateRequest(BaseModel):
    phrase: str
    severity: str


class ModerationRulePatchRequest(BaseModel):
    enabled: bool | None = None
    severity: str | None = None


class ModerationRuleResponse(BaseModel):
    id: str
    phrase: str
    severity: str
    enabled: bool

    class Config:
        from_attributes = True
