"""Render synthetic demo data offscreen for visual QA; never uses private photos."""
import os
from pathlib import Path
import sys
import tempfile
import threading

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
from calibre.gui2 import Application
from qt.core import QFontDatabase, QFont, QImage, QPainter, QColor, Qt
from papierbibliothek.models import Book
from papierbibliothek.persistence.project import ProjectStore
from papierbibliothek.image_processing.photos import import_batch
from papierbibliothek.ui.main import MainDialog
from papierbibliothek.ui.widgets import BookDialog
from papierbibliothek.ui.vision import CropDialog, ReviewDialog, SettingsDialog
from papierbibliothek.ui.calibre_import import ImportDialog
from papierbibliothek.vision.gemini import DEFAULT_GEMINI_MODEL
from papierbibliothek.ui.shelf import RegionsDialog
from papierbibliothek.models import now
from papierbibliothek.vision.schema import FIELDS
from papierbibliothek.vision.provider import DEFAULT_MODEL
from papierbibliothek.vision.workflow import save_proposal
from papierbibliothek.image_processing.crop import crop_image, jpeg_bytes

app = Application([])
font_path = Path('C:/Windows/Fonts/segoeui.ttf')
if font_path.exists():
    QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont('Segoe UI', 10))
output = root / 'test-results'
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='papierbibliothek-preview-') as temp:
    store, project = ProjectStore.create(Path(temp) / 'Sammlung', 'Meine Papierbibliothek')
    source = Path(temp) / 'Regal-A.jpg'
    image = QImage(1000, 420, QImage.Format.Format_RGB32)
    image.fill(QColor('#ebe5dc'))
    painter = QPainter(image)
    painter.fillRect(20, 365, 960, 25, QColor('#8a6347'))
    titles = ['FAUST', 'DIE VERWANDLUNG', 'BUDDENBROOKS', 'DER PROZESS', 'UNBEKANNT', 'GEDICHTE']
    colors = ['#385c60', '#9c5044', '#5c6682', '#bc944d', '#827975', '#447458']
    for i, title in enumerate(titles):
        x = 70 + i * 145
        painter.fillRect(x, 40 + i % 2 * 25, 116, 325 - i % 2 * 25, QColor(colors[i]))
        painter.save()
        painter.translate(x + 75, 335)
        painter.rotate(-90)
        painter.setPen(QColor('white'))
        painter.setFont(QFont('Segoe UI', 16))
        painter.drawText(0, 0, title)
        painter.restore()
    painter.end()
    image.save(str(source), 'JPEG')
    import_batch(store, project, [source], 'Arbeitszimmer · Regal A · Fach 2', threading.Event(), lambda value: None)
    photo = project.photos[0]
    project.books = [
        Book(title='Faust', author='Johann Wolfgang von Goethe', publisher='Reclam', status='manual_confirmed', spine_position='1 von links'),
        Book(title='Die Verwandlung', author='Franz Kafka', status='manual_confirmed', spine_position='2 von links'),
        Book(title='Buddenbrooks', author='Thomas Mann', status='needs_manual_review', spine_position='3 von links'),
        Book(title='Der Prozess', author='Franz Kafka', status='needs_scan', spine_position='4 von links'),
        Book(status='needs_scan', notes='Titel unleserlich; Titelblatt nachfotografieren', spine_position='5 von links'),
    ]
    for index, book in enumerate(project.books):
        book.photo_id, book.image_path, book.location = photo.photo_id, photo.image_path, photo.location
        book.bounding_box = dict(x=70+index*145,y=40+index%2*25,width=116,height=325-index%2*25)
        book.detection = dict(provider='demo',model='synthetic',confidence=.92 if index < 4 else .4,
                              kind='spine' if index < 4 else 'group',warnings=[] if index < 4 else ['Grenzen prüfen: mehrere Bücher möglich.'],
                              detected_at=now(),reviewed_at=None,image_width=1000,image_height=420)
    store.save(project)
    window = MainDialog()
    if not window.load_project(store.path):
        raise RuntimeError('Demo-Projekt konnte nicht geladen werden')
    window.show()
    app.processEvents()
    window.viewer.fit_photo()
    window.grab().save(str(output / 'hauptfenster.png'))
    regions = RegionsDialog(project, photo, image, window)
    regions.show()
    app.processEvents()
    regions.view.fit_photo()
    regions.grab().save(str(output / 'regal-rahmen.png'))
    regions.close()
    shelf_upload = CropDialog(image, DEFAULT_MODEL, window, shelf=True)
    shelf_upload.show()
    app.processEvents()
    shelf_upload.grab().save(str(output / 'regal-upload.png'))
    shelf_upload.close()
    from unittest.mock import patch
    with patch('papierbibliothek.ui.vision.settings', return_value=dict(
            provider='gemini', model=DEFAULT_MODEL, gemini_model=DEFAULT_GEMINI_MODEL,
            review_threshold=.8, metadata_threshold=.88, metadata_offline=False,
            use_openlibrary=True, use_googlebooks=True, use_dnb=True, custom_url='')):
        config = SettingsDialog(parent=window)
        config.show()
        app.processEvents()
        config.grab().save(str(output / 'ki-anbieter.png'))
        config.close()
    gemini_crop = CropDialog(image, DEFAULT_GEMINI_MODEL, window, shelf=True, provider_name='Google Gemini')
    gemini_crop.show()
    app.processEvents()
    gemini_crop.grab().save(str(output / 'gemini-upload.png'))
    gemini_crop.close()
    editor = BookDialog(project, book=project.books[0], parent=window)
    editor.show()
    app.processEvents()
    editor.grab().save(str(output / 'buch-erfassen.png'))
    editor.close()
    crop = CropDialog(image, DEFAULT_MODEL, parent=window)
    crop.show()
    app.processEvents()
    from qt.core import QRectF
    crop.view.set_selection(QRectF(60, 30, 140, 340))
    crop.update_preview()
    crop.view.fit_photo()
    app.processEvents()
    crop.grab().save(str(output / 'ki-ausschnitt.png'))
    crop.close()
    fields = dict.fromkeys(FIELDS)
    fields.update(title='Faust', author='Johann Wolfgang von Goethe', publisher='Reclam', raw_text='FAUST')
    extraction = {'fields': fields, 'field_confidence': {k: (0.92 if k != 'publisher' else 0.55) if v else None for k, v in fields.items()},
                  'overall': 0.75, 'readability': 'partial', 'warnings': ['Demodaten: Verlag bitte am Buch prüfen.']}
    box = dict(x=60, y=30, width=140, height=340)
    result = save_proposal(store, project, photo, jpeg_bytes(crop_image(image, box)), box,
                          dict(provider='openai', model=DEFAULT_MODEL, extraction=extraction, usage={}), threading.Event(), project.books[0].book_id)
    review = ReviewDialog(result['project'].books[0], store, photo=photo, parent=window)
    review.show()
    app.processEvents()
    review.grab().save(str(output / 'ki-pruefen.png'))
    review.close()
    import_preview = ImportDialog([
        {'book_id':'1','title':'Faust','author':'Johann Wolfgang von Goethe','isbn':'9783150000014',
         'status':'matched','duplicates':[],'calibre_book_id':None},
        {'book_id':'2','title':'Die Verwandlung','author':'Franz Kafka','isbn':'9783150099001',
         'status':'probable_match','duplicates':[42],'calibre_book_id':None},
    ], parent=window)
    import_preview.show()
    app.processEvents()
    import_preview.grab().save(str(output / 'calibre-import.png'))
    import_preview.close()
    window.close()
print(output)
