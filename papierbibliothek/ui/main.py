from copy import deepcopy
from pathlib import Path
import threading
import os

from qt.core import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog,
                     QInputDialog, QMessageBox, QListWidget, QListWidgetItem, QSplitter,
                     QWidget, QTableWidget, QTableWidgetItem, QLineEdit, QComboBox,
                     QHeaderView, QAbstractItemView, QProgressBar, QThread, pyqtSignal,
                     QLockFile, Qt, QRectF, QTimer)

from ..models import Book, STATUSES
from ..persistence.project import ProjectStore, PROJECT_FILE
from ..persistence.title_page import save_title_page
from ..persistence.photos import remove_photos
from ..image_processing.photos import import_batch, read_image
from ..import_export.export import export_project
from .widgets import BookDialog, PhotoView
from .vision import CropDialog, ReviewDialog, SettingsDialog, settings
from ..vision.provider import OpenAIVisionProvider
from ..vision.gemini import GeminiVisionProvider
from ..vision.schema import VisionCancelled
from ..vision.workflow import save_proposal
from ..vision.shelf_workflow import save_regions, save_corrections
from .shelf import RegionsDialog, draw_regions
from .metadata import MetadataDialog
from ..metadata_providers import LobidProvider, OpenLibraryProvider, GoogleBooksProvider, DNBProvider, CustomJSONProvider
from ..metadata_providers.workflow import search_book, search_books
from ..isbn import normalize, valid, to_isbn13
from .calibre_import import ImportDialog
from .camera import CameraDialog
from ..calibre_plugin.importer import prepare_import, import_books
from .. import PapierbibliothekPlugin


PLUGIN_VERSION = '.'.join(str(part) for part in PapierbibliothekPlugin.version)


class Task(QThread):
    progress = pyqtSignal(str)
    result = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function
        self.cancel = threading.Event()

    def run(self):
        try:
            self.result.emit(self.function(self.cancel, self.progress.emit))
        except VisionCancelled:
            self.result.emit({'cancelled': True})
        except Exception as exc:
            self.failed.emit(str(exc))


