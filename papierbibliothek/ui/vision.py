from copy import deepcopy
import os

from qt.core import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox,
                     QComboBox, QDoubleSpinBox, QLineEdit, QLabel, QPushButton, QCheckBox,
                     QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                     QPen, QColor, QRectF, Qt, pyqtSignal)

from ..vision.provider import DEFAULT_MODEL
from ..vision.gemini import DEFAULT_GEMINI_MODEL
from ..vision.schema import FIELDS, LABELS
from ..vision.workflow import apply_review
from ..image_processing.crop import crop_image, jpeg_bytes
from ..isbn import valid
from .widgets import PhotoView


def settings():
    from calibre.utils.config import JSONConfig
    prefs = JSONConfig('plugins/papierbibliothek')
    prefs.defaults['model'] = DEFAULT_MODEL
    prefs.defaults['provider'] = 'openai'
    prefs.defaults['gemini_model'] = DEFAULT_GEMINI_MODEL
    prefs.defaults['review_threshold'] = 0.8
    prefs.defaults['metadata_threshold'] = 0.88
    prefs.defaults['metadata_offline'] = False
    prefs.defaults['use_lobid'] = True
    prefs.defaults['use_openlibrary'] = True
    prefs.defaults['use_googlebooks'] = False
    prefs.defaults['use_dnb'] = True
    prefs.defaults['custom_url'] = ''
    prefs.defaults['last_project'] = ''
    return prefs


