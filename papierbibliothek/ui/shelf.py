from copy import deepcopy

from qt.core import (QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QLabel,
                     QListWidget, QListWidgetItem, QPushButton, QSplitter, QMessageBox,
                     QRectF, Qt, QPen, QColor, QGraphicsItem, QAbstractItemView,
                     QItemSelectionModel)

from ..models import Book, now
from ..vision.shelf import validate_box, overlap
from .vision import CropView


def draw_regions(view, books, width, height, selected=None):
    """Draw boxes in the EXIF-oriented original coordinate frame, scaled to this view."""
    rect = view.sceneRect()
    selected = {selected} if isinstance(selected, str) else set(selected or ())
    for index, book in enumerate(books, 1):
        box = book.bounding_box
        if not box:
            continue
        color = '#888888' if book.status == 'rejected' else '#d05713'
        if book.detection and book.detection['kind'] == 'group':
            color = '#b62030'
        if book.book_id in selected:
            color = '#007cba'
        pen = QPen(QColor(color), 3)
        pen.setCosmetic(True)
        x, y = box['x'] * rect.width()/width, box['y'] * rect.height()/height
        item = view.scene().addRect(x, y, box['width']*rect.width()/width, box['height']*rect.height()/height, pen)
        item.setToolTip(f'{index}: ' + (book.title or 'Noch nicht ausgewertet'))
        label = view.scene().addSimpleText(str(index))
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        label.setBrush(QColor(color))
        label.setPos(x, y)
    view.scene().setSceneRect(rect)


