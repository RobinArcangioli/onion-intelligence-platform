"""Contrats stricts des routes sources (aucune URL arbitraire)."""
import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.security.onion import canonical_onion_root


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceCreate(StrictSchema):
    url: str
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    priority: int = Field(default=3, ge=1, le=5)
    authorization_confirmed: Literal[True]
    authorization_note: str = Field(min_length=10, max_length=1000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return canonical_onion_root(value)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Le nom ne peut pas être vide")
        return result

    @field_validator("authorization_note")
    @classmethod
    def strip_authorization(cls, value: str) -> str:
        result = value.strip()
        if len(result) < 10:
            raise ValueError("Autorisation documentée sur au moins dix caractères")
        return result


class SourcePatch(StrictSchema):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    priority: int | None = Field(default=None, ge=1, le=5)
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Le nom ne peut pas être vide")
        return value

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Justification requise (10 caractères minimum)")
        return value

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,59}", value):
            raise ValueError("Catégorie attendue : MAJUSCULES_ET_SNAKE_CASE")
        return value

    @model_validator(mode="after")
    def at_least_one_change(self) -> "SourcePatch":
        if not any(getattr(self, k) is not None for k in ("name", "description", "category", "priority")):
            raise ValueError("Au moins un champ modifiable est requis")
        return self


class SourceReason(StrictSchema):
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        result = value.strip()
        if len(result) < 10:
            raise ValueError("Une justification explicite est nécessaire")
        return result


class SourceApproval(StrictSchema):
    authorization_confirmed: Literal[True]
    authorization_note: str = Field(min_length=10, max_length=1000)

    @field_validator("authorization_note")
    @classmethod
    def strip_note(cls, value: str) -> str:
        result = value.strip()
        if len(result) < 10:
            raise ValueError("Justification d'autorisation requise")
        return result


class SourceOut(BaseModel):
    id: uuid.UUID
    canonical_url: str
    name: str
    description: str
    category: str
    availability_status: str
    approved_for_collection: bool
    collection_enabled: bool
    is_active: bool
    priority: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class SourceList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SourceOut]


class SourceAuditOut(BaseModel):
    id: uuid.UUID
    action: str
    actor: str
    details: dict[str, object]
    created_at: datetime


class SourceHistory(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SourceAuditOut]


class SourceImportRequest(StrictSchema):
    items: list[SourceCreate] = Field(min_length=1, max_length=100)


class SourceImportResult(BaseModel):
    total: int
    items: list[SourceOut]
