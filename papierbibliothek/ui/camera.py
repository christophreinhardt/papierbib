"""Live camera dialog with local ISBN-barcode recognition."""
from time import monotonic

from qt.core import (
    QCamera, QComboBox, QDialog, QHBoxLayout, QLabel, QMediaCaptureSession,
    QMediaDevices, QPushButton, QThread, QTimer, QVBoxLayout, QVideoWidget, Qt,
    pyqtSignal,
)

from ..barcode import decode_qimage


# Keep detached workers alive if a user closes the dialog during recognition.
# QThread destruction while run() is active can terminate the entire process.
_ACTIVE_SCAN_TASKS = set()


def largest_camera_format(device):
    """Return the highest-resolution format advertised by a camera device."""
    try:
        formats = list(device.videoFormats())
    except (AttributeError, TypeError, RuntimeError):
        return None
    if not formats:
        return None

    def sort_key(camera_format):
        size = camera_format.resolution()
        try:
            fps = float(camera_format.maxFrameRate())
        except (AttributeError, TypeError, ValueError):
            fps = 0.0
        return (size.width() * size.height(), size.width(), size.height(), fps)

    return max(formats, key=sort_key)


class BarcodeTask(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal()

    def __init__(self, image):
        super().__init__()
        self.image = image

    def run(self):
        try:
            self.result.emit(decode_qimage(self.image))
        except Exception:
            self.failed.emit()
        finally:
            self.image = None


def _release_task(task):
    _ACTIVE_SCAN_TASKS.discard(task)
    task.deleteLater()


class CameraDialog(QDialog):
    """Scan locally; only the explicit KI button returns a frame for upload."""

    def __init__(self, parent=None, devices=None, start_camera=True,
                 title_page=False):
        super().__init__(parent)
        self.title_page = bool(title_page)
        self.setWindowTitle('Titelblatt fotografieren' if self.title_page
                            else 'Buch per Kamera erfassen')
        self.resize(900, 680)
        self.detected_isbn = None
        self.captured_image = None
        self._last_image = None
        self._last_scan = 0.0
        self._candidate = None
        self._candidate_count = 0
        self._candidate_seen_at = 0.0
        self._closing = False
        self._scan_task = None
        self._devices = list(QMediaDevices.videoInputs() if devices is None else devices)
        self._camera = None
        self.camera_resolution = None
        self._session = QMediaCaptureSession(self)

        layout = QVBoxLayout(self)
        if self.title_page:
            note_text = (
                'Richte das Titelblatt vollständig und möglichst gerade aus. Erst ein Klick '
                'auf „Titelblatt aufnehmen“ übernimmt ein einzelnes Bild. Die Vorschau '
                'wird nicht gespeichert oder übertragen.')
        else:
            note_text = (
                'Halte den ISBN-Barcode groß, scharf und gut beleuchtet in die Bildmitte; '
                'langsames Kippen kann bei Spiegelungen helfen. '
                'Die Erkennung läuft lokal; Kamerabilder werden nicht gespeichert oder '
                'übertragen. Nach zwei gleichen Lesungen startet die ISBN-Abfrage bei lobid.')
        note = QLabel(note_text, self)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.video = QVideoWidget(self)
        self.video.setMinimumHeight(440)
        layout.addWidget(self.video, 1)
        self._session.setVideoOutput(self.video)
        self.video.videoSink().videoFrameChanged.connect(self._frame_changed)

        row = QHBoxLayout()
        layout.addLayout(row)
        row.addWidget(QLabel('Kamera:', self))
        self.camera_choice = QComboBox(self)
        for device in self._devices:
            self.camera_choice.addItem(device.description())
        self.camera_choice.currentIndexChanged.connect(self._select_camera)
        row.addWidget(self.camera_choice, 1)
        self.ai_button = QPushButton(
            'Titelblatt aufnehmen' if self.title_page
            else 'ISBN-Text kostenpflichtig mit KI lesen …', self)
        self.ai_button.clicked.connect(self._capture_for_ai)
        self.ai_button.setEnabled(False)
        row.addWidget(self.ai_button)
        cancel = QPushButton('Abbrechen', self)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.status = QLabel('Kamera wird gestartet …', self)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        if not self._devices:
            self.status.setText(
                'Keine Kamera gefunden. Bitte Kamera anschließen und den Dialog erneut öffnen.')
            self.camera_choice.setEnabled(False)
        elif start_camera:
            self._select_camera(0)

    def _select_camera(self, index):
        if not 0 <= index < len(self._devices):
            return
        if self._camera is not None:
            self._camera.stop()
            self._camera.deleteLater()
        self._camera = QCamera(self._devices[index], self)
        self._camera.errorOccurred.connect(self._camera_error)
        selected_format = largest_camera_format(self._devices[index])
        if selected_format is not None:
            try:
                self._camera.setCameraFormat(selected_format)
                size = selected_format.resolution()
                self.camera_resolution = (size.width(), size.height())
            except (AttributeError, RuntimeError):
                self.camera_resolution = None
        self._session.setCamera(self._camera)
        self._candidate = None
        self._candidate_count = 0
        self._candidate_seen_at = 0.0
        if self.title_page and self.camera_resolution:
            self.status.setText(
                'Maximale Kameraauflösung %d × %d · Titelblatt ausrichten und Aufnahme drücken …'
                % self.camera_resolution)
        else:
            self.status.setText('Titelblatt ausrichten und Aufnahme drücken …'
                                if self.title_page else 'Suche ISBN-Barcode …')
        self._camera.start()

    def _camera_error(self, error, message):
        if message:
            self.status.setText('Kamerafehler: ' + message)

    def _observe_candidate(self, value, now):
        """Stabilize intermittent live-decoder results without accepting stale data."""
        if value == self._candidate and value:
            self._candidate_count += 1
            self._candidate_seen_at = now
        elif value:
            self._candidate, self._candidate_count = value, 1
            self._candidate_seen_at = now
        elif now - self._candidate_seen_at > 1.75:
            self._candidate, self._candidate_count = None, 0
        return bool(value and self._candidate_count >= 2)

    def _frame_changed(self, frame):
        if self._closing:
            return
        try:
            image = frame.toImage()
        except Exception:
            self.status.setText('Ein Kameraframe konnte nicht gelesen werden; Scan läuft weiter.')
            return
        if image.isNull():
            return
        now = monotonic()
        if self.title_page:
            if now - self._last_scan < .10:
                return
            self._last_scan = now
            self._last_image = image.copy()
            self.ai_button.setEnabled(True)
            self.status.setText('Bereit für die Aufnahme.')
            return
        if (now - self._last_scan < .25 or
                (self._scan_task is not None and self._scan_task.isRunning())):
            return
        self._last_scan = now
        # Detach from the multimedia frame before it is released by Qt.
        image = image.copy()
        self._last_image = image
        self.ai_button.setEnabled(True)
        task = BarcodeTask(image)
        self._scan_task = task
        _ACTIVE_SCAN_TASKS.add(task)
        task.result.connect(self._scan_result)
        task.failed.connect(self._scan_failed)
        task.finished.connect(self._scan_finished)
        task.finished.connect(lambda current=task: _release_task(current))
        task.start()

    def _scan_result(self, value):
        if self._closing:
            return
        now = monotonic()
        accepted = self._observe_candidate(value, now)
        if value:
            self.status.setText('ISBN erkannt: %s (%d/2)' %
                                (value, self._candidate_count))
        if accepted:
            self.detected_isbn = value
            # Never stop/delete the camera from inside its frame callback.
            self._closing = True
            QTimer.singleShot(0, self.accept)

    def _scan_failed(self):
        if not self._closing:
            self.status.setText(
                'Dieses Kameraframe konnte nicht ausgewertet werden; Scan läuft weiter.')

    def _scan_finished(self):
        if self.sender() is self._scan_task:
            self._scan_task = None

    def _capture_for_ai(self):
        if self._last_image is not None and not self._last_image.isNull():
            self.captured_image = self._last_image.copy()
            self.accept()

    def done(self, result):
        self._closing = True
        try:
            self.video.videoSink().videoFrameChanged.disconnect(self._frame_changed)
        except (RuntimeError, TypeError):
            pass
        if self._camera is not None:
            self._camera.stop()
        if self._scan_task is not None:
            self._scan_task.requestInterruption()
            self._scan_task = None
        super().done(result)