class SettingsDialog(QDialog):
    def __init__(self, session_key='', parent=None, gemini_session_key=''):
        super().__init__(parent)
        self.setWindowTitle('KI- und Datenbank-Einstellungen')
        self.resize(760, 720)
        self.session_key = session_key
        self.gemini_session_key = gemini_session_key
        self.prefs = settings()
        layout = QVBoxLayout(self)
        text = QLabel('Bildübertragung erfolgt nur nach Bestätigung des konkreten Ausschnitts.\n'
                      'API-Nutzung wird separat berechnet. Manuelle Erfassung bleibt offline.')
        text.setWordWrap(True)
        layout.addWidget(text)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        self.provider = QComboBox()
        self.provider.addItem('OpenAI', 'openai')
        self.provider.addItem('Google Gemini', 'gemini')
        self.provider.setCurrentIndex(self.provider.findData(self.prefs['provider']))
        form.addRow('KI-Anbieter', self.provider)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems([DEFAULT_MODEL, 'gpt-5.4-nano', 'gpt-5.4-mini'])
        self.model.setCurrentText(self.prefs['model'])
        form.addRow('OpenAI-Modell', self.model)
        self.gemini_model = QComboBox()
        self.gemini_model.setEditable(True)
        self.gemini_model.addItems([DEFAULT_GEMINI_MODEL, 'gemini-3.1-flash-lite', 'gemini-3.8-flash'])
        self.gemini_model.setCurrentText(self.prefs['gemini_model'])
        form.addRow('Gemini-Modell', self.gemini_model)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0, 1)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(self.prefs['review_threshold'])
        form.addRow('Unterhalb dieses Werts hervorheben', self.threshold)
        self.metadata_threshold = QDoubleSpinBox(); self.metadata_threshold.setRange(.5,1); self.metadata_threshold.setSingleStep(.01); self.metadata_threshold.setValue(self.prefs['metadata_threshold'])
        form.addRow('Eindeutiger Online-Treffer ab',self.metadata_threshold)
        self.offline=QCheckBox('Nur lokalen Metadaten-Cache verwenden');self.offline.setChecked(self.prefs['metadata_offline']);form.addRow('Offline-Modus',self.offline)
        self.lobid=QCheckBox('lobid-resources / hbz');self.lobid.setChecked(self.prefs['use_lobid']);form.addRow('Buchdatenbank',self.lobid)
        self.openlibrary=QCheckBox('Open Library');self.openlibrary.setChecked(self.prefs['use_openlibrary']);form.addRow('',self.openlibrary)
        self.googlebooks=QCheckBox('Google Books');self.googlebooks.setChecked(self.prefs['use_googlebooks']);form.addRow('',self.googlebooks)
        self.dnb=QCheckBox('Deutsche Nationalbibliothek');self.dnb.setChecked(self.prefs['use_dnb']);form.addRow('',self.dnb)
        self.custom_url=QLineEdit(self.prefs['custom_url']);self.custom_url.setPlaceholderText('Optional: https://anbieter.example/search');form.addRow('Eigener JSON-Anbieter',self.custom_url)
        self.key = QLineEdit(session_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Optional: Schlüssel nur für dieses geöffnete Plugin-Fenster')
        form.addRow('OpenAI-Schlüssel (nur Sitzung)', self.key)
        self.gemini_key = QLineEdit(gemini_session_key)
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key.setPlaceholderText('Leer lassen, um GEMINI_API_KEY zu verwenden')
        form.addRow('Gemini-Schlüssel (nur Sitzung)', self.gemini_key)
        key_status = 'vorhanden' if os.environ.get('OPENAI_API_KEY') else 'nicht gesetzt'
        gemini_status = 'vorhanden' if os.environ.get('GEMINI_API_KEY') else 'nicht gesetzt'
        note = QLabel('OPENAI_API_KEY: ' + key_status + ' · GEMINI_API_KEY: ' + gemini_status + '\n'
                      'Ein hier eingegebener Schlüssel wird nicht auf Festplatte gespeichert.\n'
                      'Ohne Eingabe wird die jeweilige Umgebungsvariable verwendet.\n'
                      'Nur Anbieter, Modelle und Prüfgrenze werden gespeichert. Kein automatischer Anbieterwechsel.\n'
                      'Google verarbeitet Bilder nach seinen Gemini-API-Bedingungen; Tarif und Region können die Datennutzung beeinflussen.\n'
                      'Bitte vor dem Hochladen privater Fotos die Bedingungen deines Kontos prüfen.')
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.provider.currentIndexChanged.connect(self.update_provider)
        self.update_provider()

    def update_provider(self, *args):
        selected = self.provider.currentData()
        self.model.setEnabled(selected == 'openai')
        self.key.setEnabled(selected == 'openai')
        self.gemini_model.setEnabled(selected == 'gemini')
        self.gemini_key.setEnabled(selected == 'gemini')

    def accept(self):
        import re
        model = self.model.currentText().strip()
        gemini_model = self.gemini_model.currentText().strip()
        if self.provider.currentData() not in ('openai', 'gemini'):
            QMessageBox.warning(self, 'Anbieter prüfen', 'Bitte OpenAI oder Google Gemini auswählen.')
            return
        if not re.fullmatch(r'gemini-[A-Za-z0-9._-]{1,100}', gemini_model):
            QMessageBox.warning(self, 'Modell prüfen', 'Bitte eine gültige Gemini-Modell-ID eingeben (gemini-…).')
            return
        if not re.fullmatch(r'[A-Za-z0-9._:-]{1,100}', model):
            QMessageBox.warning(self, 'Modell prüfen', 'Bitte einen gültigen API-Modellnamen eingeben.')
            return
        custom=self.custom_url.text().strip()
        if custom and not custom.startswith('https://'):
            QMessageBox.warning(self, 'Anbieter prüfen', 'Der eigene Anbieter benötigt eine HTTPS-Adresse.')
            return
        try:
            self.prefs['model'] = model
            self.prefs['gemini_model'] = gemini_model
            self.prefs['provider'] = self.provider.currentData()
            self.prefs['review_threshold'] = self.threshold.value()
            self.prefs['metadata_threshold'] = self.metadata_threshold.value()
            self.prefs['metadata_offline'] = self.offline.isChecked()
            self.prefs['use_lobid'] = self.lobid.isChecked()
            self.prefs['use_openlibrary'] = self.openlibrary.isChecked()
            self.prefs['use_googlebooks'] = self.googlebooks.isChecked()
            self.prefs['use_dnb'] = self.dnb.isChecked()
            self.prefs['custom_url'] = custom
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Speichern fehlgeschlagen', str(exc) or 'Die KI-Einstellungen konnten nicht gespeichert werden.')
            return
        self.session_key = self.key.text().strip()
        self.gemini_session_key = self.gemini_key.text().strip()
        super().accept()


class CropView(PhotoView):
    selectionChanged = pyqtSignal()
    clicked = pyqtSignal(object, bool)

    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.show_image(image)
        self.bounds = QRectF(0, 0, image.width(), image.height())
        self.start = None
        self.press_position = None
        self.selection = QRectF()
        self.overlay = None
        self.setDragMode(PhotoView.DragMode.NoDrag)
        self.setAccessibleName('Buchrücken durch Ziehen eines Rechtecks auswählen')

    def set_selection(self, rect):
        self.selection = rect.normalized().intersected(self.bounds)
        if self.overlay is None:
            pen = QPen(QColor('#d05713'), 3)
            pen.setCosmetic(True)
            self.overlay = self.scene().addRect(self.selection, pen)
        else:
            self.overlay.setRect(self.selection)
        self.scene().setSceneRect(self.bounds)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = self.mapToScene(event.position().toPoint())
            self.press_position = event.position().toPoint()
            self.set_selection(QRectF(self.start, self.start))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.set_selection(QRectF(self.start, self.mapToScene(event.position().toPoint())))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.start is not None:
            point = self.mapToScene(event.position().toPoint())
            is_click = self.press_position is not None and (
                event.position().toPoint() - self.press_position).manhattanLength() <= 4
            self.set_selection(QRectF(self.start, point))
            self.start = None
            self.press_position = None
            self.selectionChanged.emit()
            if is_click:
                additive = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier |
                                                      Qt.KeyboardModifier.ShiftModifier))
                self.clicked.emit(point, additive)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def box(self):
        rect = self.selection.toAlignedRect().intersected(self.bounds.toRect())
        return dict(x=rect.x(), y=rect.y(), width=rect.width(), height=rect.height())


