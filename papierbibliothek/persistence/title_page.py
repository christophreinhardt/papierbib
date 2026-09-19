"""Atomic local persistence for cropped title-page camera images."""
from copy import deepcopy
from uuid import uuid4
import hashlib
from qt.core import QImage

from .project import atomic_write
from ..models import Photo, now


def save_title_page(store, project, book_id, jpeg):
    image = QImage.fromData(jpeg, 'JPEG') if isinstance(jpeg, bytes) else QImage()
    if (not isinstance(jpeg, bytes) or not jpeg.startswith(b'\xff\xd8') or
            image.isNull()):
        raise ValueError('Das zugeschnittene Titelblatt ist kein gültiges JPEG-Bild.')
    if len(jpeg) > 25 * 1024 * 1024:
        raise ValueError('Das zugeschnittene Titelblatt überschreitet 25 MB.')
    candidate = deepcopy(project)
    book = next((item for item in candidate.books if item.book_id == book_id), None)
    if book is None:
        raise ValueError('Der ausgewählte Buchdatensatz ist nicht mehr vorhanden.')
    relative = 'title_pages/%s-%s.jpg' % (book_id, uuid4().hex)
    target = store.asset(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, jpeg)
    book.title_page_path = relative
    photo = next((item for item in candidate.photos
                  if item.photo_id == book.title_page_photo_id), None)
    if photo is None:
        photo = Photo()
        candidate.photos.append(photo)
    photo.original_name = 'Titelblatt – ' + (book.title or book.book_id)
    photo.image_path = relative
    photo.preview_path = relative
    photo.sha256 = hashlib.sha256(jpeg).hexdigest()
    photo.width = image.width()
    photo.height = image.height()
    photo.location = book.location or ''
    book.title_page_photo_id = photo.photo_id
    book.updated_at = now()
    try:
        store.save(candidate)
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return candidate
