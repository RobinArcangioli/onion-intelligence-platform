"""Validated administrative contracts. No URLs cause network requests."""
from datetime import datetime
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.analyzers.keywords import normalized_phrase


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WatchlistCreate(Strict):
    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid watchlist name")
        return value


class RuleCreate(Strict):
    phrase: str = Field(min_length=2, max_length=120)
    weight: int = Field(default=10, ge=1, le=30)

    @field_validator("phrase")
    @classmethod
    def validate_phrase(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2 or any(ord(c) < 32 for c in value) or not normalized_phrase(value) or len(normalized_phrase(value)) > 160:
            raise ValueError("Invalid phrase")
        return value


class ActiveUpdate(Strict):
    is_active: bool
    reason: str = Field(min_length=10, max_length=100)


class DiscoveryReview(Strict):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=10, max_length=100)


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    watchlist_id: uuid.UUID
    phrase: str
    weight: int
    is_active: bool
    created_at: datetime
