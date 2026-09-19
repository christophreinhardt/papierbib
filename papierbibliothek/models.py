"""Versioned, offline domain model. One book record represents one physical copy."""
from dataclasses import asdict, dataclass, field
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4
import math
import re

from .isbn import normalize, valid, to_isbn13

SCHEMA_VERSION = 5
STATUSES = {
    'needs_manual_review': 'Prüfen', 'needs_scan': 'Nachscan nötig',
    'manual_confirmed': 'Manuell bestätigt', 'rejected': 'Ignoriert',
    'matched': 'Eindeutig zugeordnet', 'probable_match': 'Wahrscheinlicher Treffer',
    'imported': 'In Calibre importiert', 'import_error': 'Importfehler',
}
MANUAL_STATUSES = ('needs_manual_review', 'needs_scan', 'manual_confirmed', 'rejected')


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Ungültiger relativer Bildpfad.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value:
        raise ValueError('Bildpfade müssen innerhalb des Projekts liegen.')
    return value


@dataclass
class Photo:
    photo_id: str = field(default_factory=uid)
    original_name: str = ''
    image_path: str = ''
    preview_path: str = ''
    sha256: str = ''
    width: int = 0
    height: int = 0
    location: str = ''
    created_at: str = field(default_factory=now)


@dataclass
class Book:
    book_id: str = field(default_factory=uid)
    photo_id: str | None = None
    image_path: str | None = None
    crop_path: str | None = None
    title_page_path: str | None = None
    title_page_photo_id: str | None = None
    vision_image_path: str | None = None
    bounding_box: dict | None = None
    raw_text: str | None = None
    author: str | None = None
    title: str | None = None
    subtitle: str | None = None
    publisher: str | None = None
    language: str | None = None
    publication_year: int | None = None
    isbn10: str | None = None
    isbn13: str | None = None
    location: str | None = None
    spine_position: str | None = None
    tags: list = field(default_factory=list)
    confidence: dict = field(default_factory=lambda: dict.fromkeys(('author', 'title', 'publisher', 'isbn', 'overall')))
    provider_matches: list = field(default_factory=list)
    vision: dict | None = None
    detection: dict | None = None
    status: str = 'needs_manual_review'
    calibre_book_id: int | None = None
    notes: str | None = None
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)

    def validate(self):
        if self.detection is not None:
            from .vision.shelf import validate_detection
            validate_detection(self.detection)
            from .vision.shelf import validate_box
            validate_box(self.bounding_box, self.detection['image_width'], self.detection['image_height'], 8)
            if self.detection['kind'] == 'group' and self.status in ('manual_confirmed', 'matched', 'imported'):
                raise ValueError('Eine Buchgruppe muss zuerst in einzelne Bücher aufgeteilt werden.')
        if self.vision is not None:
            from .vision.schema import validate_extraction
            if not isinstance(self.vision, dict) or set(self.vision) != {'provider', 'model', 'extraction', 'usage', 'extracted_at', 'reviewed_at', 'warnings'}:
                raise ValueError('Ungültiger gespeicherter KI-Vorschlag.')
            validate_extraction(self.vision['extraction'])
            if any(not isinstance(self.vision[k], str) for k in ('provider', 'model', 'extracted_at')):
                raise ValueError('Ungültige KI-Quellenangaben.')
            if self.vision['reviewed_at'] is not None and not isinstance(self.vision['reviewed_at'], str):
                raise ValueError('Ungültiger Prüfzeitpunkt.')
            if not isinstance(self.vision['usage'], dict) or any(k not in ('input_tokens', 'output_tokens', 'total_tokens') or type(v) is not int or v < 0 for k, v in self.vision['usage'].items()):
                raise ValueError('Ungültige Tokenzählung.')
            if not isinstance(self.vision['warnings'], list) or any(not isinstance(w, str) for w in self.vision['warnings']):
                raise ValueError('Ungültige KI-Hinweise.')
        for key in ('book_id', 'photo_id', 'title_page_photo_id', 'author', 'title', 'subtitle', 'publisher', 'language',
                    'raw_text', 'location', 'spine_position', 'notes', 'created_at', 'updated_at'):
            value = getattr(self, key)
            if value is not None and not isinstance(value, str):
                raise ValueError('Ungültiges Textfeld: ' + key)
        if not self.book_id or self.status not in STATUSES:
            raise ValueError('Ungültige Buch-ID oder unbekannter Status.')
        for key in ('image_path', 'crop_path', 'title_page_path', 'vision_image_path'):
            if getattr(self, key) is not None:
                relative_path(getattr(self, key))
        if self.publication_year is not None and (type(self.publication_year) is not int or not 1 <= self.publication_year <= 9999):
            raise ValueError('Das Erscheinungsjahr muss zwischen 1 und 9999 liegen.')
        for key, length in (('isbn10', 10), ('isbn13', 13)):
            value = getattr(self, key)
            if value is not None:
                if not isinstance(value, str) or not valid(value) or len(normalize(value)) != length:
                    raise ValueError('Ungültige ' + key.upper() + ': Bitte Prüfziffer und Länge kontrollieren.')
                setattr(self, key, normalize(value))
        if self.isbn10 and self.isbn13 and to_isbn13(self.isbn10) != self.isbn13:
            raise ValueError('ISBN-10 und ISBN-13 gehören nicht zusammen.')
        if not isinstance(self.confidence, dict) or set(self.confidence) != {'author', 'title', 'publisher', 'isbn', 'overall'}:
            raise ValueError('Ungültige Konfidenzfelder.')
        for value in self.confidence.values():
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError('Konfidenzen müssen zwischen 0 und 1 liegen oder null sein.')
        if not isinstance(self.tags, list) or not all(isinstance(t, str) for t in self.tags):
            raise ValueError('Tags müssen eine Liste von Texten sein.')
        if not isinstance(self.provider_matches, list):
            raise ValueError('Ungültige Trefferliste.')
        if self.calibre_book_id is not None and (type(self.calibre_book_id) is not int or self.calibre_book_id < 1):
            raise ValueError('Ungültige Calibre-ID.')
        if self.bounding_box is not None:
            if not isinstance(self.bounding_box, dict) or set(self.bounding_box) != {'x', 'y', 'width', 'height'}:
                raise ValueError('Ungültiger Bildausschnitt.')
            if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in self.bounding_box.values()):
                raise ValueError('Ungültige Bildkoordinaten.')
        if self.status == 'manual_confirmed' and not (self.title and self.title.strip()):
            raise ValueError('Für eine manuelle Bestätigung ist ein Titel erforderlich.')


