"""Strict provider-neutral extraction contract. Model confidence is not a probability guarantee."""
from copy import deepcopy
import json
import math

FIELDS = ('title', 'author', 'subtitle', 'publisher', 'language', 'publication_year', 'isbn10', 'isbn13', 'raw_text')
LABELS = dict(zip(FIELDS, ('Titel', 'Autor(en)', 'Untertitel', 'Verlag', 'Sprache', 'Jahr', 'ISBN-10', 'ISBN-13', 'Abgelesener Text')))


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


EXTRACTION_SCHEMA = object_schema({
    'fields': object_schema({key: {'type': ['integer' if key == 'publication_year' else 'string', 'null']} for key in FIELDS}),
    'field_confidence': object_schema({key: {'type': ['number', 'null']} for key in FIELDS}),
    'overall': {'type': 'number'},
    'readability': {'type': 'string', 'enum': ['readable', 'partial', 'unreadable', 'multiple_books']},
    'warnings': {'type': 'array', 'items': {'type': 'string'}},
})


class VisionError(ValueError):
    """Only safe, user-facing messages; never include raw responses or credentials."""


class VisionCancelled(VisionError):
    pass


def strict_json(text):
    def pairs(values):
        data = {}
        for key, value in values:
            if key in data:
                raise ValueError('duplicate key')
            data[key] = value
        return data
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError, TypeError, RecursionError):
        raise VisionError('Die KI-Antwort enthält kein gültiges eindeutiges JSON.') from None


def validate_extraction(data):
    def keys(obj, expected):
        if not isinstance(obj, dict) or set(obj) != set(expected):
            raise VisionError('Die KI-Antwort entspricht nicht dem erwarteten Schema.')
    keys(data, EXTRACTION_SCHEMA['properties'])
    keys(data['fields'], FIELDS)
    keys(data['field_confidence'], FIELDS)
    for key, value in data['fields'].items():
        if value is None:
            if data['field_confidence'][key] is not None:
                raise VisionError('Konfidenz für ein unbekanntes Feld muss null sein.')
        elif key == 'publication_year':
            if type(value) is not int or not 1 <= value <= 9999:
                raise VisionError('Die KI hat ein ungültiges Jahr geliefert.')
        elif not isinstance(value, str) or not value.strip() or len(value) > 12000:
            raise VisionError('Die KI hat ein ungültiges Textfeld geliefert.')
        confidence = data['field_confidence'][key]
        if value is not None and confidence is None:
            raise VisionError('Für ein erkanntes Feld fehlt die Konfidenz.')
        if confidence is not None and (type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise VisionError('Ungültige KI-Konfidenz.')
    overall = data['overall']
    if type(overall) not in (int, float) or not math.isfinite(overall) or not 0 <= overall <= 1:
        raise VisionError('Ungültige Gesamt-Konfidenz.')
    if not isinstance(data['readability'], str) or data['readability'] not in EXTRACTION_SCHEMA['properties']['readability']['enum']:
        raise VisionError('Ungültige Lesbarkeitsangabe.')
    if not isinstance(data['warnings'], list) or len(data['warnings']) > 30 or any(not isinstance(w, str) or len(w) > 2000 for w in data['warnings']):
        raise VisionError('Ungültige Hinweise in der KI-Antwort.')
    return deepcopy(data)


def extraction_from_response(response, validator=validate_extraction):
    if not isinstance(response, dict):
        raise VisionError('Ungültige API-Antwort.')
    if response.get('status') != 'completed':
        raise VisionError('Die KI-Auswertung wurde nicht vollständig beendet. Bitte erneut versuchen oder das Modell ändern.')
    texts = []
    try:
        for item in response.get('output', []):
            if item.get('type') != 'message':
                continue
            for content in item.get('content', []):
                if content.get('type') == 'refusal':
                    raise VisionError('Das Modell hat die Auswertung abgelehnt. Bitte einen anderen Ausschnitt wählen.')
                if content.get('type') == 'output_text':
                    texts.append(content['text'])
        if len(texts) != 1 or not isinstance(texts[0], str):
            raise VisionError('Die API lieferte kein eindeutiges Textergebnis.')
        return validator(strict_json(texts[0]))
    except (KeyError, AttributeError, TypeError):
        raise VisionError('Die API-Antwort hat ein unerwartetes Format.') from None
