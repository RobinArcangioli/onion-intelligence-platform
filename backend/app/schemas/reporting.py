"""Validated actions and API-safe reporting metadata."""
from datetime import datetime, timezone, timedelta
from typing import Literal
import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AlertOut(ORMOut):
    id: uuid.UUID
    source_id: uuid.UUID
    observation_id: uuid.UUID
    event_type: str
    signal_code: str
    priority: str
    verification_status: str
    relevance_score: int
    status: str
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime


class AlertReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ACKNOWLEDGED", "RESOLVED"]
    reason: str = Field(default="Manual check", min_length=10, max_length=100, pattern=r"^[\x20-\x7e]+$")


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: uuid.UUID | None = None
    period_start: datetime
    period_end: datetime
    max_rows_per_type: int = Field(default=100, ge=1, le=200)

    @model_validator(mode="after")
    def validate_period(self) -> "ReportCreate":
        a, b = self.period_start, self.period_end
        if a.utcoffset() is None or b.utcoffset() is None:
            raise ValueError("Timezone-aware dates are required")
        if a >= b or b - a > timedelta(days=366):
            raise ValueError("Invalid report period (maximum 366 days)")
        if b > datetime.now(timezone.utc) + timedelta(days=1):
            raise ValueError("Report period cannot end in the distant future")
        return self


class ReportOut(ORMOut):
    id: uuid.UUID
    source_id: uuid.UUID | None
    period_start: datetime
    period_end: datetime
    created_at: datetime