@dataclass
class Project:
    name: str
    schema_version: int = SCHEMA_VERSION
    project_id: str = field(default_factory=uid)
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    photos: list = field(default_factory=list)
    books: list = field(default_factory=list)

    def validate(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ValueError('Diese Projektversion wird nicht unterstützt. Bitte das Plugin aktualisieren.')
        if not isinstance(self.name, str) or not self.name.strip() or not isinstance(self.project_id, str) or not self.project_id:
            raise ValueError('Projektname oder Projekt-ID fehlt.')
        photo_ids, book_ids = set(), set()
        for photo in self.photos:
            if not isinstance(photo, Photo) or not isinstance(photo.photo_id, str) or not photo.photo_id or photo.photo_id in photo_ids:
                raise ValueError('Ungültige oder doppelte Foto-ID.')
            photo_ids.add(photo.photo_id)
            for key in ('original_name', 'location', 'created_at'):
                if not isinstance(getattr(photo, key), str):
                    raise ValueError('Ungültige Fotometadaten.')
            relative_path(photo.image_path)
            relative_path(photo.preview_path)
            if not re.fullmatch('[a-f0-9]{64}', photo.sha256) or any(type(v) is not int or v <= 0 for v in (photo.width, photo.height)):
                raise ValueError('Ungültige Bildgröße oder Prüfsumme.')
        for book in self.books:
            book.validate()
            if book.book_id in book_ids:
                raise ValueError('Doppelte Buch-ID.')
            book_ids.add(book.book_id)
            if book.photo_id is not None and book.photo_id not in photo_ids:
                raise ValueError('Ein Buch verweist auf ein unbekanntes Foto.')
            if book.title_page_photo_id is not None and book.title_page_photo_id not in photo_ids:
                raise ValueError('Ein Buch verweist auf ein unbekanntes Titelblattfoto.')

    def to_dict(self):
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data.get('schema_version') not in (1, 2, 3, 4, SCHEMA_VERSION):
            raise ValueError('Keine unterstützte Papierbibliothek-Projektdatei (Version 1 bis 5).')
        try:
            values = deepcopy(data)
            values['schema_version'] = SCHEMA_VERSION
            values['photos'] = [Photo(**x) for x in values['photos']]
            values['books'] = [Book(**x) for x in values['books']]
            project = cls(**values)
            project.validate()
            return project
        except (TypeError, KeyError, AttributeError) as exc:
            raise ValueError('Die Projektdatei enthält ungültige oder unbekannte Felder.') from exc
