"""Deterministic, image-free exports for the existing Calibre plugin."""
import csv
import io
import json


CONFIDENCE_KEYS = ('author', 'title', 'publisher', 'isbn', 'overall')
CSV_FIELDS = ('book_id', 'title', 'author', 'subtitle', 'publisher',
              'publication_year', 'language', 'isbn10', 'isbn13', 'status',
              'confidence', 'notes', 'raw_text')


def _confidence(record):
    result = ((record.get('vision') or {}).get('result') or {})
    values = result.get('confidence') if isinstance(result, dict) else None
    values = values if isinstance(values, dict) else {}
    return {key: values.get(key) if key in values else None for key in CONFIDENCE_KEYS}


def _status(value):
    return {'confirmed': 'manual_confirmed', 'draft': 'needs_manual_review',
            'needs_scan': 'needs_scan'}.get(value, 'needs_manual_review')


def _book(record):
    vision_result = ((record.get('vision') or {}).get('result') or {})
    raw_text = vision_result.get('raw_text') if isinstance(vision_result, dict) else None
    return {
        'book_id': record['book_id'], 'photo_id': None, 'image_path': None,
        'crop_path': None, 'title_page_path': None,
        'title_page_photo_id': None, 'vision_image_path': None,
        'bounding_box': None, 'raw_text': raw_text,
        'author': '; '.join(record.get('authors') or []) or None,
        'title': record.get('title'), 'subtitle': record.get('subtitle'),
        'publisher': record.get('publisher'), 'language': record.get('language'),
        'publication_year': record.get('publication_year'),
        'isbn10': record.get('isbn10'), 'isbn13': record.get('isbn13'),
        'location': None, 'spine_position': None, 'tags': ['Papierbuch', 'Mobil erfasst'],
        'confidence': _confidence(record), 'provider_matches': [],
        'vision': None, 'detection': None, 'status': _status(record.get('status')),
        'calibre_book_id': None, 'notes': record.get('notes'),
        'created_at': record.get('created_at') or record.get('updated_at'),
        'updated_at': record.get('updated_at') or record.get('created_at'),
    }


def calibre_project(project, records):
    return {
        'name': project['name'], 'schema_version': 5,
        'project_id': project['project_id'],
        'created_at': project['created_at'], 'updated_at': project['updated_at'],
        'photos': [], 'books': [_book(record) for record in records],
    }


def json_export(project, records):
    return (json.dumps(calibre_project(project, records), ensure_ascii=False,
                       indent=2, allow_nan=False) + '\n').encode('utf-8')


def csv_export(records):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, delimiter=';')
    writer.writeheader()
    for record in records:
        book = _book(record)
        row = {key: book[key] for key in CSV_FIELDS}
        row['confidence'] = book['confidence']['overall']
        for key, value in row.items():
            text = '' if value is None else str(value)
            if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
                row[key] = "'" + text
        writer.writerow(row)
    return stream.getvalue().encode('utf-8-sig')