class CropDialog(QDialog):
    def __init__(self, image, model, parent=None, shelf=False, provider_name='OpenAI',
                 identifier=False, local_title_page=False, title_page_analysis=False):
        super().__init__(parent)
        self.local_title_page = bool(local_title_page)
        self.title_page_analysis = bool(title_page_analysis)
        self.setWindowTitle('Einzelnen Buchrücken auswählen')
        if shelf:
            self.setWindowTitle('Regalabschnitt für Buchrücken-Erkennung auswählen')
        elif identifier:
            self.setWindowTitle('ISBN oder Barcode auswählen')
        elif self.local_title_page:
            self.setWindowTitle('Titelblatt zuschneiden')
        elif self.title_page_analysis:
            self.setWindowTitle('Titelblatt für KI-Auswertung auswählen')
        self.resize(1050, 650)
        self.source = image
        self.jpeg = self.box = None
        layout = QVBoxLayout(self)
        text = QLabel('Links ein Rechteck um genau einen Buchrücken ziehen. Rechts siehst du den Ausschnitt, der übertragen wird.')
        if shelf:
            text.setText('Eine Regalreihe oder das gesamte Foto auswählen. Rechts siehst du das übertragene Bild. Maximal 60 Bereiche pro Anfrage; dichte Regale besser in Abschnitten erfassen.')
        elif identifier:
            text.setText('Ein Rechteck um Barcode oder gedruckte ISBN ziehen. Rechts siehst du genau den Ausschnitt, der übertragen wird.')
        elif self.local_title_page:
            text.setText('Links den gewünschten Titelblattbereich markieren. Rechts wird der lokal zu speichernde Ausschnitt angezeigt.')
        elif self.title_page_analysis:
            text.setText('Links den auszuwertenden Titelblattbereich markieren. Rechts siehst du genau den Ausschnitt, der nach Bestätigung übertragen wird.')
        text.setWordWrap(True)
        layout.addWidget(text)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.view = CropView(image)
        self.preview = PhotoView()
        split.addWidget(self.view)
        split.addWidget(self.preview)
        split.setSizes([660, 330])
        layout.addWidget(split, 1)
        row = QHBoxLayout()
        layout.addLayout(row)
        whole = QPushButton('Ganzes Foto (wenn es nur ein Buch zeigt)')
        if shelf:
            whole.setText('Ganzes Regalbild')
        elif identifier:
            whole.setText('Ganzes ISBN-/Barcodefoto')
        elif self.local_title_page:
            whole.setText('Ganzes Titelblattfoto')
        elif self.title_page_analysis:
            whole.setText('Ganzes Titelblatt')
        whole.clicked.connect(self.select_whole)
        row.addWidget(whole)
        fit = QPushButton('Bild einpassen')
        fit.clicked.connect(self.view.fit_photo)
        row.addWidget(fit)
        self.rotation = QComboBox()
        for degrees in (0, 90, 180, 270):
            self.rotation.addItem(str(degrees) + '° drehen', degrees)
        self.rotation.currentIndexChanged.connect(self.update_preview)
        row.addWidget(self.rotation)
        self.rotate_left = QPushButton('↶ 90° links')
        self.rotate_left.clicked.connect(lambda: self.rotate_by(-90))
        row.addWidget(self.rotate_left)
        self.rotate_right = QPushButton('↷ 90° rechts')
        self.rotate_right.clicked.connect(lambda: self.rotate_by(90))
        row.addWidget(self.rotate_right)
        if self.local_title_page:
            disclosure = ('Der zugeschnittene Ausschnitt wird ausschließlich lokal im '
                          'Projekt gespeichert. Es erfolgt keine KI- oder Netzwerkübertragung.')
        else:
            disclosure = (
                'Anbieter: ' + provider_name + ' · Modell: ' + model +
                '\nÜbertragen wird nur der Ausschnitt, ohne EXIF-/GPS-Daten. Kein automatischer Anbieter- oder Modellwechsel.'
                '\nMit „Kostenpflichtig auswerten“ stimmst du der Übertragung dieses angezeigten Ausschnitts und möglichen API-Kosten zu.')
        self.disclosure = QLabel(disclosure)
        self.disclosure.setTextFormat(Qt.TextFormat.PlainText)
        self.disclosure.setWordWrap(True)
        layout.addWidget(self.disclosure)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            'Zuschneiden und speichern' if self.local_title_page
            else 'Kostenpflichtig auswerten')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.view.selectionChanged.connect(self.update_preview)
        if shelf:
            self.rotation.setEnabled(False)
            self.rotate_left.setEnabled(False)
            self.rotate_right.setEnabled(False)
            self.select_whole()

    def select_whole(self):
        self.view.set_selection(self.view.bounds)
        self.update_preview()

    def rotate_by(self, degrees):
        target = (int(self.rotation.currentData()) + degrees) % 360
        index = self.rotation.findData(target)
        if index >= 0:
            self.rotation.setCurrentIndex(index)

    def update_enabled(self):
        box = self.view.box()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(min(box['width'], box['height']) >= 8)

    def update_preview(self):
        try:
            max_edge = None if self.local_title_page else 2400
            self.preview.show_image(crop_image(
                self.source, self.view.box(), self.rotation.currentData(), max_edge=max_edge))
        except ValueError:
            self.preview.show_photo()
        self.update_enabled()

    def accept(self):
        try:
            self.box = self.view.box()
            max_edge = None if self.local_title_page else 2400
            self.jpeg = jpeg_bytes(crop_image(
                self.source, self.box, self.rotation.currentData(), max_edge=max_edge))
        except ValueError as exc:
            QMessageBox.warning(self, 'Ausschnitt prüfen', str(exc))
            return
        super().accept()


