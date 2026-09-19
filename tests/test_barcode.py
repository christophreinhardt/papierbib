import tempfile
import threading
from time import perf_counter
import unittest
from pathlib import Path
from unittest.mock import patch

from qt.core import QApplication, QDialog, QImage, QPainter, QTransform, Qt

from papierbibliothek.barcode import (
    decode_modules, decode_qimage, decode_rows, encode_ean13,
)
from papierbibliothek.metadata_providers.base import MetadataRecord, ProviderError
from papierbibliothek.metadata_providers.workflow import search_book
from papierbibliothek.models import Book
from papierbibliothek.persistence.project import ProjectStore
from papierbibliothek.ui.camera import CameraDialog, largest_camera_format
from papierbibliothek.ui.main import MainDialog


ISBN = '9783150099001'


class BarcodeTests(unittest.TestCase):
    def test_ean_modules_roundtrip_and_damage_tolerance(self):
        modules = encode_ean13(ISBN)
        self.assertEqual(len(modules), 95)
        self.assertEqual(decode_modules(modules), ISBN)
        damaged = list(modules)
        damaged[0] = '1' if damaged[0] == '0' else '0'
        self.assertEqual(decode_modules(''.join(damaged)), ISBN)
        self.assertIsNone(decode_modules(encode_ean13('4006381333931')))

    def test_scaled_and_mirrored_scanlines(self):
        modules = encode_ean13(ISBN)
        row = bytes([255] * 30 + [0 if bit == '1' else 255
                                 for bit in modules for _ in range(4)] +
                    [255] * 30)
        self.assertEqual(decode_rows([row]), ISBN)
        self.assertEqual(decode_rows([row[::-1]]), ISBN)
        self.assertIsNone(decode_rows([bytes([128] * len(row))]))

    def test_perspective_scanline_with_changing_module_width(self):
        modules = encode_ean13(ISBN)
        pixels = [255] * 45
        for index, bit in enumerate(modules):
            width = 3 + int(index * 2 / (len(modules) - 1))
            pixels.extend([0 if bit == '1' else 255] * width)
        pixels.extend([255] * 45)
        self.assertEqual(decode_rows([bytes(pixels)]), ISBN)

    def test_qimage_decoder_and_no_camera_state(self):
        modules = encode_ean13(ISBN)
        scale, quiet, height = 4, 40, 260
        image = QImage(quiet * 2 + len(modules) * scale, height,
                       QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.black)
        for index, bit in enumerate(modules):
            if bit == '1':
                painter.drawRect(quiet + index * scale, 20, scale, height - 40)
        painter.end()
        self.assertEqual(decode_qimage(image), ISBN)

        rotated = image.transformed(QTransform().rotate(11),
                                    Qt.TransformationMode.SmoothTransformation)
        self.assertEqual(decode_qimage(rotated), ISBN)

        dialog = CameraDialog(devices=[], start_camera=False)
        self.addCleanup(dialog.close)
        self.assertIsNone(dialog.detected_isbn)
        self.assertFalse(dialog.camera_choice.isEnabled())
        self.assertIn('Keine Kamera', dialog.status.text())

    def test_high_transition_image_has_bounded_runtime(self):
        image = QImage(1280, 720, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.setPen(Qt.GlobalColor.black)
        for x in range(0, image.width(), 2):
            painter.drawLine(x, 0, x, image.height() - 1)
        painter.end()
        started = perf_counter()
        self.assertIsNone(decode_qimage(image))
        self.assertLess(perf_counter() - started, 2.0)

    def test_bad_camera_frame_does_not_escape_qt_callback(self):
        image = QImage(320, 200, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)

        class Frame:
            @staticmethod
            def toImage():
                return image

        dialog = CameraDialog(devices=[], start_camera=False)
        self.addCleanup(dialog.close)
        with patch('papierbibliothek.ui.camera.decode_qimage',
                   side_effect=RuntimeError('decoder failure')):
            dialog._frame_changed(Frame())
            dialog._scan_task.wait(2000)
            QApplication.instance().processEvents()
        self.assertIn('Scan läuft weiter', dialog.status.text())
        self.assertIsNone(dialog.detected_isbn)

    def test_camera_decoder_runs_outside_ui_thread_without_queueing(self):
        image = QImage(320, 200, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        entered, release = threading.Event(), threading.Event()

        class Frame:
            @staticmethod
            def toImage():
                return image

        def slow_decode(_image):
            entered.set()
            release.wait(2)
            return None

        dialog = CameraDialog(devices=[], start_camera=False)
        self.addCleanup(dialog.close)
        with patch('papierbibliothek.ui.camera.decode_qimage', side_effect=slow_decode):
            started = perf_counter()
            dialog._frame_changed(Frame())
            self.assertLess(perf_counter() - started, .2)
            self.assertTrue(entered.wait(1))
            first_task = dialog._scan_task
            dialog._last_scan = 0.0
            dialog._frame_changed(Frame())
            self.assertIs(dialog._scan_task, first_task)
            release.set()
            self.assertTrue(first_task.wait(2000))
            QApplication.instance().processEvents()

    def test_camera_keeps_candidate_across_one_missed_frame(self):
        dialog = CameraDialog(devices=[], start_camera=False)
        self.addCleanup(dialog.close)
        dialog._candidate = ISBN
        dialog._candidate_count = 1
        dialog._candidate_seen_at = 10.0
        self.assertFalse(dialog._observe_candidate(None, 10.5))
        self.assertEqual((dialog._candidate, dialog._candidate_count), (ISBN, 1))
        self.assertTrue(dialog._observe_candidate(ISBN, 10.8))

        dialog._candidate = ISBN
        dialog._candidate_count = 1
        dialog._candidate_seen_at = 10.0
        self.assertFalse(dialog._observe_candidate(None, 12.0))
        self.assertEqual((dialog._candidate, dialog._candidate_count), (None, 0))

    def test_title_page_camera_captures_without_starting_decoder(self):
        image = QImage(640, 480, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)

        class Frame:
            @staticmethod
            def toImage():
                return image

        dialog = CameraDialog(devices=[], start_camera=False, title_page=True)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.windowTitle(), 'Titelblatt fotografieren')
        dialog._frame_changed(Frame())
        self.assertTrue(dialog.ai_button.isEnabled())
        self.assertIsNone(dialog._scan_task)
        dialog._capture_for_ai()
        self.assertFalse(dialog.captured_image.isNull())
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_largest_camera_format_is_selected_by_pixel_area(self):
        class Size:
            def __init__(self, width, height):
                self._width, self._height = width, height
            def width(self):
                return self._width
            def height(self):
                return self._height

        class Format:
            def __init__(self, width, height, fps):
                self.size, self.fps = Size(width, height), fps
            def resolution(self):
                return self.size
            def maxFrameRate(self):
                return self.fps

        class Device:
            def videoFormats(self):
                return [Format(1920, 1080, 30), Format(2560, 1440, 15),
                        Format(3840, 2160, 5)]

        selected = largest_camera_format(Device())
        self.assertEqual((selected.resolution().width(), selected.resolution().height()),
                         (3840, 2160))


class CameraWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store, self.project = ProjectStore.create(
            Path(self.temp.name) / 'Projekt', 'Kameratest')

    def test_exact_isbn_can_be_applied_automatically(self):
        book = Book(isbn13=ISBN)
        self.project.books.append(book)
        self.store.save(self.project)
        record = MetadataRecord(
            provider='Test', provider_id='1', title='Die Verwandlung',
            authors=['Franz Kafka'], publisher='Reclam', publication_year=2015,
            isbn13=ISBN, language='de', source_url='https://example.org/1')

        class Provider:
            name = 'Test'

            @staticmethod
            def search(**query):
                return [record]

        result = search_book(
            self.store, self.project, book.book_id, [Provider()],
            threading.Event(), lambda message: None, auto_apply=True)
        self.assertTrue(result['auto_applied'])
        saved = result['project'].books[0]
        self.assertEqual((saved.title, saved.author),
                         ('Die Verwandlung', 'Franz Kafka'))
        self.assertEqual(saved.status, 'matched')

    def test_provider_failure_keeps_scanned_isbn_durably(self):
        book = Book(isbn13=ISBN)
        self.project.books.append(book)
        self.store.save(self.project)

        class BrokenProvider:
            name = 'Nicht erreichbar'

            @staticmethod
            def search(**query):
                raise ProviderError('Nicht erreichbar: Netzwerkfehler.')

        result = search_book(
            self.store, self.project, book.book_id, [BrokenProvider()],
            threading.Event(), lambda message: None, auto_apply=True)
        self.assertFalse(result['auto_applied'])
        self.assertTrue(result['errors'])
        self.assertEqual(result['project'].books[0].isbn13, ISBN)
        self.assertEqual(self.store.load().books[0].isbn13, ISBN)

    def test_lookup_start_failure_still_saves_camera_isbn(self):
        window = MainDialog()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        with patch.object(window, 'search_metadata_for', return_value=False) as search:
            window.accept_camera_isbn(ISBN)
        self.assertEqual(window.project.books[0].isbn13, ISBN)
        self.assertEqual(self.store.load().books[0].isbn13, ISBN)
        self.assertIn('ISBN gespeichert', window.status.text())
        providers=search.call_args.kwargs['providers']
        self.assertEqual([provider.name for provider in providers], ['lobid-resources'])

    def test_camera_scan_creates_once_and_starts_automatic_lookup(self):
        window = MainDialog()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        with patch.object(window, 'search_metadata_for') as search:
            window.accept_camera_isbn(ISBN)
            self.assertEqual(len(window.project.books), 1)
            book_id = window.project.books[0].book_id
            search.assert_called_once_with(
                book_id, auto_apply=True, camera_scan=True,
                providers=search.call_args.kwargs['providers'])
            self.assertEqual([x.name for x in search.call_args.kwargs['providers']],
                             ['lobid-resources'])
        with patch.object(window, 'search_metadata_for') as search:
            window.accept_camera_isbn(ISBN)
            self.assertEqual(len(window.project.books), 1)
            search.assert_called_once_with(
                book_id, auto_apply=True, camera_scan=True,
                providers=search.call_args.kwargs['providers'])
            self.assertEqual([x.name for x in search.call_args.kwargs['providers']],
                             ['lobid-resources'])


if __name__ == '__main__':
    unittest.main()
