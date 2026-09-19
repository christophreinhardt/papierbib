import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from qt.core import QAbstractItemView, QMessageBox, Qt

from papierbibliothek.models import Book, Project
from papierbibliothek.image_processing.photos import import_batch
from papierbibliothek.persistence.photos import remove_photos
from papierbibliothek.persistence.project import ProjectStore
from papierbibliothek.ui.main import MainDialog
import json


class PhotoDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store, self.project = ProjectStore.create(self.root / 'Project', 'Fotos')
        self.original = self.root / 'original.jpg'
        Image.new('RGB', (80, 120), 'white').save(self.original)
        import_batch(self.store, self.project, [self.original], '',
                     threading.Event(), lambda message: None)
        self.photo = self.project.photos[0]
        self.book = Book(title='Erhalten', photo_id=self.photo.photo_id,
                         image_path=self.photo.image_path,
                         crop_path='crops/evidence.jpg',
                         vision_image_path='crops/evidence.jpg',
                         bounding_box={'x': 0, 'y': 0, 'width': 10, 'height': 20},
                         calibre_book_id=12, status='imported')
        self.project.books.append(self.book)
        self.store.asset('crops').mkdir()
        self.store.asset(self.book.crop_path).write_bytes(self.original.read_bytes())
        self.store.save(self.project)

    def test_removal_keeps_books_and_evidence_and_archives_only_project_copies(self):
        before = self.original.read_bytes()
        result, recycle, warnings = remove_photos(
            self.store, self.project, [self.photo.photo_id])
        self.assertEqual(warnings, [])
        self.assertEqual(result.photos, [])
        book = result.books[0]
        self.assertEqual((book.title, book.calibre_book_id, book.status),
                         ('Erhalten', 12, 'imported'))
        self.assertIsNone(book.photo_id)
        self.assertIsNone(book.image_path)
        self.assertIsNone(book.bounding_box)
        self.assertEqual(self.original.read_bytes(), before)
        self.assertTrue(self.store.asset(book.crop_path).is_file())
        self.assertTrue(self.store.asset(book.vision_image_path).is_file())
        for path in (self.photo.image_path, self.photo.preview_path):
            self.assertFalse(self.store.asset(path).exists())
            self.assertTrue(self.store.asset(recycle + '/' + path).is_file())
        old = Project.from_dict(json.loads(
            self.store.asset(recycle + '/projekt.json').read_text(encoding='utf-8')))
        self.assertEqual(old.photos[0].photo_id, self.photo.photo_id)
        self.assertEqual(self.project.books[0].photo_id, self.photo.photo_id)
        self.assertEqual(ProjectStore(self.store.root).load().photos, [])

    def test_title_page_is_not_readded_on_reopen_and_shared_evidence_survives(self):
        self.book.title_page_photo_id = self.photo.photo_id
        self.book.title_page_path = self.photo.image_path
        self.book.vision_image_path = self.photo.image_path
        self.store.save(self.project)
        result, _, _ = remove_photos(self.store, self.project, [self.photo.photo_id])
        self.assertIsNone(result.books[0].title_page_path)
        self.assertIsNone(result.books[0].title_page_photo_id)
        self.assertTrue(self.store.asset(self.photo.image_path).is_file())
        self.assertEqual(ProjectStore(self.store.root).load().photos, [])

    def test_failed_save_does_not_move_photos_or_modify_project(self):
        original = self.store.path.read_bytes()
        with patch.object(self.store, 'save', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                remove_photos(self.store, self.project, [self.photo.photo_id])
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertEqual(len(self.project.photos), 1)
        self.assertTrue(self.store.asset(self.photo.image_path).is_file())
        self.assertTrue(self.store.asset(self.photo.preview_path).is_file())

    def test_move_failure_reports_retained_files_after_manifest_save(self):
        import os
        replace = os.replace

        def fail_image_move(source, target):
            if Path(source).suffix.lower() == '.jpg':
                raise PermissionError('locked')
            return replace(source, target)

        with patch('papierbibliothek.persistence.photos.os.replace', side_effect=fail_image_move):
            result, _, warnings = remove_photos(self.store, self.project, [self.photo.photo_id])
        self.assertEqual(result.photos, [])
        self.assertIn(self.photo.image_path, warnings)
        self.assertTrue(self.store.asset(self.photo.image_path).is_file())
        self.assertEqual(ProjectStore(self.store.root).load().photos, [])

    def test_unknown_selection_does_not_save(self):
        with self.assertRaises(ValueError):
            remove_photos(self.store, self.project, ['missing'])
        self.assertEqual(len(ProjectStore(self.store.root).load().photos), 1)

    def test_ui_cancel_then_multi_delete_preserves_books_and_resets_filter(self):
        second = self.root / 'second.jpg'
        Image.new('RGB', (80, 120), 'red').save(second)
        import_batch(self.store, self.project, [second], '',
                     threading.Event(), lambda message: None)
        window = MainDialog()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        self.assertEqual(window.photos.selectionMode(),
                         QAbstractItemView.SelectionMode.ExtendedSelection)
        window.photos.selectAll()
        self.assertTrue(window.delete_photos_button.isEnabled())
        with patch('papierbibliothek.ui.main.QMessageBox.question',
                   return_value=QMessageBox.StandardButton.No):
            window.delete_photos()
        self.assertEqual(window.photos.count(), 2)
        window.photo_filter.setCurrentIndex(1)
        with patch('papierbibliothek.ui.main.QMessageBox.question',
                   return_value=QMessageBox.StandardButton.Yes):
            window.delete_photos()
        self.assertEqual(window.photos.count(), 0)
        self.assertEqual(window.table.rowCount(), 1)
        self.assertEqual(window.photo_filter.currentIndex(), 0)
        self.assertFalse(window.delete_photos_button.isEnabled())
        self.assertIn('2 Foto(s) gelöscht', window.status.text())
        self.assertEqual(ProjectStore(self.store.root).load().photos, [])

    def test_ui_shows_version_help_and_changes_selected_photo_locations(self):
        second = self.root / 'second.jpg'
        Image.new('RGB', (80, 120), 'red').save(second)
        import_batch(self.store, self.project, [second], '',
                     threading.Event(), lambda message: None)
        window = MainDialog()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        self.assertIn('Version 0.6.10', window.windowTitle())
        window.photos.selectAll()
        with patch('papierbibliothek.ui.main.QInputDialog.getText',
                   return_value=('Arbeitszimmer · Regal B · Fach 4', True)):
            window.photo_location()
        self.assertEqual({photo.location for photo in window.project.photos},
                         {'Arbeitszimmer · Regal B · Fach 4'})
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Ok):
            window.show_help()
        # The help dialog is intentionally tested through its visible title.
        self.assertIn('Hilfe', window.help_button.text())
