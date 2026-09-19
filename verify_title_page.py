"""Hardware smoke test for explicit title-page capture and local crop."""
from calibre.gui2 import Application
from qt.core import QDialog, QImage, QMediaDevices, QRectF, QTimer

from papierbibliothek.ui.camera import CameraDialog
from papierbibliothek.ui.vision import CropDialog


app = Application([])
devices = list(QMediaDevices.videoInputs())
if not devices:
    raise SystemExit('Keine Kamera gefunden.')
dialog = CameraDialog(devices=devices, title_page=True)


def capture_when_ready():
    if dialog.ai_button.isEnabled():
        dialog._capture_for_ai()
    else:
        QTimer.singleShot(100, capture_when_ready)


QTimer.singleShot(300, capture_when_ready)
QTimer.singleShot(5000, dialog.reject)
if dialog.exec() != QDialog.DialogCode.Accepted or dialog.captured_image is None:
    raise SystemExit('Innerhalb von 5 Sekunden konnte kein Titelblattfoto aufgenommen werden.')
image = dialog.captured_image
crop = CropDialog(image, '', local_title_page=True)
crop.view.set_selection(QRectF(5, 5, image.width() - 10, image.height() - 10))
crop.update_preview()
crop.rotate_by(90)
crop.accept()
if crop.result() != QDialog.DialogCode.Accepted or not crop.jpeg.startswith(b'\xff\xd8'):
    raise SystemExit('Der lokale Titelblatt-Ausschnitt konnte nicht erstellt werden.')
result = QImage.fromData(crop.jpeg, 'JPEG')
if result.isNull() or result.width() >= result.height():
    raise SystemExit('Die Drehung des Titelblatts wurde nicht in das JPEG übernommen.')
print('Kamera:', devices[0].description())
print('Aufnahme:', image.width(), 'x', image.height())
print('Gedrehter Ausschnitt:', result.width(), 'x', result.height(),
      '·', len(crop.jpeg), 'Bytes')
print('Keine Bilder gespeichert oder übertragen.')
