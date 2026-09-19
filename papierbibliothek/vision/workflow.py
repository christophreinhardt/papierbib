from copy import deepcopy

from ..models import Book, now, uid
from ..isbn import valid, normalize, to_isbn13
from ..persistence.project import atomic_write
from .schema import validate_extraction, VisionError, VisionCancelled, FIELDS


def save_proposal(store, project, photo, jpeg, box, result, cancel, book_id=None,
                  title_page=False):
    if cancel.is_set():
        raise VisionCancelled('Auswertung abgebrochen.')
    result = deepcopy(result)
    result['extraction'] = validate_extraction(result['extraction'])
    candidate = deepcopy(project)
    book = next((b for b in candidate.books if b.book_id == book_id), None) if book_id else None
    if book_id and book is None:
        raise VisionError('Der zu prüfende Buchdatensatz fehlt.')
    if title_page and book is None:
        raise VisionError('Für die Titelblatt-Auswertung fehlt der Buchdatensatz.')
    if book is None:
        book = Book(photo_id=photo.photo_id, image_path=photo.image_path, location=photo.location or None)
        candidate.books.append(book)
    if not title_page:
        book.photo_id, book.image_path = photo.photo_id, photo.image_path
    relative = 'crops/' + uid() + '.jpg'
    path = store.asset(relative)
    path.parent.mkdir(exist_ok=True)
    atomic_write(path, jpeg)
    result['extracted_at'] = now()
    result['reviewed_at'] = None
    result['warnings'] = []
    for key in ('isbn10', 'isbn13'):
        value = result['extraction']['fields'][key]
        if value and (not valid(value) or len(normalize(value)) != (10 if key == 'isbn10' else 13)):
            result['warnings'].append('Erkannte ' + key.upper() + ' hat eine ungültige Prüfziffer. Bitte am Buch prüfen.')
    book.vision = result
    if not title_page and book.detection and book.bounding_box != box:
        book.detection.update(confidence=None, reviewed_at=None)
    book.vision_image_path = relative
    if not title_page:
        book.crop_path, book.bounding_box = relative, deepcopy(box)
    book.status = 'needs_scan' if result['extraction']['readability'] in ('unreadable', 'multiple_books') else 'needs_manual_review'
    book.updated_at = now()
    try:
        store.save(candidate)
    except Exception:
        # Keep the orphaned crop for recovery; never delete originals or old crops.
        raise
    return {'project': candidate, 'review_book_id': book.book_id}


def apply_review(book, values, confirm=True, status=None):
    """Apply ONLY explicitly selected fields. Preserve the original extraction for comparison."""
    candidate = deepcopy(book)
    if not candidate.vision:
        raise VisionError('Kein KI-Vorschlag vorhanden.')
    for key, value in values.items():
        if key not in FIELDS:
            raise VisionError('Unbekanntes Metadatenfeld.')
        setattr(candidate, key, value)
    if 'isbn10' in values and candidate.isbn10 and not candidate.isbn13:
        candidate.isbn13 = to_isbn13(candidate.isbn10)
    extracted = candidate.vision['extraction']
    for key in ('author', 'title', 'publisher'):
        if key in values:
            candidate.confidence[key] = extracted['field_confidence'][key] if values[key] == extracted['fields'][key] else None
    if set(values) & {'isbn10', 'isbn13'}:
        matches = [extracted['field_confidence'][key] for key in ('isbn10', 'isbn13')
                   if key in values and values[key] is not None and values[key] == extracted['fields'][key]]
        candidate.confidence['isbn'] = min(matches) if matches else None
    candidate.confidence['overall'] = None  # Human-reviewed metadata has no calibrated overall score.
    candidate.vision['reviewed_at'] = now()
    candidate.updated_at = now()
    status = status or ('manual_confirmed' if confirm else 'needs_scan')
    if status not in ('manual_confirmed', 'needs_manual_review', 'needs_scan'):
        raise VisionError('Unzulässiger Prüfstatus.')
    candidate.status = status
    candidate.validate()
    return candidate
