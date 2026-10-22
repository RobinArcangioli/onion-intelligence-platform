"""Read-only CTI API and bounded classification review actions."""
from datetime import datetime
from typing import Literal
import uuid
from pydantic import BaseModel, ConfigDict, Field

class ORMOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class ClassificationOut(ORMOutput):
    id: uuid.UUID
    observation_id: uuid.UUID
    source_id: uuid.UUID
    category: str
    confidence: int
    evidence_codes: list[str]
    ruleset_version: str
    review_status: str
    reviewed_at: datetime | None
    created_at: datetime

class IndicatorOut(ORMOutput):
    id: uuid.UUID
    observation_id: uuid.UUID
    source_id: uuid.UUID
    indicator_type: str
    public_reference: str
    verification_status: str
    confidence: int
    evidence_codes: list[str]
    ruleset_version: str
    created_at: datetime

class ClassificationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ACCEPTED", "REJECTED"]
    reason: str = Field(default="Manual check", min_length=10, max_length=100, pattern=r"^[\x20-\x7e]+$")
