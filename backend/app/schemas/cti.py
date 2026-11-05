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
    review_status: str
    analyst_priority: str
    reviewed_at: datetime | None
    created_at: datetime

class IndicatorReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ACCEPTED", "REJECTED"]
    analyst_priority: Literal["UNASSESSED", "LOW", "MEDIUM", "HIGH"] = "UNASSESSED"
    reason: str = Field(min_length=10, max_length=100, pattern=r"^[\x20-\x7e]+$")

class ClassificationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ACCEPTED", "REJECTED"]
    reason: str = Field(default="Manual check", min_length=10, max_length=100, pattern=r"^[\x20-\x7e]+$")


class IocCandidateOut(ORMOutput):
    id: uuid.UUID
    observation_id: uuid.UUID
    source_id: uuid.UUID
    indicator_type: Literal["DOMAIN", "IPV4", "IPV6", "SHA256"]
    normalized_value: str
    confidence: int
    evidence_codes: list[str]
    ruleset_version: str
    review_status: str
    analyst_priority: str
    reviewed_at: datetime | None
    created_at: datetime


class IocCandidateReview(BaseModel):
    """Fixed reason codes avoid storing accidental secrets in analyst notes."""
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ACCEPTED", "REJECTED"]
    analyst_priority: Literal["UNASSESSED", "LOW", "MEDIUM", "HIGH"] = "UNASSESSED"
    reason_code: Literal["PUBLIC_REFERENCE_CONFIRMED", "NON_INDICATOR", "MISPARSED", "OUT_OF_SCOPE"]
