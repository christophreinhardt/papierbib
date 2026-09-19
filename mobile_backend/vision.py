"""Replaceable, server-only vision providers for one confirmed book image."""
import base64
import json
import socket
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .images import CropSpec, crop_image
from .isbn import canonical, isbn10, valid


class VisionError(Exception):
    pass


class Confidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    author: float = Field(ge=0, le=1)
    title: float = Field(ge=0, le=1)
    publisher: float = Field(ge=0, le=1)
    isbn: float = Field(ge=0, le=1)
    overall: float = Field(ge=0, le=1)


class VisionResult(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    raw_text: str | None = Field(max_length=5000)
    title: str | None = Field(max_length=500)
    subtitle: str | None = Field(max_length=500)
    authors: list[str] = Field(max_length=30)
    publisher: str | None = Field(max_length=500)
    language: str | None = Field(max_length=40)
    publication_year: int | None = Field(ge=1000, le=2100)
    isbn10: str | None = Field(max_length=30)
    isbn13: str | None = Field(max_length=30)
    confidence: Confidence

    @field_validator('authors')
    @classmethod
    def author_names(cls, values):
        return list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))

    @model_validator(mode='after')
    def normalize_only_valid_isbns(self):
        values = [v for v in (self.isbn13, self.isbn10) if v and valid(v)]
        if not values:
            self.isbn10 = self.isbn13 = None
            return self
        number = canonical(values[0])
        # Contradictory ISBN fields are evidence of a bad extraction, not a cue
        # to choose one silently.
        if any(canonical(value) != number for value in values):
            self.isbn10 = self.isbn13 = None
            return self
        self.isbn13, self.isbn10 = number, isbn10(number)
        return self


SCHEMA = VisionResult.model_json_schema()
SCHEMA['additionalProperties'] = False
SCHEMA['propertyOrdering'] = list(SCHEMA['properties'])

PROMPT = '''Extract bibliographic evidence from this single {kind} photograph.
Return only observed text and metadata. Unknown fields must be null; authors must
be an empty list when unknown. Preserve accents. Never infer or fabricate an ISBN.
Do not confuse title and author. ISBN values may only be transcribed if clearly
visible. confidence values describe what is visible in this image, from 0 to 1.'''


def _json_request(url, headers, payload, timeout=35):
    request = Request(url, data=json.dumps(payload, separators=(',', ':')).encode(), headers=headers, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(4_000_001)
            if len(body) > 4_000_000:
                raise VisionError('KI-Antwort überschreitet das Sicherheitslimit.')
            return json.loads(body)
    except HTTPError as exc:
        raise VisionError('KI-Anbieter hat die Anfrage abgelehnt oder ist nicht verfügbar (HTTP %s).' % exc.code) from exc
    except (URLError, socket.timeout, TimeoutError, OSError, ValueError) as exc:
        raise VisionError('KI-Anbieter ist derzeit nicht erreichbar oder lieferte keine gültige Antwort.') from exc


def _openai_text(response):
    for item in response.get('output', []):
        for content in item.get('content', []):
            if content.get('type') == 'output_text' and isinstance(content.get('text'), str):
                return content['text']
    raise VisionError('OpenAI lieferte keine strukturierte Textantwort.')


def openai(settings, image, kind):
    if not settings.openai_api_key:
        raise VisionError('OpenAI ist nicht konfiguriert. OPENAI_API_KEY in Portainer setzen.')
    encoded = base64.b64encode(image).decode('ascii')
    payload = {
        'model': settings.openai_vision_model,
        'input': [{'role': 'user', 'content': [
            {'type': 'input_text', 'text': PROMPT.format(kind=kind)},
            {'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + encoded, 'detail': 'high'},
        ]}],
        'text': {'format': {'type': 'json_schema', 'name': 'book_metadata', 'strict': True, 'schema': SCHEMA}},
    }
    return json.loads(_openai_text(_json_request('https://api.openai.com/v1/responses', {
        'Authorization': 'Bearer ' + settings.openai_api_key, 'Content-Type': 'application/json'}, payload)))


def gemini(settings, image, kind):
    if not settings.gemini_api_key:
        raise VisionError('Gemini ist nicht konfiguriert. GEMINI_API_KEY in Portainer setzen.')
    payload = {
        'contents': [{'role': 'user', 'parts': [
            {'text': PROMPT.format(kind=kind)},
            {'inlineData': {'mimeType': 'image/jpeg', 'data': base64.b64encode(image).decode('ascii')}},
        ]}],
        'generationConfig': {'responseMimeType': 'application/json', 'responseJsonSchema': SCHEMA},
    }
    endpoint = 'https://generativelanguage.googleapis.com/v1beta/models/' + quote(settings.gemini_vision_model, safe='-_.') + ':generateContent'
    response = _json_request(endpoint, {'x-goog-api-key': settings.gemini_api_key, 'Content-Type': 'application/json'}, payload)
    try:
        return json.loads(response['candidates'][0]['content']['parts'][0]['text'])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise VisionError('Gemini lieferte keine strukturierte Textantwort.') from exc


def configured(settings):
    return [name for name, key in (('openai', settings.openai_api_key), ('gemini', settings.gemini_api_key)) if key]


def analyze(settings, provider, image, kind):
    _, crop = crop_image(image, CropSpec(), settings.max_pixels)
    provider = provider or settings.ai_provider
    if provider not in configured(settings):
        raise VisionError('Der gewählte KI-Anbieter ist nicht konfiguriert.')
    parsed = openai(settings, crop['data'], kind) if provider == 'openai' else gemini(settings, crop['data'], kind)
    result = VisionResult.model_validate(parsed)
    return dict(result.model_dump(), provider=provider,
                model=settings.openai_vision_model if provider == 'openai' else settings.gemini_vision_model,
                analyzed_at=datetime.now(timezone.utc).isoformat())
