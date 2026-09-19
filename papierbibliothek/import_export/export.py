import csv
import io
import json
from pathlib import Path

from ..persistence.project import atomic_write, json_bytes

CSV_FIELDS = ('book_id', 'title', 'author', 'subtitle', 'publisher', 'publication_year',
              'language', 'isbn10', 'isbn13', 'tags', 'location', 'spine_position',
              'status', 'confidence', 'photo_id', 'image_path', 'notes', 'raw_text',
              'crop_path', 'title_page_path', 'title_page_photo_id',
              'vision_image_path', 'bounding_box', 'detection')


def safe_cell(value):
    """Prevent spreadsheet formula execution; JSON remains lossless."""
    text = '' if value is None else str(value)
    if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def export_project(project, path, kind, project_root=None):
    project.validate()
    path = Path(path).resolve()
    if project_root is not None:
        # Export into a dedicated folder; never overwrite manifests or managed images.
        root = Path(project_root).resolve()
        if path.is_relative_to(root) and not path.is_relative_to(root / 'exports'):
            raise ValueError('Im Projekt bitte ausschließlich in den Unterordner exports exportieren.')
    if kind == 'json':
        content = json_bytes(project.to_dict())
    elif kind == 'csv':
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, delimiter=';')
        writer.writeheader()
        for book in project.books:
            row = {key: getattr(book, key) for key in CSV_FIELDS}
            row['tags'] = ' | '.join(book.tags)
            row['confidence'] = book.confidence.get('overall')
            for key in ('bounding_box', 'detection'):
                row[key] = json.dumps(row[key], ensure_ascii=False) if row[key] is not None else None
            writer.writerow({key: safe_cell(value) for key, value in row.items()})
        content = stream.getvalue().encode('utf-8-sig')
    else:
        raise ValueError('Unbekanntes Exportformat.')
    atomic_write(path, content)
