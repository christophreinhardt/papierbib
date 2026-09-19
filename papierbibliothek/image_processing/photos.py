import hashlib
import os
from pathlib import Path
import tempfile

from qt.core import QImageReader, QSize, Qt

from ..models import Photo, uid

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'}
MAX_PIXELS = 120_000_000


class Cancelled(Exception):
    pass


def discover(inputs, cancel):
    """Yield paths lazily; do not follow directory symlinks."""
    seen = set()
    for entry in inputs:
        path = Path(entry)
        if path.is_dir():
            for directory, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not Path(directory, d).is_symlink())
                for name in sorted(files):
                    if cancel.is_set():
                        return
                    candidate = Path(directory, name)
                    if candidate.suffix.lower() in EXTENSIONS and candidate.resolve() not in seen:
                        seen.add(candidate.resolve())
                        yield candidate
        elif path.resolve() not in seen:
            seen.add(path.resolve())
            yield path


def read_image(path, max_edge=2400):
    reader = QImageReader(str(path))
    try:
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > MAX_PIXELS:
            raise ValueError('Bild ist nicht lesbar oder überschreitet 120 Megapixel. HEIC bitte bei Bedarf als JPEG exportieren.')
        if max_edge is not None and max(size.width(), size.height()) > max_edge:
            reader.setScaledSize(size.scaled(QSize(max_edge, max_edge), Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            raise ValueError('Bild konnte nicht gelesen werden: ' + reader.errorString())
        return image, size
    finally:
        # Tracebacks can keep a reader alive; release its file before unlink on Windows.
        reader.setFileName('')


def import_photo(store, source, known_hashes, location, cancel):
    """Copy bytes, hash and decode in a worker. Preserve the original unchanged."""
    if cancel.is_set():
        raise Cancelled()
    source = Path(source)
    if source.suffix.lower() not in EXTENSIONS:
        raise ValueError('Dieses Bildformat wird nicht unterstützt.')
    token = uid()
    target = store.asset('photos/' + token + source.suffix.lower())
    preview = store.asset('previews/' + token + '.jpg')
    target.parent.mkdir(exist_ok=True)
    preview.parent.mkdir(exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.import-', dir=target.parent)
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, 'wb') as output, source.open('rb') as original:
            while chunk := original.read(1024 * 1024):
                if cancel.is_set():
                    raise Cancelled()
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest() in known_hashes:
            return None
        image, size = read_image(temp)
        if cancel.is_set():
            raise Cancelled()
        if not image.save(str(preview), 'JPEG', 90):
            raise OSError('Die Bildvorschau konnte nicht gespeichert werden.')
        os.replace(temp, target)
        return Photo(photo_id=token, original_name=source.name,
                     image_path=target.relative_to(store.root).as_posix(),
                     preview_path=preview.relative_to(store.root).as_posix(),
                     sha256=digest.hexdigest(), width=size.width(), height=size.height(), location=location)
    except Exception:
        # Only remove files created by this attempt, never source images.
        preview.unlink(missing_ok=True)
        raise
    finally:
        Path(temp).unlink(missing_ok=True)


def import_batch(store, project, inputs, location, cancel, progress):
    imported = duplicates = 0
    errors = []
    known = {photo.sha256 for photo in project.photos}
    for index, path in enumerate(discover(inputs, cancel), 1):
        if cancel.is_set():
            break
        try:
            photo = import_photo(store, path, known, location, cancel)
        except Cancelled:
            break
        except (OSError, ValueError) as exc:
            errors.append(f'{path.name}: {exc}')
            progress(f'{index} Dateien bearbeitet · {imported} importiert · {len(errors)} Fehler')
            continue
        if photo is None:
            duplicates += 1
        else:
            project.photos.append(photo)
            try:
                store.save(project)
            except Exception:
                project.photos.pop()
                raise
            known.add(photo.sha256)
            imported += 1
        progress(f'{index} Dateien bearbeitet · {imported} importiert · {duplicates} doppelt')
    return {'imported': imported, 'duplicates': duplicates, 'errors': errors, 'cancelled': cancel.is_set()}