class RegionsDialog(QDialog):
    def __init__(self, project, photo, image, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Buchrücken-Rahmen prüfen und korrigieren')
        self.resize(1140, 760)
        self.project = deepcopy(project)
        self.photo, self.image = photo, image
        layout = QVBoxLayout(self)
        hint = QLabel('Erkannte Bereiche sind zur Übernahme angehakt; falsch erkannte Rücken durch Entfernen des Hakens ausschließen.\n'
                      'Rahmen in der Liste oder direkt im Foto anklicken; Strg/Umschalt ermöglicht Mehrfachauswahl. Zum Korrigieren einen neuen Rahmen ziehen und „Rahmen ersetzen“ drücken.\n'
                      'Fehlende Bücher: Rahmen ziehen, dann hinzufügen. Rot: untrennbare Gruppe. Orange: ungeprüft. Blau: ausgewählt.\n'
                      'Eine Rahmenbestätigung bestätigt keine Metadaten. Keine Bildübertragung in dieser Ansicht.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.view = CropView(image)
        self.regions = QListWidget()
        self.regions.setMinimumWidth(240)
        self.regions.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.regions.itemSelectionChanged.connect(self.select)
        self.regions.itemChanged.connect(self.toggle_included)
        self.view.clicked.connect(self.select_at)
        split.addWidget(self.view)
        split.addWidget(self.regions)
        split.setSizes([820, 280])
        layout.addWidget(split, 1)
        self.info = QLabel()
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        row = QHBoxLayout()
        layout.addLayout(row)
        for text, callback in [('Rahmen ersetzen', self.replace), ('Buch hinzufügen', self.add),
                               ('Gruppe / Einzelbuch', self.toggle_group), ('Auswahl bestätigen', self.confirm),
                               ('Auswahl ein-/ausschließen', self.ignore), ('Einpassen', self.view.fit_photo)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def books(self):
        return [b for b in self.project.books if b.photo_id == self.photo.photo_id and b.bounding_box]

    def current(self):
        item = self.regions.currentItem()
        book_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((book for book in self.books() if book.book_id == book_id), None)

    def selected_books(self):
        ids = {item.data(Qt.ItemDataRole.UserRole) for item in self.regions.selectedItems()}
        return [book for book in self.books() if book.book_id in ids]

    def refresh(self, selected=None):
        if isinstance(selected, str):
            selected_ids = {selected}
        else:
            selected_ids = set(selected or (book.book_id for book in self.selected_books()))
        current_id = self.current().book_id if self.current() else None
        self.regions.blockSignals(True)
        self.regions.clear()
        for index, book in enumerate(self.books(), 1):
            detection = book.detection
            kind = 'Gruppe' if detection and detection['kind'] == 'group' else 'Buch'
            score = f" · {detection['confidence']:.0%}" if detection and detection['confidence'] is not None else ''
            checked = ' · Rahmen geprüft' if detection and detection['reviewed_at'] else ''
            state = ' · ignoriert' if book.status == 'rejected' else checked
            item = QListWidgetItem(f'{index}. {book.title or kind}{score}{state}')
            item.setData(Qt.ItemDataRole.UserRole, book.book_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if book.status == 'rejected' else Qt.CheckState.Checked)
            self.regions.addItem(item)
            if book.book_id in selected_ids:
                item.setSelected(True)
            if book.book_id == current_id:
                self.regions.setCurrentItem(item, QItemSelectionModel.SelectionFlag.NoUpdate)
        if self.regions.currentRow() < 0 and self.regions.count():
            self.regions.setCurrentRow(0)
        self.regions.blockSignals(False)
        self.select()

    def select(self, *args):
        book = self.current()
        self.view.overlay = None
        self.view.show_image(self.image)
        draw_regions(self.view, self.books(), self.image.width(), self.image.height(),
                     [item.book_id for item in self.selected_books()])
        self.view.set_selection(QRectF())
        if book:
            box = book.bounding_box
            self.view.set_selection(QRectF(box['x'], box['y'], box['width'], box['height']))
            pen = QPen(QColor('#007cba'), 3)
            pen.setCosmetic(True)
            self.view.overlay.setPen(pen)
            warnings = list(book.detection['warnings']) if book.detection else []
            if any(other.book_id != book.book_id and overlap(box, other.bounding_box) > 0.1 for other in self.books()):
                warnings.append('Überlappende Rahmen: bitte Buchgrenzen prüfen.')
            self.info.setText(f"x={box['x']}, y={box['y']}, Breite={box['width']}, Höhe={box['height']} (Pixel im gedrehten Original)\n" + '\n'.join(warnings))
        else:
            self.info.setText('Noch keine Bereiche. Einen Rahmen ziehen und Buch hinzufügen.')

    def select_at(self, point, additive=False):
        matches = []
        for book in self.books():
            box = book.bounding_box
            rect = QRectF(box['x'], box['y'], box['width'], box['height'])
            if rect.contains(point):
                matches.append((box['width'] * box['height'], book.book_id))
        if not matches:
            return
        book_id = min(matches)[1]
        for row in range(self.regions.count()):
            item = self.regions.item(row)
            if item.data(Qt.ItemDataRole.UserRole) != book_id:
                continue
            if not additive:
                self.regions.clearSelection()
                item.setSelected(True)
            else:
                item.setSelected(not item.isSelected())
            self.regions.setCurrentItem(item, QItemSelectionModel.SelectionFlag.NoUpdate)
            self.select()
            return

    def toggle_included(self, item):
        book_id = item.data(Qt.ItemDataRole.UserRole)
        book = next((book for book in self.books() if book.book_id == book_id), None)
        if not book:
            return
        included = item.checkState() == Qt.CheckState.Checked
        book.status = ('needs_scan' if book.detection and book.detection['kind'] == 'group'
                       else 'needs_manual_review') if included else 'rejected'
        book.updated_at = now()
        self.select()

    def detection(self, book):
        if not book.detection:
            book.detection = dict(provider='manual', model='', confidence=None, kind='spine', warnings=[],
                                  detected_at=now(), reviewed_at=None, image_width=self.image.width(), image_height=self.image.height())
        return book.detection

    def selection(self):
        try:
            return validate_box(self.view.box(), self.image.width(), self.image.height(), 8)
        except ValueError as exc:
            QMessageBox.warning(self, 'Rahmen prüfen', str(exc))
            return None

    def replace(self):
        book = self.current()
        box = self.selection()
        if book and box:
            book.bounding_box = box
            self.detection(book).update(confidence=None, reviewed_at=None)
            self.refresh(book.book_id)

    def add(self):
        box = self.selection()
        if box:
            if any(overlap(box, b.bounding_box) >= 0.7 for b in self.books()):
                QMessageBox.warning(self, 'Doppelter Bereich', 'Hier existiert bereits ein Rahmen. Bitte diesen auswählen und korrigieren.')
                return
            book = Book(photo_id=self.photo.photo_id, image_path=self.photo.image_path,
                        location=self.photo.location or None, bounding_box=box)
            self.detection(book)
            self.project.books.append(book)
            self.refresh(book.book_id)

    def toggle_group(self):
        book = self.current()
        if book:
            detection = self.detection(book)
            detection['kind'] = 'spine' if detection['kind'] == 'group' else 'group'
            detection['reviewed_at'] = None
            book.status = 'needs_scan' if detection['kind'] == 'group' else 'needs_manual_review'
            self.refresh()

    def confirm(self):
        books = self.selected_books() or ([self.current()] if self.current() else [])
        for book in books:
            self.detection(book)['reviewed_at'] = now()
            book.updated_at = now()
        if books:
            self.refresh([book.book_id for book in books])

    def ignore(self):
        books = self.selected_books() or ([self.current()] if self.current() else [])
        if books:
            include = all(book.status == 'rejected' for book in books)
            for book in books:
                book.status = (('needs_scan' if book.detection and book.detection['kind'] == 'group'
                                else 'needs_manual_review') if include else 'rejected')
                book.updated_at = now()
            self.refresh([book.book_id for book in books])