class MainDialog(QDialog):
    def __init__(self, parent=None, auto_open=False):
        super().__init__(parent)
        self.setWindowTitle(f'Papierbibliothek · Version {PLUGIN_VERSION}')
        self.resize(1260, 900)
        self.store = self.project = self.lock = self.task = None
        self.pending_result = self.pending_error = None
        self.session_key = ''
        self.gemini_session_key = ''
        self.remember_last_project = auto_open
        self.calibre_gui=parent if hasattr(parent,'current_db') else None
        self.review_threshold = settings()['review_threshold']
        self.controls = []
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        outer.addLayout(top)
        self.new_button = self.button(top, 'Neues Projekt', self.new_project)
        self.open_button = self.button(top, 'Projekt öffnen', self.open_project)
        self.rename_button = self.button(top, 'Umbenennen', self.rename_project)
        self.settings_button = self.button(top, 'KI- und Datenbank-Einstellungen', self.configure_vision)
        self.help_button = self.button(top, 'Hilfe', self.show_help)
        top.addStretch()
        self.csv_button = self.button(top, 'CSV exportieren', lambda: self.export('csv'))
        self.json_button = self.button(top, 'JSON exportieren', lambda: self.export('json'))
        self.summary = QLabel('Projekt anlegen oder öffnen. KI-Bildübertragung nur nach Bestätigung.')
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        left_layout.addLayout(row)
        self.files_button = self.button(row, 'Fotos hinzufügen', self.add_files)
        self.folder_button = self.button(row, 'Fotoordner hinzufügen', self.add_folder)
        self.photos = QListWidget()
        self.photos.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.photos.setAccessibleName('Importierte Regalfotos')
        self.photos.currentItemChanged.connect(self.select_photo)
        left_layout.addWidget(self.photos)
        self.delete_photos_button = self.button(
            left_layout, 'Ausgewählte Fotos löschen', self.delete_photos)
        self.photos.itemSelectionChanged.connect(self.update_enabled)
        self.photo_location_button = self.button(
            left_layout, 'Regal / Fach ausgewählter Fotos ändern', self.photo_location)
        split.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.viewer = PhotoView()
        right_layout.addWidget(self.viewer, 1)
        row = QHBoxLayout()
        right_layout.addLayout(row)
        self.button(row, 'Bild einpassen', self.viewer.fit_photo)
        self.full_button = self.button(row, 'Original ansehen', self.show_original)
        self.photo_caption = QLabel('Mausrad: Zoom · Ziehen: Verschieben')
        self.photo_caption.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.photo_caption)
        split.addWidget(right)
        split.setSizes([300, 820])

        vision_row = QHBoxLayout()
        outer.addLayout(vision_row)
        self.analyze_button = self.button(vision_row, 'Buchrücken mit KI erfassen', self.analyze_new)
        self.reanalyze_button = self.button(vision_row, 'Gewähltes Buch erneut auswerten', self.analyze_existing)
        self.review_button = self.button(vision_row, 'KI-Vorschlag prüfen', self.review_current)
        vision_row.addStretch()
        shelf_row = QHBoxLayout()
        outer.addLayout(shelf_row)
        self.shelf_button = self.button(shelf_row, 'Regal mit KI aufteilen', lambda: self.prepare_shelf(True))
        self.regions_button = self.button(shelf_row, 'Buchrücken-Rahmen bearbeiten', lambda: self.prepare_shelf(False))
        shelf_row.addStretch()
        capture_row=QHBoxLayout();outer.addLayout(capture_row)
        self.camera_button=self.button(capture_row,'Buch per Kamera erfassen',self.scan_camera)
        self.title_page_button=self.button(capture_row,'Titelblatt fotografieren',self.capture_title_page)
        self.title_page_view_button=self.button(capture_row,'Titelblatt anzeigen',self.show_title_page)
        self.title_page_ai_button=self.button(capture_row,'Titelblatt mit KI auswerten',self.analyze_title_page)
        self.isbn_button=self.button(capture_row,'ISBN eingeben und suchen',self.enter_isbn)
        self.isbn_photo_button=self.button(capture_row,'ISBN-/Barcodefoto auswerten',self.scan_identifier_photo)
        capture_row.addStretch()
        metadata_row=QHBoxLayout();outer.addLayout(metadata_row)
        self.metadata_button=self.button(metadata_row,'Online-Datenbanken abgleichen',self.search_metadata)
        self.metadata_batch_button=self.button(metadata_row,'Offene Bücher stapelweise abgleichen',self.search_metadata_batch)
        self.metadata_review_button=self.button(metadata_row,'Online-Treffer prüfen',self.review_metadata)
        metadata_row.addStretch()
        calibre_row=QHBoxLayout();outer.addLayout(calibre_row)
        self.calibre_button=self.button(calibre_row,'Importvorschau für aktuelle Calibre-Bibliothek',self.prepare_calibre_import)
        calibre_row.addWidget(QLabel('Nur bestätigte Auswahl; vorhandene Datensätze werden nie stillschweigend geändert.'))
        calibre_row.addStretch()

        filters = QHBoxLayout()
        outer.addLayout(filters)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Titel, Autor, ISBN, Regal oder Notizen suchen …')
        self.search.textChanged.connect(self.refresh_books)
        filters.addWidget(self.search, 1)
        self.status_filter = QComboBox()
        self.status_filter.addItem('Alle Status', None)
        for key, label in STATUSES.items():
            self.status_filter.addItem(label, key)
        self.status_filter.currentIndexChanged.connect(self.refresh_books)
        filters.addWidget(self.status_filter)
        self.photo_filter = QComboBox()
        self.photo_filter.addItem('Alle Fotos', False)
        self.photo_filter.addItem('Nur ausgewähltes Foto', True)
        self.photo_filter.currentIndexChanged.connect(self.refresh_books)
        filters.addWidget(self.photo_filter)
        self.confidence_filter = QComboBox()
        self.confidence_filter.addItem('Alle KI-Konfidenzen', 'all')
        self.confidence_filter.addItem('Unter Prüfgrenze', 'low')
        self.confidence_filter.addItem('Ohne KI-Auswertung', 'unknown')
        self.confidence_filter.currentIndexChanged.connect(self.refresh_books)
        filters.addWidget(self.confidence_filter)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Titel', 'Autor(en)', 'Verlag', 'ISBN', 'Regal / Fach', 'Position', 'Status'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self.activate_book)
        self.table.itemSelectionChanged.connect(self.select_book)
        self.table.setMinimumHeight(180)
        outer.addWidget(self.table, 1)
        book_row = QHBoxLayout()
        outer.addLayout(book_row)
        self.add_button = self.button(book_row, 'Buchdatensatz manuell anlegen', self.add_book)
        self.edit_button = self.button(book_row, 'Buch bearbeiten', self.edit_book)
        self.delete_button = self.button(book_row, 'Buch entfernen', self.delete_book)
        self.count = QLabel('0 Bücher')
        book_row.addWidget(self.count)
        book_row.addStretch()
        self.button(book_row, 'Schließen', self.close)
        status_row = QHBoxLayout()
        outer.addLayout(status_row)
        self.progress = QProgressBar()
        self.progress.hide()
        status_row.addWidget(self.progress)
        self.status = QLabel('Bereit')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        status_row.addWidget(self.status, 1)
        self.cancel_button = QPushButton('Vorgang abbrechen')
        self.cancel_button.clicked.connect(self.cancel_task)
        self.cancel_button.hide()
        status_row.addWidget(self.cancel_button)
        self.update_enabled()
        if auto_open:
            QTimer.singleShot(0, self.open_last_project)

    def button(self, layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        self.controls.append(button)
        return button

    def update_enabled(self):
        busy = self.task is not None
        for control in self.controls:
            control.setEnabled(not busy)
        for control in (self.rename_button, self.csv_button, self.json_button, self.files_button,
                        self.folder_button, self.add_button, self.edit_button, self.delete_button,
                        self.full_button, self.photo_location_button):
            control.setEnabled(self.project is not None and not busy)
        for control in (self.analyze_button, self.reanalyze_button, self.review_button, self.shelf_button, self.regions_button,
                        self.metadata_button,self.metadata_batch_button,self.metadata_review_button,self.isbn_button,self.isbn_photo_button,
                        self.camera_button,self.title_page_button,self.title_page_view_button,
                        self.title_page_ai_button):
            control.setEnabled(self.project is not None and not busy)
        self.calibre_button.setEnabled(self.project is not None and not busy and self.current_calibre_db() is not None)
        self.delete_photos_button.setEnabled(
            self.project is not None and not busy and bool(self.photos.selectedItems()))
        for control in (self.photos, self.table, self.search, self.status_filter, self.photo_filter, self.confidence_filter):
            control.setEnabled(not busy)

    def error(self, message):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle('Papierbibliothek')
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(message)
        box.exec()

    def show_help(self):
        box = QMessageBox(self)
        box.setWindowTitle(f'Papierbibliothek · Hilfe · Version {PLUGIN_VERSION}')
        box.setIcon(QMessageBox.Icon.Information)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            'Fotos\n'
            '• Fotos hinzufügen oder einen ganzen Fotoordner importieren.\n'
            '• Ein oder mehrere Fotos in der Fotoliste markieren.\n'
            '• Regal / Fach ausgewählter Fotos ändern aktualisiert alle markierten Fotos.\n'
            '• Ausgewählte Fotos löschen entfernt die Projektkopien nach Bestätigung. '
            'Bücher und gespeicherte Ausschnitte bleiben erhalten; die Projektkopien '
            'liegen danach im Ordner .trash/.\n\n'
            'Bücher\n'
            '• Buchdatensatz manuell anlegen oder einen leeren Datensatz doppelt anklicken.\n'
            '• Titelblatt fotografieren nimmt ein Bild mit der USB-Kamera auf. Im Editor '
            'kann es gedreht und zugeschnitten werden.\n'
            '• Regal mit KI aufteilen erkennt Buchrücken. Die kostenpflichtige KI-Auswertung '
            'erfolgt erst nach ausdrücklicher Bestätigung.\n\n'
            'Speicherung\n'
            'Das Projekt liegt im jeweils angezeigten Projektordner. CSV und JSON werden '
            'über die Export-Schaltflächen erstellt. Eine Kopie des Projektordners vor '
            'größeren Änderungen ist empfehlenswert.')
        box.exec()

    def acquire(self, root):
        lock = QLockFile(str(Path(root) / '.papierbibliothek.lock'))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise ValueError('Das Projekt ist bereits geöffnet oder nicht beschreibbar. Bitte das andere Fenster schließen und Zugriffsrechte prüfen.')
        return lock

    def set_project(self, store, project, lock):
        if self.lock:
            self.lock.unlock()
        self.store, self.project, self.lock = store, project, lock
        self.search.clear()
        self.status_filter.setCurrentIndex(0)
        self.photo_filter.setCurrentIndex(0)
        self.confidence_filter.setCurrentIndex(0)
        if self.remember_last_project:
            settings()['last_project'] = str(store.path)
        self.refresh()

    def open_last_project(self):
        path = settings()['last_project']
        if path and Path(path).is_file():
            self.load_project(path)

    def new_project(self):
        path = QFileDialog.getSaveFileName(self, 'Neuen Projektordner anlegen (noch nicht vorhanden)', '', 'Projektordner (*)')[0]
        if not path:
            return
        name, ok = QInputDialog.getText(self, 'Projektname', 'Name der Sammlung:', text=Path(path).name)
        if not ok:
            return
        try:
            store, project = ProjectStore.create(path, name)
            lock = self.acquire(store.root)
            self.set_project(store, project, lock)
        except (OSError, ValueError) as exc:
            self.error(str(exc))

    def open_project(self):
        path = QFileDialog.getOpenFileName(self, 'Projekt öffnen', '', 'Projekt (projekt.json);;JSON (*.json)')[0]
        if path:
            self.load_project(path)

    def load_project(self, path):
        path = Path(path).resolve()
        if path.name != PROJECT_FILE:
            self.error('Bitte die projekt.json im Projektordner öffnen. Hinweise zum Wiederherstellen eines JSON-Exports stehen in der README.')
            return False
        if self.store and path == self.store.path:
            return True
        lock = None
        try:
            lock = self.acquire(path.parent)
            store = ProjectStore(path.parent)
            project = store.load()
            missing = sum(not store.asset(photo.image_path).exists() for photo in project.photos)
            self.set_project(store, project, lock)
            if missing:
                self.error(f'{missing} Originalfoto(s) fehlen. Die Metadaten sind weiterhin bearbeitbar. Bitte photos/ und previews/ aus der Sicherung ergänzen.')
            return True
        except (OSError, ValueError) as exc:
            if lock:
                lock.unlock()
            self.error(str(exc))
            return False

    def commit(self, candidate):
        try:
            self.store.save(candidate)
            self.project = candidate
            self.refresh()
            self.status.setText('Gespeichert')
            return True
        except (OSError, ValueError) as exc:
            self.error('Speichern fehlgeschlagen. Die letzte gespeicherte Fassung bleibt erhalten.\n' + str(exc))
            return False

    def rename_project(self):
        name, ok = QInputDialog.getText(self, 'Projekt umbenennen', 'Neuer Name:', text=self.project.name)
        if ok:
            candidate = deepcopy(self.project)
            candidate.name = name.strip()
            self.commit(candidate)

    def current_photo_id(self):
        item = self.photos.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def current_photo(self):
        if not self.project:
            return None
        return next((p for p in self.project.photos if p.photo_id == self.current_photo_id()), None)

    def current_book(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0)
        if not item or not self.project:
            return None
        return next((b for b in self.project.books if b.book_id == item.data(Qt.ItemDataRole.UserRole)), None)

    def selected_books(self):
        if not self.project:
            return []
        ids = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item and item.data(Qt.ItemDataRole.UserRole) not in ids:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        by_id = {book.book_id: book for book in self.project.books}
        return [by_id[book_id] for book_id in ids if book_id in by_id]

    def refresh(self):
        selected = self.current_photo_id()
        self.photos.blockSignals(True)
        self.photos.clear()
        for photo in self.project.photos:
            item = QListWidgetItem(photo.original_name + (' · ' + photo.location if photo.location else ''))
            item.setData(Qt.ItemDataRole.UserRole, photo.photo_id)
            item.setToolTip(f'{photo.width} × {photo.height} Pixel')
            self.photos.addItem(item)
            if photo.photo_id == selected:
                self.photos.setCurrentItem(item)
        if self.photos.currentRow() < 0 and self.photos.count():
            self.photos.setCurrentRow(0)
        self.photos.blockSignals(False)
        self.summary.setText(f'{self.project.name} · {len(self.project.photos)} Fotos · {len(self.project.books)} Bücher\n{self.store.root}')
        self.select_photo()
        self.update_enabled()

    def select_photo(self, *args):
        photo = self.current_photo()
        try:
            self.viewer.show_photo(self.store.asset(photo.preview_path) if photo else None)
            self.show_overlays()
        except ValueError as exc:
            self.error(str(exc))
        self.refresh_books()

    def show_overlays(self):
        photo = self.current_photo()
        if not photo:
            return
        books = [b for b in self.project.books if b.photo_id == photo.photo_id and b.bounding_box]
        width, height = photo.width, photo.height
        rect = self.viewer.sceneRect()
        if (width > height) != (rect.width() > rect.height()):
            width, height = height, width
        book = self.current_book()
        draw_regions(self.viewer, books, width, height, book.book_id if book else None)

    def show_original(self):
        photo = self.current_photo()
        if photo:
            path = self.store.asset(photo.image_path)
            self.run_task(lambda cancel, progress: {'image': read_image(path, max_edge=16000)[0]},
                          'Originalfoto wird geladen …', cancellable=False)

    def photo_location(self):
        if not self.project:
            return
        selected = self.photos.selectedItems()
        if not selected and self.current_photo():
            selected = [self.photos.currentItem()]
        ids = {item.data(Qt.ItemDataRole.UserRole) for item in selected if item}
        if not ids:
            return
        current = next((photo.location for photo in self.project.photos
                        if photo.photo_id in ids), '')
        location, ok = QInputDialog.getText(
            self, 'Fotos zuordnen',
            f'Regal / Fach für {len(ids)} ausgewählte(s) Foto(s):', text=current)
        if ok:
            candidate = deepcopy(self.project)
            for photo in candidate.photos:
                if photo.photo_id in ids:
                    photo.location = location.strip()
            self.commit(candidate)

    def refresh_books(self, *args):
        previous = self.current_book()
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        if self.project:
            query = self.search.text().strip().casefold()
            for book in self.project.books:
                score = book.vision['extraction']['overall'] if book.vision else None
                mode = self.confidence_filter.currentData()
                if mode == 'unknown' and score is not None:
                    continue
                if mode == 'low' and (score is None or score >= self.review_threshold):
                    continue
                if self.status_filter.currentData() and book.status != self.status_filter.currentData():
                    continue
                if (self.photo_filter.currentData() and
                        self.current_photo_id() not in (book.photo_id, book.title_page_photo_id)):
                    continue
                haystack = ' '.join(str(getattr(book, k) or '') for k in ('title', 'author', 'isbn10', 'isbn13', 'location', 'notes', 'publisher')).casefold()
                if book.vision:
                    haystack += ' ' + ' '.join(str(v or '') for v in book.vision['extraction']['fields'].values()).casefold()
                if query and query not in haystack:
                    continue
                row = self.table.rowCount()
                self.table.insertRow(row)
                display_title = book.title or ('KI: ' + (book.vision['extraction']['fields']['title'] or '(unleserlich)') if book.vision else '(ohne Titel)')
                if not book.title and not book.vision and book.detection and book.detection['kind'] == 'group':
                    display_title = '(Buchgruppe – trennen)'
                for column, value in enumerate((display_title, book.author, book.publisher,
                                                book.isbn13 or book.isbn10, book.location, book.spine_position, STATUSES[book.status])):
                    item = QTableWidgetItem(value or '')
                    item.setData(Qt.ItemDataRole.UserRole, book.book_id)
                    self.table.setItem(row, column, item)
                if previous and book.book_id == previous.book_id:
                    self.table.selectRow(row)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self.count.setText(f'{self.table.rowCount()} von {len(self.project.books) if self.project else 0} Büchern')

    def select_book(self):
        book = self.current_book()
        if book and book.photo_id and not self.photo_filter.currentData():
            for index in range(self.photos.count()):
                item = self.photos.item(index)
                if item.data(Qt.ItemDataRole.UserRole) == book.photo_id:
                    self.photos.blockSignals(True)
                    self.photos.setCurrentItem(item)
                    self.photos.blockSignals(False)
                    photo = self.current_photo()
                    self.viewer.show_photo(self.store.asset(photo.preview_path))
                    self.show_overlays()
                    break

    def add_book(self):
        dialog = BookDialog(self.project, photo_id=self.current_photo_id(), parent=self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            candidate = deepcopy(self.project)
            candidate.books.append(dialog.book)
            if self.commit(candidate):
                self.select_book_id(dialog.book.book_id)
                self.status.setText(
                    'Manueller Buchdatensatz gespeichert. Titelblatt, ISBN oder Barcode können jetzt ergänzt werden.')
                break

    def configure_vision(self):
        dialog = SettingsDialog(self.session_key, parent=self, gemini_session_key=self.gemini_session_key)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.session_key = dialog.session_key
                self.gemini_session_key = dialog.gemini_session_key
                self.review_threshold = settings()['review_threshold']
                self.refresh_books()
        finally:
            dialog.key.clear()
            dialog.gemini_key.clear()
            dialog.session_key = dialog.gemini_session_key = ''
            dialog.deleteLater()

    def analyze_new(self):
        self.prepare_analysis()

    def metadata_providers(self):
        prefs=settings();providers=[]
        if prefs['use_lobid']:providers.append(LobidProvider())
        if prefs['use_openlibrary']:providers.append(OpenLibraryProvider())
        if prefs['use_googlebooks']:providers.append(GoogleBooksProvider(os.environ.get('GOOGLE_BOOKS_API_KEY','')))
        if prefs['use_dnb']:providers.append(DNBProvider())
        if prefs['custom_url']:providers.append(CustomJSONProvider(prefs['custom_url'],os.environ.get('PAPIERBIBLIOTHEK_CUSTOM_API_KEY','')))
        return providers

    def enter_isbn(self):
        book=self.current_book()
        if not book:self.error('Bitte zuerst einen Buchdatensatz auswählen.');return
        value,ok=QInputDialog.getText(self,'ISBN erfassen','ISBN-10 oder ISBN-13 (Bindestriche erlaubt):',text=book.isbn13 or book.isbn10 or '')
        if not ok:return
        value=normalize(value)
        if not valid(value):self.error('Ungültige ISBN: Länge oder Prüfziffer stimmt nicht.');return
        candidate=deepcopy(self.project);target=next(x for x in candidate.books if x.book_id==book.book_id)
        self.set_book_isbn(target,value)
        target.status='needs_manual_review'
        if self.commit(candidate):self.search_metadata_for(book.book_id)

    def search_metadata(self):
        book=self.current_book()
        if not book:self.error('Bitte zuerst ein Buch auswählen.');return
        self.search_metadata_for(book.book_id)

    def search_metadata_for(self,book_id,auto_apply=False,camera_scan=False,providers=None):
        try:
            if providers is None:providers=self.metadata_providers()
        except ValueError as exc:self.error(str(exc));return False
        prefs=settings()
        if not providers and not prefs['metadata_offline']:
            self.error('Bitte mindestens einen Metadatenanbieter aktivieren.')
            return False
        snapshot=deepcopy(self.project)
        def work(cancel,progress):
            result=search_book(self.store,snapshot,book_id,providers,cancel,progress,
                               prefs['metadata_offline'],prefs['metadata_threshold'],auto_apply)
            result['camera_scan']=camera_scan
            return result
        self.run_task(work,'Online-Abgleich …')
        return True

    def search_metadata_batch(self):
        ids=[book.book_id for book in self.project.books
             if book.status not in ('rejected','imported') and (book.isbn10 or book.isbn13 or book.title)]
        if not ids:self.error('Es gibt keine abgleichbaren Bücher mit ISBN oder Titel.');return
        try:providers=self.metadata_providers()
        except ValueError as exc:self.error(str(exc));return
        prefs=settings()
        if not providers and not prefs['metadata_offline']:self.error('Bitte mindestens einen Metadatenanbieter aktivieren.');return
        snapshot=deepcopy(self.project)
        self.run_task(lambda cancel,progress:search_books(self.store,snapshot,ids,providers,cancel,progress,
                      prefs['metadata_offline'],prefs['metadata_threshold']),'Stapel-Abgleich …')

    def review_metadata(self):
        book=self.current_book()
        if not book or not book.provider_matches:self.error('Für dieses Buch gibt es noch keine Online-Treffer.');return
        self.review_metadata_for(book.book_id)

    def review_metadata_for(self,book_id):
        book=next((x for x in self.project.books if x.book_id==book_id),None)
        if not book or not book.provider_matches:self.error('Für dieses Buch gibt es noch keine Online-Treffer.');return
        dialog=MetadataDialog(book,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            candidate=deepcopy(self.project);candidate.books=[dialog.book if x.book_id==book.book_id else x for x in candidate.books];self.commit(candidate)

    @staticmethod
    def set_book_isbn(book,value):
        if len(value)==10:
            book.isbn10=value;book.isbn13=to_isbn13(value)
        else:
            book.isbn13=value
            if book.isbn10 and to_isbn13(book.isbn10)!=value:book.isbn10=None

    def scan_identifier_photo(self):
        book=self.current_book()
        if not book:self.error('Bitte zuerst einen Buchdatensatz auswählen.');return
        try:provider,provider_name=self.selected_provider()
        except ValueError as exc:self.error(str(exc));return
        path=QFileDialog.getOpenFileName(self,'ISBN-/Barcodefoto öffnen','',
              'Bilder (*.jpg *.jpeg *.png *.webp *.heic *.heif);;Alle Dateien (*)')[0]
        if not path:return
        self.run_task(lambda cancel,progress:{'identifier_source':read_image(path,max_edge=None)[0],
                      'provider':provider,'provider_name':provider_name,'book_id':book.book_id},
                      'ISBN-/Barcodefoto wird geladen …')

    def scan_camera(self):
        if not self.project:
            self.error('Bitte zuerst ein Projekt öffnen oder anlegen.');return
        dialog=CameraDialog(self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if dialog.detected_isbn:
            self.accept_camera_isbn(dialog.detected_isbn)
        elif dialog.captured_image is not None:
            self.launch_camera_identifier(dialog.captured_image)

    def capture_title_page(self):
        if not self.project:
            self.error('Bitte zuerst ein Projekt öffnen oder anlegen.');return
        book = self.current_book()
        if not book:
            self.error('Bitte zuerst den Buchdatensatz auswählen, dem das Titelblatt zugeordnet werden soll.');return
        camera = CameraDialog(self, title_page=True)
        if camera.exec() != QDialog.DialogCode.Accepted or camera.captured_image is None:
            return
        editor = CropDialog(camera.captured_image, '', parent=self,
                            local_title_page=True)
        editor.select_whole()
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.project = save_title_page(
                self.store, self.project, book.book_id, editor.jpeg)
            self.refresh()
            self.select_book_id(book.book_id)
            self.show_title_page()
            self.status.setText('Titelblatt zugeschnitten und lokal im Projekt gespeichert.')
        except (OSError, ValueError) as exc:
            self.error('Titelblatt konnte nicht gespeichert werden.\n' + str(exc))

    def show_title_page(self):
        book = self.current_book()
        if not book or not book.title_page_path:
            self.error('Für den ausgewählten Buchdatensatz ist noch kein Titelblatt gespeichert.');return
        try:
            path = self.store.asset(book.title_page_path)
            if not path.is_file():
                raise ValueError('Die gespeicherte Titelblattdatei fehlt.')
            self.viewer.show_photo(path)
            self.photo_caption.setText('Gespeichertes Titelblatt · Mausrad: Zoom · Ziehen: Verschieben')
        except (OSError, ValueError) as exc:
            self.error(str(exc))

    def analyze_title_page(self):
        book = self.current_book()
        if not book or not book.title_page_path:
            self.error('Bitte zuerst für den ausgewählten Buchdatensatz ein Titelblatt aufnehmen.');return
        try:
            provider, provider_name = self.selected_provider()
            path = self.store.asset(book.title_page_path)
        except (OSError, ValueError) as exc:
            self.error(str(exc));return
        self.run_task(
            lambda cancel, progress: {
                'crop_source': read_image(path, max_edge=None)[0],
                'provider': provider, 'provider_name': provider_name,
                'photo': None, 'book_id': book.book_id,
                'title_page_analysis': True},
            'Titelblatt für KI-Auswertung laden …')

    def launch_camera_identifier(self,image):
        try:provider,provider_name=self.selected_provider()
        except ValueError as exc:self.error(str(exc));return
        dialog=CropDialog(image,provider.model,parent=self,
                          provider_name=provider_name,identifier=True)
        dialog.select_whole()
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        jpeg=dialog.jpeg
        def analyze(cancel,progress):
            progress('ISBN-Text wird gelesen …')
            return {'identifier_result':provider.scan_identifier(
                        jpeg,consent=True,cancel=cancel),
                    'book_id':None,'camera_new':True}
        self.run_task(analyze,'ISBN-Erkennung …')

    def accept_camera_isbn(self,value):
        value=normalize(value)
        if not valid(value):
            self.error('Die Kameraerkennung lieferte keine gültige ISBN.');return
        canonical=to_isbn13(value) if len(value)==10 else value
        existing=next((book for book in self.project.books
                       if ((to_isbn13(book.isbn10) if book.isbn10 else book.isbn13)
                           == canonical)),None)
        if existing:
            self.select_book_id(existing.book_id)
            if any(getattr(existing,key) for key in
                   ('title','author','subtitle','publisher','publication_year')):
                self.status.setText('ISBN ist bereits im Projekt; kein doppelter Datensatz angelegt.')
                return
            self.status.setText('ISBN ist bereits im Projekt; leerer Datensatz wird abgeglichen.')
            self.search_metadata_for(existing.book_id,auto_apply=True,camera_scan=True,
                                     providers=[LobidProvider()])
            return
        photo=self.current_photo()
        book=Book(isbn13=canonical,
                  location=(photo.location if photo and photo.location else None),
                  status='needs_manual_review')
        candidate=deepcopy(self.project);candidate.books.append(book)
        if self.commit(candidate):
            self.select_book_id(book.book_id)
            if not self.search_metadata_for(
                    book.book_id,auto_apply=True,camera_scan=True,
                    providers=[LobidProvider()]):
                self.status.setText(
                    'ISBN gespeichert; Online-Abgleich konnte nicht gestartet werden.')

    def select_book_id(self,book_id):
        for row in range(self.table.rowCount()):
            item=self.table.item(row,0)
            if item and item.data(Qt.ItemDataRole.UserRole)==book_id:
                self.table.setCurrentCell(row,0);self.table.selectRow(row);return True
        return False

    def launch_identifier(self,data):
        provider=data['provider']
        dialog=CropDialog(data['identifier_source'],provider.model,parent=self,
                          provider_name=data['provider_name'],identifier=True)
        dialog.select_whole()
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        jpeg=dialog.jpeg
        def analyze(cancel,progress):
            progress('ISBN oder Barcode wird gelesen …')
            return {'identifier_result':provider.scan_identifier(jpeg,consent=True,cancel=cancel),
                    'book_id':data['book_id']}
        self.run_task(analyze,'ISBN-Erkennung …')

    def present_identifier(self,data):
        extraction=data['identifier_result']['extraction']
        candidates=[]
        for raw in extraction['isbn_candidates']:
            value=normalize(raw)
            if valid(value):
                canonical=to_isbn13(value) if len(value)==10 else value
                if canonical not in candidates:candidates.append(canonical)
        details=('Erkannter Text:\n'+(extraction['raw_text'] or '(leer)')+
                 '\n\nISBN-Kandidaten: '+(', '.join(extraction['isbn_candidates']) or '(keine)')+
                 f"\nKonfidenz: {extraction['confidence']:.0%}")
        if len(candidates)!=1:
            message='Keine gültige ISBN mit korrekter Prüfziffer erkannt.' if not candidates else 'Mehrere unterschiedliche gültige ISBNs erkannt; bitte ISBN manuell eingeben.'
            self.error(message+'\n\n'+details);return
        answer=QMessageBox.question(self,'ISBN-Ergebnis prüfen',
                 'Gültige ISBN-13: '+candidates[0]+'\n\n'+details+'\n\nDiese ISBN übernehmen und online suchen?',
                 QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        if data.get('camera_new'):
            self.accept_camera_isbn(candidates[0]);return
        candidate=deepcopy(self.project);book=next(x for x in candidate.books if x.book_id==data['book_id'])
        self.set_book_isbn(book,candidates[0]);book.status='needs_manual_review'
        if self.commit(candidate):self.search_metadata_for(book.book_id)

    def prepare_calibre_import(self):
        db=self.current_calibre_db()
        if db is None:self.error('Der direkte Import ist nur innerhalb der Calibre-Hauptoberfläche verfügbar.');return
        snapshot=deepcopy(self.project)
        def prepare(cancel,progress):
            result=prepare_import(snapshot,db,cancel,progress);result['calibre_db']=db;return result
        self.run_task(prepare,
                      'Calibre-Dublettenprüfung …')

    def current_calibre_db(self):
        try:return self.calibre_gui.current_db.new_api if self.calibre_gui is not None else None
        except Exception:return None

    def launch_import_preview(self,rows,db):
        if not rows:self.error('Keine importierbaren Bücher. Erforderlich sind Titel und Status Eindeutig, Wahrscheinlich, Manuell bestätigt oder Importfehler.');return
        dialog=ImportDialog(rows,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        creates=sum(x['action']=='create' for x in dialog.plans);updates=sum(x['action']=='update' for x in dialog.plans)
        answer=QMessageBox.question(self,'Calibre-Import bestätigen',
             f'{creates} neue Datensätze anlegen und {updates} vorhandene Datensätze aktualisieren?\n'
             'Dieser Vorgang verändert die aktuell geöffnete Calibre-Bibliothek.',
             QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        if self.current_calibre_db() is not db:
            self.error('Die aktive Calibre-Bibliothek wurde gewechselt. Bitte die Importvorschau neu öffnen.');return
        snapshot=deepcopy(self.project);plans=deepcopy(dialog.plans);covers=dialog.cover.isChecked()
        self.run_task(lambda cancel,progress:import_books(self.store,snapshot,plans,db,cancel,progress,covers),
                      'Import in Calibre …')

    def refresh_calibre(self,ids,added=0):
        if not ids or self.calibre_gui is None:return
        model=self.calibre_gui.library_view.model()
        try:
            # refresh_ids() only repaints rows already known to the model.
            # Calibre 9.x requires books_added() when new_api created rows.
            if added:model.books_added(added)
            model.refresh_ids(set(ids))
        except Exception:
            # Slower, public fallback for changed Calibre model behaviour.
            try:model.refresh()
            except Exception:pass
        try:self.calibre_gui.tags_view.recount()
        except Exception:pass

    def selected_provider(self):
        prefs = settings()
        if prefs['provider'] == 'gemini':
            return GeminiVisionProvider(self.gemini_session_key or os.environ.get('GEMINI_API_KEY', ''), prefs['gemini_model']), 'Google Gemini'
        if prefs['provider'] == 'openai':
            return OpenAIVisionProvider(self.session_key or os.environ.get('OPENAI_API_KEY', ''), prefs['model']), 'OpenAI'
        raise ValueError('Unbekannter KI-Anbieter. Bitte in den KI-Einstellungen auswählen.')

    def prepare_shelf(self, detect):
        photo = self.current_photo()
        if not photo:
            self.error('Bitte zuerst ein Regalfoto auswählen.')
            return
        provider = None
        provider_name = None
        if detect:
            try:
                provider, provider_name = self.selected_provider()
            except ValueError as exc:
                self.error(str(exc))
                return
        path = self.store.asset(photo.image_path)
        self.run_task(lambda cancel, progress: {'shelf_source': read_image(path, max_edge=None)[0],
                      'photo': photo, 'provider': provider, 'provider_name': provider_name}, 'Regalfoto laden …')

    def launch_shelf(self, data):
        image, photo, provider = data['shelf_source'], data['photo'], data['provider']
        if provider is None:
            dialog = RegionsDialog(self.project, photo, image, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.run_task(lambda cancel, progress: save_corrections(self.store, self.project, dialog.project, photo, image, cancel), 'Rahmen und Ausschnitte speichern …')
            return
        dialog = CropDialog(image, provider.model, self, shelf=True, provider_name=data['provider_name'])
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def work(cancel, progress):
            progress('Buchrücken werden lokalisiert …')
            result = provider.detect_shelf(dialog.jpeg, consent=True, cancel=cancel)
            progress('Bereiche und Ausschnitte werden gespeichert …')
            return save_regions(self.store, self.project, photo, image, dialog.box, result, cancel)
        self.run_task(work, 'Regal-Erkennung …')

    def analyze_existing(self):
        book = self.current_book()
        if not book:
            self.error('Bitte zuerst einen Buchdatensatz auswählen.')
            return
        self.prepare_analysis(book)

    def prepare_analysis(self, book=None):
        photo = next((p for p in self.project.photos if p.photo_id == book.photo_id), None) if book else self.current_photo()
        if photo is None:
            self.error('Bitte ein Foto auswählen oder dem Buch ein Foto zuordnen.')
            return
        try:
            provider, provider_name = self.selected_provider()
        except ValueError as exc:
            self.error(str(exc))
            return
        path = self.store.asset(photo.image_path)
        self.run_task(lambda cancel, progress: {'crop_source': read_image(path, max_edge=None)[0],
                      'provider': provider, 'provider_name': provider_name, 'photo': photo, 'book_id': book.book_id if book else None},
                      'Regalfoto für Ausschnittauswahl laden …')

    def launch_analysis(self, data):
        provider, photo = data['provider'], data['photo']
        title_page_analysis = bool(data.get('title_page_analysis'))
        dialog = CropDialog(data['crop_source'], provider.model, parent=self,
                            provider_name=data['provider_name'],
                            title_page_analysis=title_page_analysis)
        book = next((b for b in self.project.books if b.book_id == data['book_id']), None)
        if book and book.bounding_box:
            box = book.bounding_box
            dialog.view.set_selection(QRectF(box['x'], box['y'], box['width'], box['height']))
            dialog.update_preview()
        elif title_page_analysis:
            dialog.select_whole()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        jpeg, box = dialog.jpeg, dialog.box
        def analyze(cancel, progress):
            progress('Buchrücken wird ausgewertet …')
            result = provider.analyze(jpeg, consent=True, cancel=cancel)
            return save_proposal(self.store, self.project, photo, jpeg, box, result,
                                 cancel, data['book_id'],
                                 title_page=title_page_analysis)
        self.run_task(analyze, 'KI-Auswertung …')

    def review_current(self):
        book = self.current_book()
        if book:
            self.review_book(book.book_id)
        else:
            self.error('Bitte zuerst ein Buch mit KI-Vorschlag auswählen.')

    def review_book(self, book_id):
        book = next((b for b in self.project.books if b.book_id == book_id), None)
        if not book or not book.vision:
            self.error('Für dieses Buch gibt es noch keinen KI-Vorschlag.')
            return
        photo = next((p for p in self.project.photos if p.photo_id == book.photo_id), None)
        dialog = ReviewDialog(book, self.store, self.review_threshold, parent=self, photo=photo)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            candidate = deepcopy(self.project)
            candidate.books = [dialog.book if b.book_id == book_id else b for b in candidate.books]
            if self.commit(candidate):
                break

    def edit_book(self, *args):
        book = self.current_book()
        if book:
            dialog = BookDialog(self.project, book=book, parent=self)
            while dialog.exec() == QDialog.DialogCode.Accepted:
                candidate = deepcopy(self.project)
                candidate.books = [dialog.book if b.book_id == book.book_id else b for b in candidate.books]
                if self.commit(candidate):
                    break

    @staticmethod
    def has_bibliographic_data(book):
        return any(getattr(book, key) not in (None, '') for key in
                   ('title', 'author', 'subtitle', 'publisher', 'publication_year',
                    'isbn10', 'isbn13', 'raw_text'))

    def activate_book(self, *args):
        book = self.current_book()
        if not book:
            return
        if self.has_bibliographic_data(book):
            self.edit_book()
        elif book.vision:
            self.review_book(book.book_id)
        else:
            self.prepare_analysis(book)

    def delete_book(self):
        books = self.selected_books()
        if not books:
            book = self.current_book()
            books = [book] if book else []
        if books and QMessageBox.question(
                self, 'Buch entfernen',
                (f'{len(books)} ausgewählte Buchdatensätze entfernen?' if len(books) > 1
                 else 'Ausgewählten Buchdatensatz entfernen?') + ' Fotos bleiben erhalten.') == QMessageBox.StandardButton.Yes:
            ids = {book.book_id for book in books}
            candidate = deepcopy(self.project)
            candidate.books = [b for b in candidate.books if b.book_id not in ids]
            self.commit(candidate)

    def add_files(self):
        paths = QFileDialog.getOpenFileNames(self, 'Regalfotos hinzufügen', '', 'Fotos (*.jpg *.jpeg *.png *.webp *.heic *.heif);;Alle Dateien (*)')[0]
        if paths:
            self.start_import(paths)

    def delete_photos(self):
        if not self.project or self.task is not None:
            return
        ids = {item.data(Qt.ItemDataRole.UserRole)
               for item in self.photos.selectedItems()}
        if not ids:
            return
        linked = sum(book.photo_id in ids or book.title_page_photo_id in ids
                     for book in self.project.books)
        message = (f'{len(ids)} ausgewählte Foto(s) aus dem Projekt löschen?\n\n'
                   f'{linked} zugeordnete Buchdatensätze bleiben erhalten. '
                   'Ihre Zuordnung zu diesen Fotos wird entfernt. '
                   'Gespeicherte Buchrückenausschnitte und KI-Belege bleiben erhalten.\n\n'
                   'Die Projektkopien werden zur Wiederherstellung unter .trash/ '
                   'im Projektordner aufbewahrt. Ursprünglich importierte Dateien '
                   'außerhalb des Projekts bleiben erhalten.')
        if QMessageBox.question(
                self, 'Fotos löschen', message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.project, recycle, warnings = remove_photos(self.store, self.project, ids)
        except (OSError, ValueError) as exc:
            self.error('Fotos konnten nicht gelöscht werden.\n' + str(exc))
            return
        # Detached books should remain visible even when a photo filter was set.
        self.photo_filter.setCurrentIndex(0)
        self.refresh()
        self.photo_caption.setText('Mausrad: Zoom · Ziehen: Verschieben')
        self.status.setText(f'{len(ids)} Foto(s) gelöscht. Bücher erhalten. Papierkorb: {recycle}')
        if warnings:
            self.error('Die Fotos wurden aus dem Projekt entfernt. Einige Bilddateien '
                       'konnten nicht in den Projektpapierkorb verschoben werden '
                       'und liegen weiterhin am bisherigen Speicherort:\n' + '\n'.join(warnings))

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Fotoordner (mit Unterordnern)')
        if path:
            # Prevent recursively ingesting the managed project itself.
            resolved = Path(path).resolve()
            if self.store.root.is_relative_to(resolved) or resolved.is_relative_to(self.store.root):
                self.error('Bitte einen Fotoordner außerhalb des Projektordners auswählen, der das Projekt auch nicht enthält.')
                return
            self.start_import([path])

    def start_import(self, paths):
        location, ok = QInputDialog.getText(self, 'Regalfotos zuordnen', 'Regal / Fach für diese Fotos (optional):')
        if ok:
            self.run_task(lambda cancel, progress: import_batch(self.store, self.project, paths, location.strip(), cancel, progress), 'Fotos werden importiert …')

    def export(self, kind):
        destination = self.store.root / 'exports'
        try:
            destination.mkdir(exist_ok=True)
        except OSError as exc:
            self.error(str(exc))
            return
        path = QFileDialog.getSaveFileName(self, 'Alle Bücher exportieren', str(destination / ('buecher.' + kind)), kind.upper() + ' (*.' + kind + ')')[0]
        if path:
            if not Path(path).suffix:
                path += '.' + kind
            snapshot = deepcopy(self.project)
            def export_work(cancel, progress):
                if not cancel.is_set():
                    export_project(snapshot, path, kind, self.store.root)
                    return {'exported': path}
                return {'cancelled': True}
            self.run_task(export_work, 'Export wird erstellt …', cancellable=False)

    def run_task(self, function, title, cancellable=True):
        if self.task is not None:
            return
        self.pending_result = self.pending_error = None
        self.task = Task(function, self)
        self.task.progress.connect(self.status.setText)
        self.task.result.connect(self.task_result)
        self.task.failed.connect(self.task_error)
        self.task.finished.connect(self.task_finished)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_button.setVisible(cancellable)
        self.cancel_button.setEnabled(True)
        self.status.setText(title)
        self.update_enabled()
        self.task.start()

    def task_result(self, result):
        self.pending_result = result

    def task_error(self, error):
        self.pending_error = error

    def task_finished(self):
        task = self.task
        cancelled = task.cancel.is_set()
        self.task = None
        task.deleteLater()
        self.progress.hide()
        self.cancel_button.hide()
        self.refresh()
        if self.pending_error:
            self.status.setText('Vorgang fehlgeschlagen; bereits gespeicherte Daten bleiben erhalten.')
            self.error(self.pending_error)
        elif self.pending_result:
            result = self.pending_result
            if 'shelf_saved' in result or 'regions_edited' in result:
                self.project = result['project']
                self.refresh()
                if 'shelf_saved' in result:
                    self.status.setText(f"{result['added']} Bereiche gespeichert · {result['duplicates']} ähnliche Rahmen übersprungen. Bitte Rahmen prüfen.")
                    if result['warnings']:
                        self.error('\n'.join(result['warnings']))
                    if not cancelled:
                        self.prepare_shelf(False)
                else:
                    self.status.setText('Rahmenkorrekturen gespeichert. Metadaten bleiben separat prüfpflichtig.')
            elif 'import_preview' in result:
                self.status.setText(f"{len(result['import_preview'])} importierbare Bücher geprüft.")
                self.launch_import_preview(result['import_preview'],result['calibre_db'])
            elif 'calibre_import' in result:
                self.project=result['project'];self.refresh()
                added=sum(item.get('action')=='create' and not item.get('error') for item in result['results'])
                self.refresh_calibre(result['changed_ids'],added)
                failures=[x for x in result['results'] if x.get('error')]
                warnings=[x for x in result['results'] if x.get('warning') or x.get('warnings')]
                text=f"{len(result['changed_ids'])} Calibre-Datensätze verarbeitet"
                if result.get('cancelled'):text+=' · abgebrochen; fertige Datensätze bleiben erhalten'
                self.status.setText(text)
                if failures or warnings:
                    box=QMessageBox(self);box.setWindowTitle('Calibre-Import');box.setText(text)
                    details=[]
                    for item in failures:details.append(item['book_id']+': '+item['error'])
                    for item in warnings:details.append(item['book_id']+': '+str(item.get('warning') or ', '.join(item.get('warnings',[]))))
                    box.setDetailedText('\n'.join(details));box.exec()
            elif 'batch_metadata' in result:
                self.project=result['project'];self.refresh()
                text=f"{result['searched']} Bücher abgeglichen"
                if result.get('cancelled'):text+=' · abgebrochen; Zwischenergebnisse gespeichert'
                self.status.setText(text)
                if result['errors']:
                    box=QMessageBox(self);box.setWindowTitle('Stapel-Abgleich');box.setText(text)
                    box.setDetailedText('\n'.join(result['errors']));box.exec()
            elif 'metadata_book_id' in result:
                self.project=result['project'];self.refresh();self.status.setText(result['reason'])
                if result['errors']:self.error('\n'.join(result['errors']))
                self.select_book_id(result['metadata_book_id'])
                matches=next((b.provider_matches for b in self.project.books
                              if b.book_id==result['metadata_book_id']),[])
                if result.get('camera_scan') and result.get('auto_applied'):
                    self.status.setText('ISBN erkannt · eindeutige Metadaten automatisch übernommen.')
                elif result.get('camera_scan') and not matches:
                    self.status.setText(
                        'ISBN gespeichert; Online-Abfrage nicht erfolgreich. Später erneut abgleichen.')
                elif matches:
                    self.review_metadata_for(result['metadata_book_id'])
            elif 'identifier_result' in result:
                self.status.setText('ISBN-Erkennung abgeschlossen; bitte Ergebnis prüfen.')
                self.present_identifier(result)
            elif 'review_book_id' in result:
                self.project = result['project']
                self.refresh()
                self.status.setText('KI-Vorschlag gespeichert; bitte prüfen.')
                self.review_book(result['review_book_id'])
            elif (cancelled or result.get('cancelled')) and 'imported' not in result:
                self.status.setText('Abgebrochen. Bereits gesendete API-Anfragen können Kosten verursachen.')
            elif 'crop_source' in result:
                self.launch_analysis(result)
            elif 'identifier_source' in result:
                self.launch_identifier(result)
            elif 'shelf_source' in result:
                self.launch_shelf(result)
            elif 'image' in result:
                self.viewer.show_image(result['image'])
                self.show_overlays()
                self.status.setText('Originalansicht · Mausrad zum Zoomen')
            elif 'exported' in result:
                self.status.setText('Export gespeichert: ' + result['exported'])
            elif 'imported' in result:
                text = f"{result['imported']} Fotos importiert · {result['duplicates']} identische Fotos übersprungen · {len(result['errors'])} Fehler"
                if result.get('cancelled'):
                    text += ' · Abgebrochen'
                self.status.setText(text)
                if result['errors']:
                    box = QMessageBox(self)
                    box.setWindowTitle('Fotoimport')
                    box.setText(text)
                    box.setDetailedText('\n'.join(result['errors']))
                    box.exec()

    def cancel_task(self):
        if self.task:
            self.task.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText('Abbruch angefordert; laufende Bildverarbeitung wird beendet …')

    def reject(self):
        self.close()

    def close(self):
        # Qt may skip closeEvent on an already hidden, reused dialog.
        if not self.isVisible() and not self.task:
            self.release_project()
        return super().close()

    def closeEvent(self, event):
        if self.task:
            self.cancel_task()
            event.ignore()
            return
        self.release_project()
        event.accept()

    def release_project(self):
        if self.lock:
            self.lock.unlock()
        self.lock = self.store = self.project = None
        self.session_key = ''
        self.gemini_session_key = ''
        self.pending_result = self.pending_error = None
        self.photos.clear()
        self.table.setRowCount(0)
        self.summary.setText('Projekt anlegen oder öffnen. KI-Bildübertragung nur nach Bestätigung.')
        self.viewer.show_photo()
        self.update_enabled()
