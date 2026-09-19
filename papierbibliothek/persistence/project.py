import hashlib
import json
import os
from pathlib import Path
import tempfile

from qt.core import QImage

from ..models import Photo, Project, now, relative_path

PROJECT_FILE = 'projekt.json'


def atomic_write(path, data):
    """Replace a file only after its complete content is flushed to disk."""
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / PROJECT_FILE
        self.revision = None

    @classmethod
    def create(cls, root, name):
        store = cls(root)
        project = Project(name=name.strip())
        project.validate()
        store.root.mkdir(parents=True, exist_ok=False)
        (store.root / 'photos').mkdir()
        (store.root / 'previews').mkdir()
        (store.root / 'title_pages').mkdir()
        store.save(project)
        return store, project

    def load(self):
        if self.path.stat().st_size > 50 * 1024 * 1024:
            raise ValueError('Die Projektdatei überschreitet 50 MB.')
        raw = self.path.read_bytes()
        project = Project.from_dict(json.loads(raw.decode('utf-8-sig')))
        self._attach_legacy_title_pages(project)
        project.validate()
        self.revision = hashlib.sha256(raw).hexdigest()
        return project

    def _attach_legacy_title_pages(self, project):
        """Expose title pages created before schema 5 as normal project photos."""
        photos_by_path = {photo.image_path: photo for photo in project.photos}
        for book in project.books:
            if not book.title_page_path or book.title_page_photo_id:
                continue
            photo = photos_by_path.get(book.title_page_path)
            if photo is None:
                try:
                    path = self.asset(book.title_page_path)
                    data = path.read_bytes()
                    image = QImage.fromData(data)
                except (OSError, ValueError):
                    continue
                if image.isNull() or len(data) > 25 * 1024 * 1024:
                    continue
                photo = Photo(
                    original_name='Titelblatt – ' + (book.title or book.book_id),
                    image_path=book.title_page_path,
                    preview_path=book.title_page_path,
                    sha256=hashlib.sha256(data).hexdigest(),
                    width=image.width(), height=image.height(),
                    location=book.location or '', created_at=book.updated_at)
                project.photos.append(photo)
                photos_by_path[book.title_page_path] = photo
            book.title_page_photo_id = photo.photo_id

    def save(self, project):
        if self.path.exists():
            previous = self.path.read_bytes()
            if hashlib.sha256(previous).hexdigest() != self.revision:
                raise ValueError('Das Projekt wurde außerhalb dieses Fensters geändert. Bitte neu öffnen.')
        elif self.revision is not None:
            raise ValueError('Die Projektdatei wurde verschoben oder gelöscht.')
        project.updated_at = now()
        raw = json_bytes(project.to_dict())
        if self.path.exists():
            atomic_write(self.root / 'projekt.backup.json', previous)
        atomic_write(self.path, raw)
        self.revision = hashlib.sha256(raw).hexdigest()

    def asset(self, path):
        relative_path(path)
        result = (self.root / path).resolve()
        if not result.is_relative_to(self.root):
            raise ValueError('Der Bildpfad liegt außerhalb des Projekts.')
        return result
