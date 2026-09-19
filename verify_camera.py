"""Opt-in hardware smoke test: receive frames without saving or uploading them."""
from calibre.gui2 import Application
from qt.core import QMediaDevices, QTimer

from papierbibliothek.ui.camera import CameraDialog


app = Application([])
devices = list(QMediaDevices.videoInputs())
if not devices:
    raise SystemExit('Keine Kamera gefunden.')
dialog = CameraDialog(devices=devices)
frames = {'count': 0, 'width': 0, 'height': 0}
heartbeat = {'count': 0}


def received(frame):
    image = frame.toImage()
    if not image.isNull():
        frames['count'] += 1
        frames['width'], frames['height'] = image.width(), image.height()


dialog.video.videoSink().videoFrameChanged.connect(received)
timer = QTimer()
timer.setInterval(100)
timer.timeout.connect(lambda: heartbeat.__setitem__('count', heartbeat['count'] + 1))
timer.start()
QTimer.singleShot(5000, dialog.reject)
dialog.exec()
if frames['count'] < 1:
    raise SystemExit('Kamera geöffnet, aber innerhalb von 5 Sekunden kein Frame empfangen.')
if heartbeat['count'] < 30:
    raise SystemExit('Die Qt-Oberfläche reagierte während der Barcodeerkennung nicht ausreichend.')
print('Kamera:', devices[0].description())
print('Frames empfangen:', frames['count'])
print('Letzte Framegröße:', frames['width'], 'x', frames['height'])
print('UI-Heartbeats:', heartbeat['count'])
print('Keine Bilder gespeichert oder übertragen.')
