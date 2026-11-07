"""Réponses bornées, sans corps HTML, sans secret ni preuve présumée."""
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_serializer


class ORMOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JobOut(ORMOutput):
    id: uuid.UUID
    source_id: uuid.UUID
    page_id: uuid.UUID | None = None
    status: str
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ObservationOut(ORMOutput):
    id: uuid.UUID
    job_id: uuid.UUID
    source_id: uuid.UUID
    page_id: uuid.UUID | None = None
    origin: str = "TOR_HTTP"
    http_status: int | None
    content_type: str
    response_bytes: int
    title: str
    description: str
    text_sha256: str
    text_length: int
    change_status: str
    relevance_score: int
    keyword_hits: int
    discovered_links: int
    created_at: datetime

    @field_serializer("http_status")
    def serialize_http_status(self, status: int | None) -> int | None:
        # Historic storage requires an integer; captures have no HTTP response.
        return status if self.origin == "TOR_HTTP" else None


class DiscoveryOut(ORMOutput):
    id: uuid.UUID
    source_id: uuid.UUID
    target_url: str
    status: str
    evidence_kind: str
    reviewed_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime


class Page(BaseModel):
    total: int
    limit: int
    offset: int
    items: list


class CollectionProgress(BaseModel):
    total: int = 0
    completed: int = 0
    failed: int = 0
    waiting: int = 0
    running_url: str | None = None
    restriction: str | None = None
    retry_at: datetime | None = None
