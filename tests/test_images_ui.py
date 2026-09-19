from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image
from qt.core import QApplication, QDialog, QImage, Qt, QAbstractItemView, QItemSelectionModel, QMessageBox

from papierbibliothek.models import Book
from papierbibliothek.persistence.project import ProjectStore
from papierbibliothek.image_processing.photos import import_batch, read_image
from papierbibliothek.image_processing.crop import jpeg_bytes
from papierbibliothek.import_export.export import export_project
from papierbibliothek.ui.main import MainDialog
from papierbibliothek.ui.widgets import BookDialog


class ImageUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store, self.project = ProjectStore.create(self.root / 'Projekt', 'Testbibliothek')
        self.input = self.root / 'Quelle'
        self.input.mkdir()
        self.image = self.input / 'Regal.jpg'
        Image.new('RGB', (360, 180), '#246578').save(self.image)
        self.cancel = threading.Event()

    def run_import(self, paths=None, progress=lambda message: None):
        return import_batch(self.store, self.project, paths or [self.image], 'Regal A / Fach 2', self.cancel, progress)

    def test_title_page_camera_crop_is_assigned_to_selected_book(self):
        book = Book(title='Kamerabuch')
        self.project.books.append(book)
        self.store.save(self.project)
        window = MainDialog()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        self.assertTrue(window.select_book_id(book.book_id))
        image = QImage(640, 480, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        cropped_jpeg = jpeg_bytes(image)
        with patch('papierbibliothek.ui.main.CameraDialog') as camera, \
                patch('papierbibliothek.ui.main.CropDialog') as crop:
            camera.return_value.exec.return_value = QDialog.DialogCode.Accepted
            camera.return_value.captured_image = image
            crop.return_value.exec.return_value = QDialog.DialogCode.Accepted
            crop.return_value.jpeg = cropped_jpeg
            window.capture_title_page()
        loaded = ProjectStore(self.store.root).load()
        saved = loaded.books[0]
        self.assertTrue(saved.title_page_path.startswith('title_pages/'))
        self.assertIsNotNone(saved.title_page_photo_id)
        self.assertEqual(len(loaded.photos), 1)
        self.assertEqual(loaded.photos[0].photo_id, saved.title_page_photo_id)
        self.assertEqual(window.photos.count(), 1)
        self.assertEqual(self.store.asset(saved.title_page_path).read_bytes(),
                         cropped_jpeg)
        crop.assert_called_once()
        self.assertTrue(crop.call_args.kwargs['local_title_page'])
        self.assertIn('lokal im Projekt gespeichert', window.status.text())

        class Provider:
            model = 'vision-test'

        with patch.object(window, 'selected_provider',
                          return_value=(Provider(), 'Testanbieter')), \
                patch.object(window, 'run_task') as run_task:
            window.analyze_title_page()
        run_task.assert_called_once()
        task = run_task.call_args.args[0]
        payload = task(threading.Event(), lambda message: None)
        self.assertEqual(payload['book_id'], book.book_id)
        self.assertTrue(payload['title_page_analysis'])
        self.assertFalse(payload['crop_source'].isNull())
        self.assertIsNone(payload['photo'])
        self.assertEqual(window.title_page_ai_button.text(),
                         'Titelblatt mit KI auswerten')

    def test_import_keeps_original_bytes_and_small_preview_size(self):
        original = self.image.read_bytes()
        self.assertEqual(self.run_import()['imported'], 1)
        photo = self.project.photos[0]
        self.assertEqual(self.store.asset(photo.image_path).read_bytes(), original)
        self.assertEqual(self.image.read_bytes(), original)
        preview = QImage(str(self.store.asset(photo.preview_path)))
        self.assertEqual((preview.width(), preview.height()), (360, 180))
        self.assertEqual(len(ProjectStore(self.store.root).load().photos), 1)

    def test_exif_orientation_is_applied(self):
        exif = Image.Exif()
        exif[274] = 6
        Image.new('RGB', (360, 180), '#246578').save(self.image, exif=exif)
        self.run_import()
        preview = QImage(str(self.store.asset(self.project.photos[0].preview_path)))
        self.assertEqual((preview.width(), preview.height()), (180, 360))

    def test_large_image_is_downscaled(self):
        Image.new('RGB', (3000, 1000), '#aaaaaa').save(self.image)
        image, size = read_image(self.image)
        self.assertEqual((image.width(), image.height()), (2400, 800))
        self.assertEqual(size.width(), 3000)

    def test_directory_import_and_content_duplicates(self):
        sub = self.input / 'Unterordner'
        sub.mkdir()
        shutil.copy2(self.image, sub / 'anderer-name.jpg')
        result = self.run_import([self.input])
        self.assertEqual((result['imported'], result['duplicates']), (1, 1))
        self.assertEqual(self.run_import()['duplicates'], 1)

    def test_broken_image_does_not_abort_other_files(self):
        bad = self.input / 'kaputt.png'
        bad.write_bytes(b'not an image')
        result = self.run_import([bad, self.image])
        self.assertEqual((result['imported'], len(result['errors'])), (1, 1))
        self.assertFalse(list((self.store.root / 'photos').glob('.import-*')))

    def test_cancel_preserves_completed_imports(self):
        second = self.input / 'zweites.png'
        Image.new('RGB', (150, 200), 'red').save(second)
        result = self.run_import([self.image, second], lambda message: self.cancel.set())
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['imported'], 1)
        self.assertEqual(len(ProjectStore(self.store.root).load().photos), 1)

    def test_cancel_before_start_does_not_copy(self):
        self.cancel.set()
        self.assertEqual(self.run_import()['imported'], 0)
        self.assertEqual(list((self.store.root / 'photos').iterdir()), [])

    def test_project_move_preserves_photo_links(self):
        self.run_import()
        moved = self.root / 'Umgezogen'
        shutil.copytree(self.store.root, moved)
        store = ProjectStore(moved)
        project = store.load()
        self.assertTrue(store.asset(project.photos[0].image_path).is_file())

    def test_book_editor_manual_entry_and_isbn_conversion(self):
        self.run_import()
        editor = BookDialog(self.project, photo_id=self.project.photos[0].photo_id)
        editor.fields['title'].setText('Über das Lesen')
        editor.fields['author'].setText('José Müller')
        editor.fields['isbn10'].setText('0-306-40615-2')
        editor.status.setCurrentIndex(editor.status.findData('manual_confirmed'))
        editor.accept()
        self.assertEqual(editor.book.isbn13, '9780306406157')
        self.assertEqual(editor.book.location, 'Regal A / Fach 2')
        self.assertEqual(editor.book.image_path, self.project.photos[0].image_path)

    def test_manual_empty_draft_and_duplicate_isbn_guard(self):
        empty = BookDialog(self.project)
        self.assertEqual(empty.windowTitle(), 'Buchdatensatz manuell anlegen')
        empty.accept()
        self.assertEqual(empty.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(empty.book.status, 'needs_manual_review')

        self.project.books.append(Book(isbn13='9780306406157'))
        duplicate = BookDialog(self.project)
        duplicate.fields['isbn13'].setText('978-0-306-40615-7')
        with patch('papierbibliothek.ui.widgets.QMessageBox.warning') as warning:
            duplicate.accept()
            warning.assert_called_once()
        self.assertNotEqual(duplicate.result(), QDialog.DialogCode.Accepted)

    def test_editor_cancel_and_invalid_input_do_not_mutate_book(self):
        book = Book(title='Original')
        editor = BookDialog(self.project, book=book)
        editor.fields['title'].setText('Geändert')
        editor.fields['isbn13'].setText('bad')
        with patch('papierbibliothek.ui.widgets.QMessageBox.warning') as warning:
            editor.accept()
            warning.assert_called_once()
        editor.reject()
        self.assertEqual(book.title, 'Original')

    def test_project_lock_released_on_close(self):
        window = MainDialog()
        self.assertTrue(window.load_project(self.store.path))
        other = MainDialog()
        with patch.object(other, 'error') as error:
            self.assertFalse(other.load_project(self.store.path))
            error.assert_called_once()
        window.close()
        self.assertTrue(other.load_project(self.store.path))
        other.close()

    def test_gui_workflow_background_import_edit_filter_export_reopen(self):
        window = MainDialog()
        self.assertTrue(window.load_project(self.store.path))
        window.show()
        window.run_task(lambda cancel, progress: import_batch(window.store, window.project,
                        [self.image], 'Regal A', cancel, progress), 'Testimport')
        deadline = time.monotonic() + 15
        while window.task is not None and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)
        self.assertIsNone(window.task)
        self.assertIsNone(window.pending_error)
        self.assertEqual(window.photos.count(), 1)
        book = Book(title='Faust', author='Goethe', status='manual_confirmed',
                    photo_id=window.project.photos[0].photo_id,
                    image_path=window.project.photos[0].image_path)
        with patch('papierbibliothek.ui.main.BookDialog') as editor:
            editor.return_value.exec.side_effect = [1]
            editor.return_value.book = book
            window.add_book()
        self.assertEqual(window.table.rowCount(), 1)
        self.assertEqual(window.current_book().book_id, book.book_id)
        self.assertIn('Manueller Buchdatensatz gespeichert', window.status.text())
        window.search.setText('nicht vorhanden')
        self.assertEqual(window.table.rowCount(), 0)
        window.search.clear()
        window.status_filter.setCurrentIndex(window.status_filter.findData('needs_scan'))
        self.assertEqual(window.table.rowCount(), 0)
        window.status_filter.setCurrentIndex(0)
        window.table.selectRow(0)
        self.assertEqual(window.current_book().title, 'Faust')
        csv = self.root / 'export.csv'
        export_project(window.project, csv, 'csv', window.store.root)
        self.assertIn('Faust', csv.read_text(encoding='utf-8-sig'))
        window.close()
        self.assertTrue(window.load_project(self.store.path))
        self.assertEqual(window.table.rowCount(), 1)
        window.close()

    def test_gui_handles_hundreds_of_books_and_sorts_identity(self):
        self.project.books = [Book(title=f'Buch {i:04}', author='Müller') for i in range(600)]
        self.store.save(self.project)
        window = MainDialog()
        self.assertTrue(window.load_project(self.store.path))
        self.assertEqual(window.table.rowCount(), 600)
        window.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        window.table.selectRow(0)
        self.assertEqual(window.current_book().title, 'Buch 0599')
        window.search.setText('Buch 0042')
        self.assertEqual(window.table.rowCount(), 1)
        window.close()

    def test_last_project_auto_opens_only_when_requested(self):
        prefs = {'review_threshold': 0.8, 'last_project': str(self.store.path)}
        with patch('papierbibliothek.ui.main.settings', return_value=prefs):
            window = MainDialog(auto_open=True)
            QApplication.processEvents()
            self.assertIsNotNone(window.project)
            self.assertEqual(window.store.path, self.store.path)
            window.close()

    def test_multiple_selection_and_batch_delete(self):
        self.project.books = [Book(title='Eins'), Book(title='Zwei'), Book(title='Drei')]
        self.store.save(self.project)
        window = MainDialog()
        self.assertTrue(window.load_project(self.store.path))
        self.assertEqual(window.table.selectionMode(), QAbstractItemView.SelectionMode.ExtendedSelection)
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        window.table.selectionModel().select(window.table.model().index(0, 0), flags)
        window.table.selectionModel().select(window.table.model().index(1, 0), flags)
        self.assertEqual(len(window.selected_books()), 2)
        with patch('papierbibliothek.ui.main.QMessageBox.question',
                   return_value=QMessageBox.StandardButton.Yes):
            window.delete_book()
        self.assertEqual([book.title for book in window.project.books], ['Drei'])
        window.close()

    def test_double_click_routes_empty_book_to_ai_and_filled_book_to_editor(self):
        self.project.books = [Book(), Book(title='Vorhanden')]
        empty_id = self.project.books[0].book_id
        filled_id = self.project.books[1].book_id
        self.store.save(self.project)
        window = MainDialog()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        rows = {window.table.item(row, 0).data(Qt.ItemDataRole.UserRole): row
                for row in range(window.table.rowCount())}
        window.table.setCurrentCell(rows[empty_id], 0)
        with patch.object(window, 'prepare_analysis') as analyze, patch.object(window, 'edit_book') as edit:
            window.activate_book()
            analyze.assert_called_once_with(next(book for book in window.project.books if book.book_id == empty_id))
            edit.assert_not_called()
        window.table.setCurrentCell(rows[filled_id], 0)
        with patch.object(window, 'prepare_analysis') as analyze, patch.object(window, 'edit_book') as edit:
            window.activate_book()
            edit.assert_called_once_with()
            analyze.assert_not_called()
        window.close()
