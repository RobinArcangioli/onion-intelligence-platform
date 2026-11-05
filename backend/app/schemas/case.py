"""Case commands accept only structured metadata, never arbitrary page excerpts."""
import uuid
from datetime import datetime
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

CaseStatus = Literal["OPEN", "IN_REVIEW", "ESCALATED", "CLOSED"]
CaseAction = Literal["ASSIGN", "UNASSIGN", "START_REVIEW", "ESCALATE", "RETURN_REVIEW", "CLOSE", "SET_PRIORITY"]
CasePriority = Literal["UNASSESSED", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
EscalationReason = Literal["REVIEW_REQUIRED", "TIME_SENSITIVE", "MULTI_SOURCE", "OTHER"]
NoteCode = Literal["ANALYST_CONTEXT", "FOLLOW_UP", "FALSE_POSITIVE_CHECK", "ESCALATION_CONTEXT"]
ClosureCode = Literal["DOCUMENTED", "NOT_RELEVANT", "DUPLICATE"]


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alert_id: uuid.UUID


class CaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: CaseAction
    expected_version: int = Field(ge=1, le=2_147_483_647)
    assignee_username: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    closure_code: ClosureCode | None = None
    priority: CasePriority | None = None
    escalation_reason: EscalationReason | None = None

    @model_validator(mode="after")
    def parameters(self):
        if (self.action == "ASSIGN") != (self.assignee_username is not None):
            raise ValueError("ASSIGN requires assignee_username, other actions forbid it")
        if (self.action == "CLOSE") != (self.closure_code is not None):
            raise ValueError("CLOSE requires closure_code, other actions forbid it")
        if (self.action == "SET_PRIORITY") != (self.priority is not None):
            raise ValueError("SET_PRIORITY requires priority, other actions forbid it")
        if (self.action == "ESCALATE") != (self.escalation_reason is not None):
            raise ValueError("ESCALATE requires escalation_reason, other actions forbid it")
        return self


class CaseNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, le=2_147_483_647)
    note_code: NoteCode
    body: str = Field(min_length=8, max_length=300)

    @model_validator(mode="after")
    def safe_internal_note(self):
        value = self.body.strip()
        # These are short analyst annotations, NOT excerpts, credentials or pasted artifacts.
        if len(value) < 8 or re.search(r"[\x00-\x1f\x7f]|https?://|www\.|\.onion\b|@|\b(?:token|password|secret|api[_-]?key|bearer)\b",
                                         value, flags=re.I):
            raise ValueError("Only short sanitized notes are permitted; no URLs, credentials or source excerpts")
        self.body = value
        return self


class CaseNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    case_version: int
    actor: str
    note_code: NoteCode
    body: str
    created_at: datetime


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    alert_id: uuid.UUID
    status: CaseStatus
    priority: CasePriority
    assignee_id: uuid.UUID | None
    assignee_username: str | None = None
    version: int
    closure_code: ClosureCode | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class CaseEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    version: int
    actor: str
    action: str
    from_status: str | None
    to_status: str
    assignee_username: str | None
    reason_code: str | None
    created_at: datetime
