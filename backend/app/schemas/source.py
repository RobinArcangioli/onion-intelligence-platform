import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security.onion import canonical_onion_root


class SourceCreate(BaseModel):
    url: str
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    authorization_confirmed: Literal[True]
    authorization_note: str = Field(min_length=10, max_length=1000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return canonical_onion_root(value)


class SourceOut(BaseModel):
    id: uuid.UUID
    canonical_url: str
    name: str
    description: str
    category: str
    availability_status: str
    approved_for_collection: bool
    collection_enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceList(BaseModel):
    total: int
    items: list[SourceOut]
