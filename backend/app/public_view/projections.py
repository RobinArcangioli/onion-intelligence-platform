"""Allowlisted public metadata, independent of internal report records."""
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import Report

PUBLIC_DISCLAIMER = 'Veille documentaire : les mentions et les volumes ne prouvent aucun incident.'
TOTAL_KEYS = ('observations', 'discoveries', 'classifications', 'indicators', 'alerts')
# Names are deliberately public, but must not carry addresses or credentials.
UNSAFE_NAME = re.compile(r'(?:\.onion\b|://|www\.|@|\boip_[a-z0-9_-]+|\b(?:token|password|secret|api[_ -]?key)\s*[:=]|[a-f0-9]{32,})', re.I)


def public_source_name(value: str) -> str:
    if (UNSAFE_NAME.search(value) or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or len(value) > 160):
        return 'Source (nom masqué)'
    return value.strip() or 'Source sans nom'


def utc_date(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class PublicTotals(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)
    observations: int = Field(ge=0, le=10**12)
    discoveries: int = Field(ge=0, le=10**12)
    classifications: int = Field(ge=0, le=10**12)
    indicators: int = Field(ge=0, le=10**12)
    alerts: int = Field(ge=0, le=10**12)


class PublicReportPayload(BaseModel):
    model_config = ConfigDict(extra='ignore')
    schema_version: Literal['PUBLIC_TOTALS_V1'] = 'PUBLIC_TOTALS_V1'
    period_start: datetime
    period_end: datetime
    totals: PublicTotals
    disclaimer: Literal[PUBLIC_DISCLAIMER] = PUBLIC_DISCLAIMER


def project_report(report: Report) -> PublicReportPayload:
    totals = report.snapshot.get('totals', {})
    # Reject malformed snapshots rather than coerce arbitrary strings into public data.
    counters = PublicTotals.model_validate({key: totals.get(key, 0) for key in TOTAL_KEYS})
    return PublicReportPayload(period_start=utc_date(report.period_start),
                               period_end=utc_date(report.period_end), totals=counters)


def payload_digest(payload: PublicReportPayload) -> str:
    return hashlib.sha256(json.dumps(payload.model_dump(mode='json'),
                                     sort_keys=True, separators=(',', ':')).encode()).hexdigest()
