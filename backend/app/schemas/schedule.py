"""Schedule contract: every enabling action is an explicit ADMIN opt-in."""
import uuid
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScheduleConfigure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool  # Required, never defaults to true.
    interval_minutes: int = Field(ge=60, le=10080)
    daily_budget: int = Field(ge=1, le=24)
    window_start_hour: int = Field(ge=0, le=23)
    window_end_hour: int = Field(ge=1, le=24)
    expires_at: datetime
    approval_reference: str = Field(min_length=10, max_length=500)
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("approval_reference", "reason")
    @classmethod
    def require_explanation(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Explicit reason/reference requires at least 10 visible characters")
        return value

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must contain a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_approval(self) -> "ScheduleConfigure":
        if self.window_start_hour >= self.window_end_hour:
            raise ValueError("UTC start must precede UTC end")
        now = datetime.now(timezone.utc)
        if not now < self.expires_at <= now + timedelta(days=90):
            raise ValueError("expiry must be in the future and within one year")
        return self


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source_id: uuid.UUID
    enabled: bool
    interval_minutes: int
    daily_budget: int
    window_start_hour: int
    window_end_hour: int
    expires_at: datetime
    approval_reference: str
    next_run_at: datetime


class ScheduleDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_id: uuid.UUID
    job_id: uuid.UUID | None
    decision: str
    approval_reference: str
    authorization_expires_at: datetime
    created_at: datetime


class SchedulePause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Explicit reason required")
        return value
