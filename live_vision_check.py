"""One explicitly opted-in API check using a synthetic spine, never user photographs."""
import os
from pathlib import Path
import sys
import threading

if '--send-synthetic-image' not in sys.argv:
    raise SystemExit('Opt-in required: calibre-debug live_vision_check.py -- --send-synthetic-image')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibre.gui2 import Application
from qt.core import QImage, QPainter, QColor, QFont, QFontDatabase
from papierbibliothek.image_processing.crop import jpeg_bytes
from papierbibliothek.vision.provider import OpenAIVisionProvider
from papierbibliothek.vision.gemini import GeminiVisionProvider
from papierbibliothek.vision.schema import VisionError

app = Application([])
font = Path('C:/Windows/Fonts/segoeui.ttf')
if font.exists():
    QFontDatabase.addApplicationFont(str(font))
image = QImage(520, 1200, QImage.Format.Format_RGB32)
image.fill(QColor('#f0e6c9'))
painter = QPainter(image)
painter.setPen(QColor('#1a2528'))
painter.setFont(QFont('Segoe UI', 28))
painter.drawText(45, 160, 'LENA WINTER')
painter.drawText(45, 450, 'DAS BLAUE')
painter.drawText(45, 515, 'REGAL')
painter.setFont(QFont('Segoe UI', 22))
painter.drawText(45, 1020, 'NORDLICHT VERLAG')
painter.end()
shelf_mode = '--shelf' in sys.argv
if shelf_mode:
    shelf_image = QImage(1620, 1260, QImage.Format.Format_RGB32)
    shelf_image.fill(QColor('#454545'))
    painter = QPainter(shelf_image)
    for index in range(3):
        painter.drawImage(10 + index * 540, 20, image)
    painter.end()
    image = shelf_image
try:
    provider = GeminiVisionProvider(os.environ.get('GEMINI_API_KEY', '')) if '--gemini' in sys.argv else OpenAIVisionProvider(os.environ.get('OPENAI_API_KEY', ''))
    method = provider.detect_shelf if shelf_mode else provider.analyze
    result = method(jpeg_bytes(image), consent=True, cancel=threading.Event())
except VisionError as exc:
    raise SystemExit(str(exc)) from None
if shelf_mode:
    print('Model:', result['model'])
    print('Synthetic regions:', len(result['extraction']['regions']))
    print('Usage:', result['usage'])
    if len(result['extraction']['regions']) != 3 or result['extraction']['truncated']:
        raise SystemExit('Schema succeeded, but synthetic shelf localization needs review.')
    print('LIVE SYNTHETIC SHELF CHECK PASSED')
    raise SystemExit(0)
fields = result['extraction']['fields']
print('Model:', result['model'])
print('Provider:', result['provider'])
print('Synthetic title:', fields['title'])
print('Synthetic author:', fields['author'])
print('Synthetic publisher:', fields['publisher'])
print('Usage:', result['usage'])
if 'BLAUE' not in (fields['title'] or '').upper() or 'WINTER' not in (fields['author'] or '').upper():
    raise SystemExit('Schema succeeded, but synthetic spine recognition needs review.')
print('LIVE SYNTHETIC CHECK PASSED')
