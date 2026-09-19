from copy import deepcopy

from qt.core import (QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QComboBox,
                     QPlainTextEdit, QVBoxLayout, QLabel, QMessageBox, QGraphicsView,
                     QGraphicsScene, QPixmap, QPainter, Qt)

from ..models import Book, MANUAL_STATUSES, STATUSES, now
from ..isbn import to_isbn13


class PhotoView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setMinimumSize(320, 220)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAccessibleName('Regalfoto: Mausrad zum Zoomen, Ziehen zum Verschieben')

    def show_photo(self, path=None):
        self.scene().clear()
        self.resetTransform()
        if path is None:
            self.scene().addText('Foto auswählen oder importieren')
        else:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self.scene().addText('Bilddatei fehlt oder ist nicht lesbar.')
            else:
                self.scene().addPixmap(pixmap)
        self.scene().setSceneRect(self.scene().itemsBoundingRect())
        self.fit_photo()

    def fit_photo(self):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_photo()

    def show_image(self, image):
        self.scene().clear()
        self.resetTransform()
        self.scene().addPixmap(QPixmap.fromImage(image))
        self.scene().setSceneRect(self.scene().itemsBoundingRect())
        self.fit_photo()

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        scale = self.transform().m11() * factor
        if 0.02 <= scale <= 30:
            self.scale(factor, factor)
        event.accept()


class BookDialog(QDialog):
    def __init__(self, project, book=None, photo_id=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Buch bearbeiten' if book else 'Buchdatensatz manuell anlegen')
        self.resize(590, 710)
        self.book = deepcopy(book) if book else Book(photo_id=photo_id)
        self.project = project
        layout = QVBoxLayout(self)
        hint = QLabel('Unbekannte Felder können leer bleiben. Mehrere Autoren mit & trennen.\n'
                      'Jeder Datensatz steht für ein physisches Exemplar.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        self.photo = QComboBox()
        self.photo.addItem('Kein Foto', None)
        for item in project.photos:
            self.photo.addItem(item.original_name + (' · ' + item.location if item.location else ''), item.photo_id)
        self.photo.setCurrentIndex(max(0, self.photo.findData(self.book.photo_id)))
        form.addRow('Regalfoto', self.photo)
        self.fields = {}
        for key, label in (('title', 'Titel'), ('author', 'Autor(en)'), ('subtitle', 'Untertitel'),
                           ('publisher', 'Verlag'), ('publication_year', 'Erscheinungsjahr'),
                           ('language', 'Sprache'), ('isbn10', 'ISBN-10'), ('isbn13', 'ISBN-13'),
                           ('location', 'Regal / Fach'), ('spine_position', 'Position (z. B. 5 von links)'),
                           ('tags', 'Tags (durch Komma getrennt)')):
            value = getattr(self.book, key)
            text = ', '.join(value) if key == 'tags' else ('' if value is None else str(value))
            self.fields[key] = QLineEdit(text)
            form.addRow(label, self.fields[key])
        if book is None and photo_id:
            photo = next((p for p in project.photos if p.photo_id == photo_id), None)
            if photo:
                self.fields['location'].setText(photo.location)
        self.status = QComboBox()
        for key in MANUAL_STATUSES:
            self.status.addItem(STATUSES[key], key)
        if self.book.status not in MANUAL_STATUSES:
            self.status.addItem(STATUSES[self.book.status], self.book.status)
        self.status.setCurrentIndex(self.status.findData(self.book.status))
        form.addRow('Bearbeitungsstatus', self.status)
        self.notes = QPlainTextEdit(self.book.notes or '')
        self.notes.setMaximumHeight(75)
        form.addRow('Notizen', self.notes)
        self.raw_text = QPlainTextEdit(self.book.raw_text or '')
        self.raw_text.setMaximumHeight(65)
        form.addRow('Abgelesener Text', self.raw_text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Speichern')
        buttons.button(QDialogButtonBox.StandardButton.Save).setDefault(True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Abbrechen')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        candidate = deepcopy(self.book)
        try:
            for key, widget in self.fields.items():
                value = widget.text().strip()
                if key == 'publication_year':
                    if value and not value.isdecimal():
                        raise ValueError('Bitte ein gültiges Erscheinungsjahr eingeben.')
                    value = int(value) if value else None
                elif key == 'tags':
                    value = list(dict.fromkeys(x.strip() for x in value.split(',') if x.strip()))
                else:
                    value = value or None
                setattr(candidate, key, value)
            candidate.photo_id = self.photo.currentData()
            photo = next((p for p in self.project.photos if p.photo_id == candidate.photo_id), None)
            candidate.image_path = photo.image_path if photo else None
            if candidate.photo_id != self.book.photo_id:
                candidate.crop_path = None
                candidate.bounding_box = None
                candidate.vision = None
                candidate.detection = None
                candidate.confidence = dict.fromkeys(candidate.confidence)
            candidate.status = self.status.currentData()
            candidate.notes = self.notes.toPlainText().strip() or None
            candidate.raw_text = self.raw_text.toPlainText().strip() or None
            candidate.updated_at = now()
            for key in ('author', 'title', 'publisher'):
                if getattr(candidate, key) != getattr(self.book, key):
                    candidate.confidence[key] = None
                    candidate.confidence['overall'] = None
            if (candidate.isbn10, candidate.isbn13) != (self.book.isbn10, self.book.isbn13):
                candidate.confidence['isbn'] = candidate.confidence['overall'] = None
            if candidate.vision and candidate.status == 'manual_confirmed':
                candidate.vision['reviewed_at'] = now()
            candidate.validate()
            if candidate.isbn10 and not candidate.isbn13:
                candidate.isbn13 = to_isbn13(candidate.isbn10)
            canonical = candidate.isbn13
            if canonical and any(
                    other.book_id != candidate.book_id and
                    (other.isbn13 or (to_isbn13(other.isbn10) if other.isbn10 else None)) == canonical
                    for other in self.project.books):
                raise ValueError('Diese ISBN ist bereits einem anderen Buchdatensatz im Projekt zugeordnet.')
            candidate.validate()
        except ValueError as exc:
            QMessageBox.warning(self, 'Eingabe prüfen', str(exc))
            return
        self.book = candidate
        super().accept()
