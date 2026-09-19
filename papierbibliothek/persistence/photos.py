"""Remove photo entries, retaining books and recoverable project assets."""
from copy import deepcopy
from pathlib import PurePosixPath
from uuid import uuid4
import os

from .project import atomic_write, json_bytes
from ..models import now


def remove_photos(store, project, photo_ids):
    ids = set(photo_ids)
    removed = [photo for photo in project.photos if photo.photo_id in ids]
    if not removed or len(removed) != len(ids):
        raise ValueError('Bitte vorhandene Fotos zum Löschen auswählen.')
    candidate = deepcopy(project)
    candidate.photos = [photo for photo in candidate.photos if photo.photo_id not in ids]
    for book in candidate.books:
        changed = False
        if book.photo_id in ids:
            book.photo_id = book.image_path = None
            book.bounding_box = book.detection = None
            changed = True
        if book.title_page_photo_id in ids:
            book.title_page_photo_id = book.title_page_path = None
            changed = True
        if changed:
            book.updated_at = now()
    candidate.validate()

    # Shared images and saved OCR crops remain available to surviving records.
    used = {path for photo in candidate.photos
            for path in (photo.image_path, photo.preview_path)}
    used.update(path for book in candidate.books
                for path in (book.image_path, book.crop_path,
                             book.title_page_path, book.vision_image_path) if path)
    used_files = {store.asset(path) for path in used}
    paths = sorted({path for photo in removed
                    for path in (photo.image_path, photo.preview_path)} - used)
    recycle = '.trash/photos-' + uuid4().hex
    moves = []
    for relative in paths:
        # Never move a manifest or arbitrary file named by an edited project.
        if PurePosixPath(relative).parts[0] not in ('photos', 'previews', 'title_pages'):
            continue
        source = store.asset(relative)
        if source in used_files:
            continue
        if source.relative_to(store.root).parts[0] not in ('photos', 'previews', 'title_pages'):
            raise ValueError('Der Bildpfad verweist nicht auf einen verwalteten Fotoordner.')
        target = store.asset(recycle + '/' + relative)
        moves.append((source, target, relative))
    snapshot = store.asset(recycle + '/projekt.json')
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(snapshot, json_bytes(project.to_dict()))

    # A failed manifest save must never leave the active project without images.
    store.save(candidate)
    warnings = []
    for source, target, relative in moves:
        try:
            if not source.exists():
                continue
            if not source.is_file():
                warnings.append(relative)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
        except OSError:
            warnings.append(relative)
    return candidate, recycle, warnings
