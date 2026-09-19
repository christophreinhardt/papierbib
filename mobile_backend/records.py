"""Editable Phase-2 records; confirmations are human decisions, not AI confidence."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .isbn import canonical


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    isbn: str = Field(max_length=80)

    @field_validator('isbn')
    @classmethod
    def check_isbn(cls, value):
        return canonical(value)


class BookInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    book_id: UUID
    photo_id: UUID | None = None
    crop_id: UUID | None = None
    status: Literal['confirmed', 'draft', 'needs_scan'] = 'draft'
    isbn13: str = Field(max_length=80)
    title: str | None = Field(default=None, max_length=500)
    subtitle: str | None = Field(default=None, max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=30)
    editors: list[str] = Field(default_factory=list, max_length=30)
    publisher: str | None = Field(default=None, max_length=500)
    publication_year: int | None = Field(default=None, ge=1000, le=2100)
    language: str | None = Field(default=None, max_length=40)
    edition: str | None = Field(default=None, max_length=200)
    extent: str | None = Field(default=None, max_length=200)
    publication_place: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=500)
    fetched_at: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator('isbn13')
    @classmethod
    def check_isbn(cls, value):
        return canonical(value)

    @field_validator('authors', 'editors')
    @classmethod
    def names(cls, values):
        if any(len(v) > 200 for v in values):
            raise ValueError('Name zu lang.')
        return list(dict.fromkeys(v.strip() for v in values if v.strip()))

    @field_validator('title','subtitle','publisher','language','edition','extent','publication_place','notes')
    @classmethod
    def nullable(cls, value):
        return value or None

    @field_validator('source_url')
    @classmethod
    def source(cls, value):
        if value:
            from urllib.parse import urlsplit
            url = urlsplit(value)
            if url.scheme != 'https' or url.netloc != 'lobid.org' or not url.path.startswith('/resources/'):
                raise ValueError('Ungültige Quellenadresse.')
        return value or None
