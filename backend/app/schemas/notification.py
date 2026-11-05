"""Strictly structured metadata: external delivery is not a supported setting."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CasePriority = Literal["UNASSESSED", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
CaseStatus = Literal["OPEN", "IN_REVIEW", "ESCALATED", "CLOSED"]


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,31}$")
    target_status: CaseStatus
    minimum_priority: CasePriority


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    approved: bool
    enabled: bool

    @model_validator(mode="after")
    def only_approved_can_be_enabled(self):
        if self.enabled and not self.approved:
            raise ValueError("Enable requires explicit administrative approval")
        return self


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    target_status: CaseStatus
    minimum_priority: CasePriority
    approved: bool
    enabled: bool
    version: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    transport: Literal["NONE"] = "NONE"


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    policy_id: UUID
    expected_case_version: int = Field(ge=1)


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    policy_id: UUID
    case_id: UUID
    case_version: int
    created_by: str
    delivery_status: Literal["NOT_SENT"]
    payload: dict
    created_at: datetime
    destinations: list = Field(default_factory=list)
