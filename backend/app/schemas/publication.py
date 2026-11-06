"""Human-authored public incident summaries, separate from collected content."""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DataCategory = Literal['CUSTOMER_RECORDS', 'CONTACT_DETAILS', 'EMPLOYEE_RECORDS',
                       'INTERNAL_DOCUMENTS', 'FINANCIAL_RECORDS']
UNSAFE_TEXT = re.compile(r'(?:\.onion\b|://|www\.|@|\boip_[\w-]+|\b(?:password|secret|api[_ -]?key|token)\s*[:=]|[a-f0-9]{32,}|[<>])', re.I)


class PublicIncidentDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=8, max_length=160)
    company_name: str = Field(min_length=2, max_length=160)
    sector: str = Field(min_length=2, max_length=80)
    summary: str = Field(min_length=20, max_length=1500)
    data_categories: list[DataCategory] = Field(min_length=1, max_length=5)
    affected_records: int | None = Field(default=None, ge=1, le=10**9, strict=True)
    detected_at: datetime
    recommendations: str = Field(min_length=10, max_length=800)
    assessment: Literal['SUSPECTED_DATA_LEAK'] = 'SUSPECTED_DATA_LEAK'
    simulation: bool = Field(default=False, strict=True)

    @field_validator('title', 'company_name', 'sector', 'summary', 'recommendations')
    @classmethod
    def public_text(cls, value: str, info) -> str:
        if (not value.strip() or UNSAFE_TEXT.search(value)
                or any((ord(c) < 32 and c != '\n') or ord(c) == 127 for c in value)):
            raise ValueError('Public text must omit addresses, identifiers, credentials and markup')
        value=value.strip()
        minimum={'title':8,'company_name':2,'sector':2,'summary':20,'recommendations':10}[info.field_name]
        if len(value)<minimum:
            raise ValueError('Public text is too short after trimming')
        return value

    @field_validator('detected_at')
    @classmethod
    def aware_date(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError('Timezone-aware detection date required')
        return value

    @field_validator('data_categories')
    @classmethod
    def distinct_categories(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Data categories must be distinct')
        return value
