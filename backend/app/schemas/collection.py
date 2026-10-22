"""Réponses bornées, sans corps HTML, sans secret ni preuve présumée."""
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ORMOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JobOut(ORMOutput):
    id: uuid.UUID
    source_id: uuid.UUID
    status: str
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ObservationOut(ORMOutput):
    id: uuid.UUID
    job_id: uuid.UUID
    source_id: uuid.UUID
    http_status: int
    content_type: str
    response_bytes: int
    title: str
    description: str
    text_sha256: str
    text_length: int
    discovered_links: int
    created_at: datetime


class DiscoveryOut(ORMOutput):
    id: uuid.UUID
    source_id: uuid.UUID
    target_url: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime


class Page(BaseModel):
    total: int
    limit: int
    offset: int
    items: list