class ReviewDialog(QDialog):
    def __init__(self, book, store, threshold=0.8, parent=None, photo=None):
        super().__init__(parent)
        self.setWindowTitle('KI-Vorschlag prüfen')
        self.resize(1120, 760)
        self.book = deepcopy(book)
        layout = QVBoxLayout(self)
        result = book.vision
        extraction = result['extraction']
        note = QLabel('KI-Konfidenzen sind unkalibrierte Schätzungen. Es fand noch kein Online-Abgleich statt.\n'
                      'Nur angehakte Felder werden übernommen. Vorschläge sind in der Tabelle korrigierbar.')
        note.setWordWrap(True)
        layout.addWidget(note)
        split = QSplitter(Qt.Orientation.Horizontal)
        original = PhotoView()
        original.show_photo(store.asset(photo.preview_path) if photo else None)
        cropped = PhotoView()
        evidence = book.vision_image_path or book.crop_path
        cropped.show_photo(store.asset(evidence) if evidence else None)
        if photo is None and book.title_page_path:
            original.show_photo(store.asset(book.title_page_path))
        split.addWidget(original)
        split.addWidget(cropped)
        layout.addWidget(split, 1)
        fit = QPushButton('Beide Bilder einpassen')
        fit.clicked.connect(lambda: (original.fit_photo(), cropped.fit_photo()))
        layout.addWidget(fit)
        info = QLabel(f"{result['provider']} / {result['model']} · KI-Gesamtwert: {extraction['overall']:.0%} · {result['extracted_at']}")
        info.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(info)
        self.table = QTableWidget(len(FIELDS), 5)
        self.table.setHorizontalHeaderLabels(['Übernehmen', 'Feld', 'Bisher', 'KI-Vorschlag (editierbar)', 'KI-Konfidenz'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, key in enumerate(FIELDS):
            current, proposed = getattr(book, key), extraction['fields'][key]
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            sensible = proposed is not None and (key not in ('isbn10', 'isbn13') or valid(proposed))
            check.setCheckState(Qt.CheckState.Checked if current is None and sensible else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, check)
            confidence = extraction['field_confidence'][key]
            for column, text in ((1, LABELS[key]), (2, '' if current is None else str(current)),
                                 (3, '' if proposed is None else str(proposed)), (4, '—' if confidence is None else f'{confidence:.0%}')):
                item = QTableWidgetItem(text)
                if column != 3:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if confidence is not None and confidence < threshold:
                    item.setBackground(QColor('#fff0cc'))
                    item.setForeground(QColor('#30230b'))
                self.table.setItem(row, column, item)
        layout.addWidget(self.table, 1)
        warnings = result['warnings'] + extraction['warnings']
        hint = QLabel('\n'.join(warnings) if warnings else 'Bitte Autor, Titel und Verlag mit dem Bild vergleichen.')
        hint.setTextFormat(Qt.TextFormat.PlainText)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.confirm_button = QPushButton('Speichern und bestätigen')
        self.confirm_button.setDefault(True)
        self.confirm_button.clicked.connect(self.accept)
        row.addWidget(self.confirm_button)
        self.draft_button = QPushButton('Als Entwurf speichern')
        self.draft_button.setAutoDefault(False)
        self.draft_button.clicked.connect(self.save_draft)
        row.addWidget(self.draft_button)
        self.rescan_button = QPushButton('Nachscan nötig')
        self.rescan_button.setAutoDefault(False)
        self.rescan_button.clicked.connect(self.needs_scan)
        row.addWidget(self.rescan_button)
        self.later_button = QPushButton('Später prüfen')
        self.later_button.setAutoDefault(False)
        self.later_button.clicked.connect(self.reject)
        row.addWidget(self.later_button)
        self.action_buttons = [self.confirm_button, self.draft_button,
                               self.rescan_button, self.later_button]

    def selected_values(self):
        values = {}
        for row, key in enumerate(FIELDS):
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked:
                value = self.table.item(row, 3).text().strip()
                values[key] = (int(value) if value else None) if key == 'publication_year' else value or None
        return values

    def save(self, status):
        try:
            self.book = apply_review(self.book, self.selected_values(), status=status)
        except ValueError as exc:
            QMessageBox.warning(self, 'Angaben prüfen', 'Die Auswahl konnte nicht gespeichert werden:\n' + str(exc))
            return
        super().accept()

    def save_draft(self):
        self.save('needs_manual_review')

    def accept(self):
        self.save('manual_confirmed')

    def needs_scan(self):
        self.save('needs_scan')
