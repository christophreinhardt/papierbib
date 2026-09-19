"""Shelf proposals are saved before review. No automatic bibliographic confirmation."""
from copy import deepcopy

from ..models import Book, now, uid
from ..image_processing.crop import crop_image, jpeg_bytes
from ..persistence.project import atomic_write
from .schema import VisionCancelled
from .shelf import validate_shelf, validate_box, pixel_box, overlap


def save_regions(store, project, photo, image, frame, result, cancel):
    extraction = validate_shelf(result['extraction'])
    validate_box(frame, image.width(), image.height(), 8)
    candidate = deepcopy(project)
    added = duplicates = 0
    warnings = list(extraction['warnings'])
    if extraction['truncated']:
        warnings.append('Erkennung unvollständig (maximal 60 Bereiche). Bitte kleinere Regalabschnitte wählen.')
    for region in extraction['regions']:
        if cancel.is_set():
            raise VisionCancelled('Regal-Erkennung abgebrochen.')
        box = pixel_box(region['box'], frame)
        if min(box['width'], box['height']) < 8:
            warnings.append('Ein Bereich unter 8 Pixeln wurde verworfen. Bitte näher fotografieren.')
            continue
        existing = [b for b in candidate.books if b.photo_id == photo.photo_id and b.bounding_box]
        if any(overlap(box, b.bounding_box) >= 0.7 for b in existing):
            duplicates += 1
            continue
        notes = list(region['warnings']) + warnings
        if any(overlap(box, b.bounding_box) > 0.1 for b in existing):
            notes.append('Überlappung mit einem anderen Rahmen: Grenzen und Buchanzahl prüfen.')
        book = Book(photo_id=photo.photo_id, image_path=photo.image_path,
                    location=photo.location or None, bounding_box=box,
                    status='needs_scan' if region['kind'] == 'group' else 'needs_manual_review')
        book.detection = dict(provider=result['provider'], model=result['model'], confidence=region['confidence'],
                              kind=region['kind'], warnings=notes[:30], detected_at=now(), reviewed_at=None,
                              image_width=image.width(), image_height=image.height())
        write_crop(store, book, image)
        candidate.books.append(book)
        added += 1
    if cancel.is_set():
        raise VisionCancelled('Regal-Erkennung abgebrochen.')
    store.save(candidate)
    return {'project': candidate, 'shelf_saved': photo.photo_id, 'added': added,
            'duplicates': duplicates, 'warnings': warnings}


def write_crop(store, book, image):
    validate_box(book.bounding_box, image.width(), image.height(), 8)
    relative = 'crops/' + uid() + '.jpg'
    path = store.asset(relative)
    path.parent.mkdir(exist_ok=True)
    atomic_write(path, jpeg_bytes(crop_image(image, book.bounding_box)))
    book.crop_path = relative


def save_corrections(store, original, candidate, photo, image, cancel):
    old = {b.book_id: b for b in original.books}
    for book in candidate.books:
        if cancel.is_set():
            raise VisionCancelled('Rahmenkorrektur abgebrochen.')
        if book.photo_id != photo.photo_id or not book.bounding_box:
            continue
        previous = old.get(book.book_id)
        if previous is None or previous.bounding_box != book.bounding_box:
            write_crop(store, book, image)
            book.vision = None
            book.confidence = dict.fromkeys(book.confidence)
            if book.status != 'rejected':
                book.status = 'needs_scan' if book.detection and book.detection['kind'] == 'group' else 'needs_manual_review'
            book.updated_at = now()
    if cancel.is_set():
        raise VisionCancelled('Rahmenkorrektur abgebrochen.')
    store.save(candidate)
    return {'project': candidate, 'regions_edited': True}
