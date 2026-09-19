from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import csv
import unittest
from unittest.mock import Mock, patch

from qt.core import (QImage, QColor, QRectF, QApplication, QDialog, QDialogButtonBox,
                     QAbstractItemView, Qt)
from papierbibliothek.models import Project
from papierbibliothek.persistence.project import ProjectStore
from papierbibliothek.image_processing.photos import import_batch, read_image
from papierbibliothek.vision.schema import VisionError, VisionCancelled
from papierbibliothek.vision.provider import OpenAIVisionProvider
from papierbibliothek.vision.shelf import validate_shelf, pixel_box, overlap
from papierbibliothek.vision.shelf_workflow import save_regions, save_corrections
from papierbibliothek.ui.shelf import RegionsDialog, draw_regions
from papierbibliothek.ui.main import MainDialog
from papierbibliothek.ui.vision import CropDialog
from papierbibliothek.import_export.export import export_project


def shelf():
    return {'regions': [dict(box=dict(x=20,y=100,width=200,height=800),kind='spine',confidence=0.9,warnings=[]),
                        dict(box=dict(x=400,y=100,width=400,height=800),kind='group',confidence=0.4,warnings=['Nicht trennbar'])],
            'truncated': False, 'warnings': []}


class ShelfContractTests(unittest.TestCase):
    def test_strict_contract(self):
        self.assertEqual(validate_shelf(shelf()), shelf())
        for field, value in [('confidence', True), ('confidence', float('nan')), ('kind', 'invented'), ('warnings', 'text'), ('warnings', ['x']*11), ('box', dict(x=900,y=0,width=200,height=10))]:
            data = shelf()
            data['regions'][0][field] = value
            with self.assertRaises(VisionError): validate_shelf(data)
        for mutation in ('extra', 'count', 'truncated', 'float', 'negative'):
            data = shelf()
            if mutation == 'extra': data['secret'] = 'no'
            if mutation == 'count': data['regions'] *= 31
            if mutation == 'truncated': data['truncated'] = 'false'
            if mutation == 'float': data['regions'][0]['box']['x'] = 0.5
            if mutation == 'negative': data['regions'][0]['box']['x'] = -1
            with self.assertRaises(VisionError): validate_shelf(data)

    def test_mapping_full_partial_and_edges(self):
        frame = dict(x=300,y=500,width=4001,height=2003)
        self.assertEqual(pixel_box(dict(x=0,y=0,width=1000,height=1000), frame), frame)
        box = pixel_box(dict(x=500,y=500,width=500,height=500), frame)
        self.assertEqual(box, dict(x=2300,y=1501,width=2001,height=1002))
        self.assertEqual(overlap(frame, frame), 1)
        self.assertEqual(overlap(dict(x=0,y=0,width=10,height=10), frame), 0)

    def test_request_schema_consent_and_refusal(self):
        response = dict(status='completed', output=[dict(type='message', content=[dict(type='output_text',text=json.dumps(shelf()))])])
        transport = Mock(return_value=io.BytesIO(json.dumps(response).encode()))
        provider = OpenAIVisionProvider('not-real-secret', transport=transport)
        with self.assertRaises(VisionError): provider.detect_shelf(b'\xff\xd8x',consent=False,cancel=threading.Event())
        transport.assert_not_called()
        result = provider.detect_shelf(b'\xff\xd8x',consent=True,cancel=threading.Event())
        request = json.loads(transport.call_args.args[0].data)
        self.assertEqual(request['text']['format']['name'], 'shelf_regions')
        self.assertTrue(request['text']['format']['strict'])
        self.assertFalse(request['store'])
        self.assertNotIn('not-real-secret', json.dumps(result))
        self.assertEqual(result['extraction'], shelf())
        response['output'][0]['content'] = [dict(type='refusal')]
        transport.return_value = io.BytesIO(json.dumps(response).encode())
        with self.assertRaises(VisionError):
            provider.detect_shelf(b'\xff\xd8x',consent=True,cancel=threading.Event())

    def test_v1_v2_migration(self):
        for version in (1,2):
            data = Project('Alt').to_dict()
            data['schema_version'] = version
            self.assertEqual(Project.from_dict(data).schema_version, 5)
            self.assertEqual(data['schema_version'], version)


class ShelfWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.image = QImage(800, 500, QImage.Format.Format_RGB32)
        self.image.fill(QColor('white'))
        self.path = root/'shelf.png'
        self.assertTrue(self.image.save(str(self.path)))
        self.store, self.project = ProjectStore.create(root/'project', 'Regal')
        self.cancel = threading.Event()
        import_batch(self.store,self.project,[self.path],'Fach 1',self.cancel,lambda text: None)
        self.photo = self.project.photos[0]
        self.frame = dict(x=0,y=0,width=800,height=500)
        self.result = dict(provider='openai',model='test',extraction=shelf(),usage={})

    def save(self):
        return save_regions(self.store,self.project,self.photo,self.image,self.frame,self.result,self.cancel)

    def test_persist_crops_group_status_and_reload(self):
        before = self.path.read_bytes()
        result = self.save()
        loaded = self.store.load()
        self.assertEqual(result['added'], 2)
        self.assertEqual([b.status for b in loaded.books], ['needs_manual_review','needs_scan'])
        self.assertIsNone(loaded.books[0].title)
        self.assertIsNone(loaded.books[0].vision)
        self.assertTrue(self.store.asset(loaded.books[0].crop_path).is_file())
        self.assertEqual(loaded.books[0].bounding_box,dict(x=16,y=50,width=160,height=400))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(loaded.books[0].detection['image_width'],800)

    def test_repeated_detection_preserves_books(self):
        self.project = self.save()['project']
        self.project.books[0].title = 'Manuell behalten'
        self.store.save(self.project)
        result = self.save()
        self.assertEqual(result['duplicates'],2)
        self.assertEqual(result['added'],0)
        self.assertEqual(result['project'].books[0].title,'Manuell behalten')

    def test_cancel_and_storage_failure_do_not_change_manifest(self):
        before = self.store.path.read_bytes()
        self.cancel.set()
        with self.assertRaises(VisionCancelled): self.save()
        self.assertEqual(self.store.path.read_bytes(),before)
        self.cancel.clear()
        with patch.object(self.store,'save',side_effect=OSError('test')):
            with self.assertRaises(OSError): self.save()
        self.assertEqual(self.store.path.read_bytes(),before)
        self.assertFalse(self.project.books)

    def test_truncation_overlap_and_tiny_regions(self):
        self.result['extraction']['truncated'] = True
        self.result['extraction']['regions'].append(dict(box=dict(x=100,y=100,width=200,height=800),kind='spine',confidence=.5,warnings=[]))
        self.result['extraction']['regions'].append(dict(box=dict(x=0,y=0,width=1,height=1),kind='spine',confidence=.5,warnings=[]))
        result = self.save()
        self.assertEqual(result['added'],3)
        self.assertTrue(result['warnings'])
        self.assertTrue(any('Überlappung' in w for w in result['project'].books[-1].detection['warnings']))

    def test_editor_correction_preserves_title_and_creates_new_crop(self):
        project = self.save()['project']
        project.books[0].title = 'Eigenes Buch'
        dialog = RegionsDialog(project,self.photo,self.image)
        self.addCleanup(dialog.close)
        dialog.view.set_selection(QRectF(5,10,120,450))
        dialog.replace()
        dialog.confirm()
        self.assertIsNotNone(dialog.current().detection['reviewed_at'])
        self.assertIsNone(dialog.current().detection['confidence'])
        result = save_corrections(self.store,project,dialog.project,self.photo,self.image,self.cancel)
        book = result['project'].books[0]
        self.assertEqual(book.title,'Eigenes Buch')
        self.assertEqual(book.bounding_box,dict(x=5,y=10,width=120,height=450))
        self.assertNotEqual(book.crop_path,project.books[0].crop_path)
        self.assertTrue(self.store.asset(project.books[0].crop_path).exists())

    def test_editor_manual_add_group_ignore_and_cancel(self):
        dialog = RegionsDialog(self.project,self.photo,self.image)
        self.addCleanup(dialog.close)
        dialog.view.set_selection(QRectF(10,10,90,450))
        dialog.add()
        self.assertEqual(len(dialog.project.books),1)
        dialog.toggle_group()
        self.assertEqual(dialog.current().status,'needs_scan')
        dialog.ignore()
        self.assertEqual(dialog.current().status,'rejected')
        dialog.reject()
        self.assertFalse(self.project.books)
        self.assertFalse(self.store.load().books)

    def test_editor_defaults_to_included_supports_multi_and_photo_selection(self):
        project = self.save()['project']
        dialog = RegionsDialog(project,self.photo,self.image)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.regions.selectionMode(),
                         QAbstractItemView.SelectionMode.ExtendedSelection)
        self.assertTrue(all(dialog.regions.item(row).checkState() == Qt.CheckState.Checked
                            for row in range(dialog.regions.count())))

        first = dialog.regions.item(0)
        first.setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dialog.project.books[0].status,'rejected')
        first.setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog.project.books[0].status,'needs_manual_review')

        dialog.regions.clearSelection()
        dialog.regions.item(0).setSelected(True)
        dialog.regions.item(1).setSelected(True)
        self.assertEqual(len(dialog.selected_books()),2)
        dialog.confirm()
        self.assertTrue(all(book.detection['reviewed_at'] for book in dialog.selected_books()))

        box = dialog.project.books[0].bounding_box
        dialog.select_at(QRectF(box['x'],box['y'],box['width'],box['height']).center())
        self.assertEqual([book.book_id for book in dialog.selected_books()],
                         [dialog.project.books[0].book_id])

    def test_main_overlay_and_controls(self):
        self.save()
        window = MainDialog()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        self.assertTrue(window.shelf_button.isEnabled())
        self.assertGreaterEqual(len(window.viewer.scene().items()),5)
        window.show()
        QApplication.processEvents()
        window.close()
        self.assertFalse(window.regions_button.isEnabled())

    def test_exif_oriented_coordinates(self):
        from PIL import Image
        path = Path(self.temp.name)/'rotated.jpg'
        source = Image.new('RGB',(60,100),'red')
        exif = source.getexif()
        exif[274] = 6
        source.save(path,exif=exif)
        oriented = read_image(path,max_edge=None)[0]
        self.assertEqual((oriented.width(),oriented.height()),(100,60))
        box = pixel_box(dict(x=0,y=0,width=1000,height=1000),dict(x=0,y=0,width=100,height=60))
        self.assertEqual((box['width'],box['height']),(100,60))

    def test_group_cannot_be_confirmed_as_single_book(self):
        book = self.save()['project'].books[1]
        book.title = 'Ungeprüfte Gruppe'
        for status in ('manual_confirmed','matched','imported'):
            book.status = status
            with self.assertRaises(ValueError): book.validate()

    def test_export_includes_boxes_and_detection(self):
        project = self.save()['project']
        csv_path = Path(self.temp.name)/'export.csv'
        json_path = Path(self.temp.name)/'export.json'
        export_project(project,csv_path,'csv')
        export_project(project,json_path,'json')
        with csv_path.open(encoding='utf-8-sig',newline='') as stream:
            rows = list(csv.DictReader(stream,delimiter=';'))
        self.assertEqual(json.loads(rows[1]['detection'])['kind'],'group')
        self.assertEqual(json.loads(rows[0]['bounding_box']),project.books[0].bounding_box)
        self.assertEqual(Project.from_dict(json.loads(json_path.read_text(encoding='utf-8'))).to_dict(),project.to_dict())

    def test_shelf_upload_paid_action_tracks_valid_crop(self):
        dialog = CropDialog(self.image,'test',shelf=True)
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.rotation.isEnabled())
        self.assertEqual(dialog.view.box(),self.frame)
        self.assertTrue(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.view.set_selection(QRectF(10,10,100,100))
        dialog.update_preview()
        self.assertTrue(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.view.set_selection(QRectF(10,10,2,2))
        dialog.update_preview()
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())

    def test_background_shelf_to_saved_editor_flow(self):
        window = MainDialog()
        window.show()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        fake = Mock(model='test')
        ui_thread = threading.get_ident()
        def detect(*args,**kwargs):
            self.assertNotEqual(threading.get_ident(),ui_thread)
            return self.result
        fake.detect_shelf.side_effect = detect
        with patch.object(window,'selected_provider',return_value=(fake,'OpenAI')), \
             patch('papierbibliothek.ui.main.CropDialog') as upload, \
             patch('papierbibliothek.ui.main.RegionsDialog') as editor:
            upload.return_value.exec.return_value = QDialog.DialogCode.Accepted
            upload.return_value.jpeg = b'\xff\xd8test'
            upload.return_value.box = self.frame
            editor.return_value.exec.return_value = QDialog.DialogCode.Rejected
            window.prepare_shelf(True)
            deadline = time.monotonic()+10
            while window.task is not None and time.monotonic()<deadline:
                QApplication.processEvents()
                time.sleep(.01)
            self.assertIsNone(window.task)
            self.assertIsNone(window.pending_error)
            self.assertEqual(len(window.project.books),2)
            fake.detect_shelf.assert_called_once()
            editor.return_value.exec.assert_called_once()
        self.assertEqual(len(ProjectStore(self.store.root).load().books),2)
