from copy import deepcopy
import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from qt.core import QImage, Qt

from papierbibliothek.models import Book, Project
from papierbibliothek.isbn import valid, normalize, to_isbn13
from papierbibliothek.persistence.project import ProjectStore, atomic_write
from papierbibliothek.persistence.title_page import save_title_page
from papierbibliothek.import_export.export import export_project
from papierbibliothek.image_processing.crop import jpeg_bytes


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store, self.project = ProjectStore.create(self.root / 'Sammlung', 'Bücher & Hörbücher')

    def test_isbn_known_checksums_and_conversion(self):
        self.assertTrue(valid('0-306-40615-2'))
        self.assertTrue(valid('080442957X'))
        self.assertEqual(to_isbn13('0-306-40615-2'), '9780306406157')
        self.assertEqual(normalize(' 978-0-306-40615-7 '), '9780306406157')
        for value in ('9780306406158', '1234567890128', '0306406153', 'X123456789', ''):
            self.assertFalse(valid(value), value)

    def test_confidence_is_unknown_for_manual_data(self):
        book = Book(title='Faust', status='manual_confirmed')
        book.validate()
        self.assertTrue(all(value is None for value in book.confidence.values()))
        book.confidence['overall'] = float('nan')
        with self.assertRaises(ValueError):
            book.validate()

    def test_invalid_year_isbn_and_contradictory_pair(self):
        for book in (Book(publication_year=0), Book(publication_year=True), Book(isbn13='9780306406158'),
                     Book(isbn10='080442957X', isbn13='9780306406157')):
            with self.assertRaises(ValueError):
                book.validate()

    def test_confirmed_book_requires_title(self):
        with self.assertRaises(ValueError):
            Book(status='manual_confirmed').validate()
        Book(status='needs_scan').validate()

    def test_roundtrip_preserves_unicode_nulls_and_identity(self):
        self.project.books.append(Book(title='Über Bücher', author='José & Müller', notes='Zeile 1\nZeile 2'))
        self.store.save(self.project)
        reopened = ProjectStore(self.store.root).load()
        self.assertEqual(reopened.to_dict(), self.project.to_dict())
        self.assertIsNone(reopened.books[0].publisher)

    def test_title_page_is_saved_locally_and_survives_reload(self):
        book = Book(title='Kamerabuch')
        self.project.books.append(book)
        self.store.save(self.project)
        image = QImage(40, 60, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        jpeg = jpeg_bytes(image)
        saved = save_title_page(
            self.store, self.project, book.book_id, jpeg)
        path = self.store.asset(saved.books[0].title_page_path)
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_bytes(), jpeg)
        reopened = ProjectStore(self.store.root).load()
        self.assertEqual(reopened.books[0].title_page_path,
                         saved.books[0].title_page_path)
        self.assertTrue(saved.books[0].title_page_path.startswith('title_pages/'))
        self.assertEqual(len(saved.photos), 1)
        self.assertEqual(saved.books[0].title_page_photo_id,
                         saved.photos[0].photo_id)
        self.assertEqual(saved.photos[0].image_path,
                         saved.books[0].title_page_path)

    def test_schema4_title_page_becomes_a_regular_photo_on_load(self):
        image = QImage(40, 60, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        relative = 'title_pages/legacy.jpg'
        self.store.asset(relative).write_bytes(jpeg_bytes(image))
        self.project.books.append(Book(title='Altbestand',
                                       title_page_path=relative))
        data = self.project.to_dict()
        data['schema_version'] = 4
        data['books'][0].pop('title_page_photo_id')
        data['books'][0].pop('vision_image_path')
        atomic_write(self.store.path,
                     (json.dumps(data, ensure_ascii=False) + '\n').encode('utf-8'))
        migrated = ProjectStore(self.store.root).load()
        self.assertEqual(len(migrated.photos), 1)
        self.assertEqual(migrated.books[0].title_page_photo_id,
                         migrated.photos[0].photo_id)
        self.assertEqual(migrated.photos[0].image_path, relative)

    def test_existing_directory_is_never_reused(self):
        with self.assertRaises(FileExistsError):
            ProjectStore.create(self.store.root, 'Andere Sammlung')

    def test_failed_atomic_replace_preserves_original(self):
        before = self.store.path.read_bytes()
        with patch('papierbibliothek.persistence.project.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                atomic_write(self.store.path, b'new')
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertFalse(list(self.store.root.glob('.projekt.json-*')))

    def test_backup_and_external_edit_detection(self):
        before = self.store.path.read_bytes()
        second = ProjectStore(self.store.root)
        second_project = second.load()
        self.project.books.append(Book(title='Neu'))
        self.store.save(self.project)
        self.assertEqual((self.store.root / 'projekt.backup.json').read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'außerhalb'):
            second.save(second_project)

    def test_schema_and_relationship_validation(self):
        data = self.project.to_dict()
        data['schema_version'] = 99
        with self.assertRaises(ValueError):
            Project.from_dict(data)
        self.project.books = [Book(photo_id='missing')]
        with self.assertRaises(ValueError):
            self.project.validate()
        book = Book()
        self.project.books = [book, deepcopy(book)]
        with self.assertRaises(ValueError):
            self.project.validate()

    def test_paths_cannot_escape_project(self):
        for value in ('../secret.jpg', '/tmp/file', 'C:/file', 'photos/../../file', 'photos\\file'):
            with self.assertRaises(ValueError):
                self.store.asset(value)

    def test_csv_quotes_unicode_isbn_and_formula_protection(self):
        self.project.books.append(Book(title='=HYPERLINK("bad")', author='Müller; José',
                                       isbn10='0306406152', notes='Erste Zeile\n"Zweite"'))
        path = self.root / 'books.csv'
        export_project(self.project, path, 'csv', self.store.root)
        self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter=';'))
        self.assertEqual(rows[0]['isbn10'], '0306406152')
        self.assertEqual(rows[0]['author'], 'Müller; José')
        self.assertEqual(rows[0]['notes'], 'Erste Zeile\n"Zweite"')
        self.assertTrue(rows[0]['title'].startswith("'="))

    def test_json_export_is_lossless_and_can_reopen(self):
        self.project.books.append(Book(title='=Titel', publisher=None))
        path = self.root / 'export.json'
        export_project(self.project, path, 'json', self.store.root)
        self.assertEqual(Project.from_dict(json.loads(path.read_text(encoding='utf-8'))).to_dict(), self.project.to_dict())
        moved = self.root / 'Restored'
        moved.mkdir()
        shutil.copy2(path, moved / 'projekt.json')
        self.assertEqual(ProjectStore(moved).load().books[0].title, '=Titel')

    def test_export_must_not_overwrite_project_assets(self):
        for path in (self.store.path, self.store.root / 'projekt.backup.json', self.store.root / 'photos' / 'a.jpg'):
            with self.assertRaises(ValueError):
                export_project(self.project, path, 'json', self.store.root)
