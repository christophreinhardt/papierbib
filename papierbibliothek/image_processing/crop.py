from qt.core import QImage, QPainter, QRect, QTransform, QSize, Qt, QByteArray, QBuffer, QIODevice


def crop_image(image, box, rotation=0, max_edge=2400):
    if set(box) != {'x', 'y', 'width', 'height'} or any(type(v) is not int for v in box.values()):
        raise ValueError('Ungültiger Bildausschnitt.')
    x, y, w, h = (box[k] for k in ('x', 'y', 'width', 'height'))
    if min(x, y) < 0 or min(w, h) < 8 or x + w > image.width() or y + h > image.height():
        raise ValueError('Bitte einen gültigen Ausschnitt mit mindestens 8 × 8 Pixeln auswählen.')
    if rotation not in (0, 90, 180, 270):
        raise ValueError('Ungültige Drehung.')
    target = QSize(w, h)
    if max_edge is not None and max(w, h) > max_edge:
        target.scale(QSize(max_edge, max_edge), Qt.AspectRatioMode.KeepAspectRatio)
    # Fresh pixel-only image: no EXIF, GPS, source text or filenames are uploaded.
    clean = QImage(target, QImage.Format.Format_RGB32)
    clean.fill(Qt.GlobalColor.white)
    painter = QPainter(clean)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QRect(0, 0, target.width(), target.height()), image, QRect(x, y, w, h))
    painter.end()
    return clean.transformed(QTransform().rotate(rotation)) if rotation else clean


def jpeg_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'JPEG', 93):
        raise ValueError('Ausschnitt konnte nicht als JPEG erstellt werden.')
    buffer.close()
    return bytes(data)
