from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from qt.core import QImage, QColor, QRectF, Qt, QApplication, QDialog, QDialogButtonBox
from papierbibliothek.models import Book, Project
from papierbibliothek.persistence.project import ProjectStore
from papierbibliothek.vision.schema import FIELDS, VisionError, VisionCancelled, validate_extraction, extraction_from_response, strict_json
from papierbibliothek.vision.identifier import IDENTIFIER_SCHEMA, validate_identifier
from papierbibliothek.vision.provider import OpenAIVisionProvider, DEFAULT_MODEL, NoRedirect
from papierbibliothek.vision.workflow import save_proposal, apply_review
from papierbibliothek.image_processing.crop import crop_image, jpeg_bytes
from papierbibliothek.image_processing.photos import import_batch
from papierbibliothek.ui.vision import CropDialog, ReviewDialog
from papierbibliothek.ui.main import MainDialog
from papierbibliothek.ui.widgets import BookDialog


def sample():
    fields = dict.fromkeys(FIELDS)
    fields.update(title='Über Bücher', author='José Müller', publisher='Testverlag', raw_text='José Müller\nÜber Bücher\nTestverlag')
    return {'fields': fields, 'field_confidence': {key: 0.9 if value else None for key, value in fields.items()},
            'overall': 0.85, 'readability': 'readable', 'warnings': []}


def response(extraction=None):
    return {'status': 'completed', 'output': [{'type': 'reasoning'}, {'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps(extraction or sample())}]}],
        'usage': {'input_tokens': 200, 'output_tokens': 150, 'total_tokens': 350}}


class VisionContractTests(unittest.TestCase):
    def test_identifier_schema_validation_and_openai_request(self):
        extraction={'raw_text':'ISBN 978-3-15-009900-1','isbn_candidates':['978-3-15-009900-1'],
                    'confidence':.97,'evidence':'both','warnings':[]}
        self.assertEqual(validate_identifier(extraction),extraction)
        transport=Mock(return_value=io.BytesIO(json.dumps(response(extraction)).encode()))
        result=OpenAIVisionProvider('test',transport=transport).scan_identifier(
            bytes.fromhex('ffd8')+b'image',consent=True,cancel=threading.Event())
        payload=json.loads(transport.call_args.args[0].data)
        self.assertEqual(payload['text']['format']['name'],'book_identifier')
        self.assertEqual(payload['text']['format']['schema'],IDENTIFIER_SCHEMA)
        self.assertEqual(result['extraction'],extraction)
        for bad in ({**extraction,'confidence':2},{**extraction,'evidence':'guessed'},
                    {**extraction,'isbn_candidates':['x']*11}):
            with self.assertRaises(VisionError):validate_identifier(bad)

    def test_schema_roundtrip_and_null_confidence(self):
        self.assertEqual(extraction_from_response(response()), sample())
        for mutation in ('extra', 'missing', 'invalid_type', 'range', 'unknown_confidence'):
            data = sample()
            if mutation == 'extra': data['invented'] = True
            if mutation == 'missing': del data['fields']['author']
            if mutation == 'invalid_type': data['fields']['publication_year'] = True
            if mutation == 'range': data['overall'] = 1.1
            if mutation == 'unknown_confidence': data['field_confidence']['isbn13'] = 0.99
            with self.assertRaises(VisionError, msg=mutation):
                validate_extraction(data)

    def test_duplicate_keys_nan_and_bad_json_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', 'not json'):
            with self.assertRaises(VisionError): strict_json(text)

    def test_incomplete_refusal_and_malformed_response(self):
        for data in ({'status': 'incomplete'}, {'status': 'completed', 'output': None},
                     {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]}):
            with self.assertRaises(VisionError): extraction_from_response(data)

    def test_request_contract_and_minimal_disclosure(self):
        transport = Mock(return_value=io.BytesIO(json.dumps(response()).encode()))
        result = OpenAIVisionProvider('test-secret', transport=transport).analyze(b'\xff\xd8image', consent=True, cancel=threading.Event())
        request = transport.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
        self.assertFalse(payload['store'])
        self.assertTrue(payload['text']['format']['strict'])
        self.assertFalse(payload['text']['format']['schema']['additionalProperties'])
        self.assertEqual(payload['reasoning'], {'effort': 'none'})
        self.assertNotIn('test-secret', request.data.decode())
        self.assertNotIn('test-secret', json.dumps(result))
        self.assertEqual(result['usage']['total_tokens'], 350)

    def test_consent_key_and_cancel_prevent_network(self):
        transport = Mock()
        with self.assertRaises(VisionError): OpenAIVisionProvider('')
        with self.assertRaises(VisionError): OpenAIVisionProvider('key\nsecret')
        provider = OpenAIVisionProvider('test', transport=transport)
        with self.assertRaises(VisionError): provider.analyze(b'\xff\xd8x', consent=False, cancel=threading.Event())
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(VisionCancelled): provider.analyze(b'\xff\xd8x', consent=True, cancel=cancel)
        transport.assert_not_called()

    def test_http_errors_do_not_leak_credentials_or_body(self):
        for code in (400, 401, 403, 404, 500):
            error = HTTPError('https://api.openai.com/v1/responses', code, 'test-secret', {}, io.BytesIO(b'test-secret'))
            provider = OpenAIVisionProvider('test-secret', transport=Mock(side_effect=error))
            with self.assertRaises(VisionError) as caught:
                provider.analyze(b'\xff\xd8x', consent=True, cancel=threading.Event())
            self.assertNotIn('test-secret', str(caught.exception))

    def test_network_and_unexpected_error_are_sanitized(self):
        for error in (URLError('test-secret'), TimeoutError('test-secret'), RuntimeError('test-secret')):
            provider = OpenAIVisionProvider('test-secret', transport=Mock(side_effect=error))
            with self.assertRaises(VisionError) as caught:
                provider.analyze(b'\xff\xd8x', consent=True, cancel=threading.Event())
            self.assertNotIn('test-secret', str(caught.exception))

    def test_rate_limit_one_retry_and_quota_no_retry(self):
        error = HTTPError('url', 429, 'limited', {}, io.BytesIO(b'{"error":{"code":"rate_limit_exceeded"}}'))
        transport = Mock(side_effect=[error, io.BytesIO(json.dumps(response()).encode())])
        cancel = Mock()
        cancel.is_set.return_value = cancel.wait.return_value = False
        OpenAIVisionProvider('test', transport=transport).analyze(b'\xff\xd8x', consent=True, cancel=cancel)
        self.assertEqual(transport.call_count, 2)
        error = HTTPError('url', 429, 'quota', {}, io.BytesIO(b'{"error":{"code":"insufficient_quota"}}'))
        transport = Mock(side_effect=error)
        with self.assertRaises(VisionError):
            OpenAIVisionProvider('test', transport=transport).analyze(b'\xff\xd8x', consent=True, cancel=cancel)
        self.assertEqual(transport.call_count, 1)

    def test_redirects_never_forward_key(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))

    def test_project_v1_migration_does_not_modify_source(self):
        data = Project(name='Alt', books=[Book(title='Alt')]).to_dict()
        data['schema_version'] = 1
        del data['books'][0]['vision']
        migrated = Project.from_dict(data)
        self.assertEqual(migrated.schema_version, 5)
        self.assertIsNone(migrated.books[0].vision)
        self.assertEqual(data['schema_version'], 1)
        self.assertNotIn('vision', data['books'][0])


class VisionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store, self.project = ProjectStore.create(self.root / 'Projekt', 'KI-Test')
        self.image = QImage(300, 500, QImage.Format.Format_RGB32)
        self.image.fill(QColor('red'))
        self.image.setText('GPS', 'private-location')
        source = self.root / 'spine.png'
        self.image.save(str(source))
        self.cancel = threading.Event()
        import_batch(self.store, self.project, [source], 'Regal A', self.cancel, lambda text: None)
        self.photo = self.project.photos[0]
        self.box = dict(x=10, y=20, width=100, height=400)
        self.jpeg = jpeg_bytes(crop_image(self.image, self.box))
        self.result = dict(provider='openai', model=DEFAULT_MODEL, extraction=sample(), usage={})

    def proposal(self, book_id=None):
        saved = save_proposal(self.store, self.project, self.photo, self.jpeg, self.box, self.result, self.cancel, book_id)
        self.project = saved['project']
        return self.project.books[-1]

    def test_crop_rotation_bounds_and_metadata_removed(self):
        cropped = crop_image(self.image, self.box, 90)
        self.assertEqual((cropped.width(), cropped.height()), (400, 100))
        self.assertEqual(cropped.textKeys(), [])
        self.assertNotIn(b'private-location', jpeg_bytes(cropped))
        with self.assertRaises(ValueError): crop_image(self.image, dict(x=-1, y=0, width=100, height=100))

    def test_selection_enables_explicit_paid_action(self):
        dialog = CropDialog(self.image, DEFAULT_MODEL)
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.select_whole()
        self.assertTrue(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.rotation.setCurrentIndex(1)
        self.assertTrue(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(dialog.jpeg.startswith(b'\xff\xd8'))
        dialog.close()

    def test_local_title_page_crop_has_no_upload_action(self):
        dialog = CropDialog(self.image, '', local_title_page=True)
        self.assertEqual(dialog.windowTitle(), 'Titelblatt zuschneiden')
        self.assertIn('keine KI- oder Netzwerkübertragung', dialog.disclosure.text())
        dialog.select_whole()
        dialog.rotate_right.click()
        self.assertEqual(dialog.rotation.currentData(), 90)

        full_resolution = QImage(3000, 2000, QImage.Format.Format_RGB32)
        full_resolution.fill(QColor('blue'))
        local = CropDialog(full_resolution, '', local_title_page=True)
        local.select_whole()
        local.accept()
        saved = QImage.fromData(local.jpeg, 'JPEG')
        self.assertEqual((saved.width(), saved.height()), (3000, 2000))
        dialog.rotate_left.click()
        self.assertEqual(dialog.rotation.currentData(), 0)
        button = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertEqual(button.text(), 'Zuschneiden und speichern')
        dialog.accept()
        self.assertTrue(dialog.jpeg.startswith(b'\xff\xd8'))
        dialog.close()

    def test_title_page_ai_keeps_spine_links_separate(self):
        book = Book(title='Mit Titelblatt', photo_id=self.photo.photo_id,
                    image_path=self.photo.image_path, crop_path='crops/spine.jpg',
                    bounding_box=self.box, title_page_path='title_pages/page.jpg')
        self.project.books.append(book)
        self.store.save(self.project)
        saved = save_proposal(
            self.store, self.project, None, self.jpeg,
            dict(x=0, y=0, width=100, height=400), self.result,
            self.cancel, book.book_id, title_page=True)['project'].books[0]
        self.assertEqual(saved.photo_id, self.photo.photo_id)
        self.assertEqual(saved.crop_path, 'crops/spine.jpg')
        self.assertEqual(saved.bounding_box, self.box)
        self.assertNotEqual(saved.vision_image_path, saved.crop_path)
        self.assertTrue(self.store.asset(saved.vision_image_path).is_file())

    def test_proposal_is_durable_without_overwriting_metadata(self):
        original = Book(title='Mein korrigierter Titel', photo_id=self.photo.photo_id, status='manual_confirmed')
        self.project.books.append(original)
        self.store.save(self.project)
        book = self.proposal(original.book_id)
        self.assertEqual(book.title, original.title)
        self.assertEqual(book.status, 'needs_manual_review')
        self.assertEqual(len(self.project.books), 1)
        loaded = ProjectStore(self.store.root).load().books[0]
        self.assertEqual(loaded.vision['extraction']['fields']['title'], 'Über Bücher')
        self.assertTrue(self.store.asset(loaded.crop_path).exists())

    def test_low_readability_and_bad_isbn_are_flagged(self):
        self.result['extraction']['readability'] = 'multiple_books'
        self.result['extraction']['fields']['isbn13'] = '9780306406158'
        self.result['extraction']['field_confidence']['isbn13'] = 0.5
        book = self.proposal()
        self.assertEqual(book.status, 'needs_scan')
        self.assertTrue(book.vision['warnings'])
        self.assertIsNone(book.isbn13)

    def test_review_only_applies_selected_fields_and_keeps_evidence(self):
        book = self.proposal()
        reviewed = apply_review(book, {'title': 'Von mir korrigiert', 'author': 'José Müller'})
        self.assertEqual(reviewed.status, 'manual_confirmed')
        self.assertIsNone(reviewed.publisher)
        self.assertEqual(reviewed.confidence['author'], 0.9)
        self.assertIsNone(reviewed.confidence['title'])
        self.assertEqual(reviewed.vision['extraction']['fields']['title'], 'Über Bücher')
        self.assertIsNone(book.title)

    def test_cancelled_result_is_not_persisted(self):
        self.cancel.set()
        with self.assertRaises(VisionCancelled): self.proposal()
        self.assertEqual(len(ProjectStore(self.store.root).load().books), 0)

    def test_manual_correction_invalidates_old_confidence(self):
        book = apply_review(self.proposal(), {'title': 'Über Bücher', 'author': 'José Müller'})
        editor = BookDialog(self.project, book=book)
        editor.fields['title'].setText('Neuer Titel')
        editor.accept()
        self.assertIsNone(editor.book.confidence['title'])
        self.assertEqual(editor.book.vision['extraction']['fields']['title'], 'Über Bücher')
        editor.close()

    def test_session_key_and_pending_provider_released_on_close(self):
        window = MainDialog()
        window.session_key = 'test-session-secret'
        window.pending_result = {'provider': OpenAIVisionProvider('test-session-secret')}
        window.close()
        self.assertEqual(window.session_key, '')
        self.assertIsNone(window.pending_result)

    def test_review_dialog_preserves_conflicts_and_allows_correction(self):
        book = self.proposal()
        book.title = 'Bestehender Titel'
        dialog = ReviewDialog(book, self.store, photo=self.photo)
        self.assertEqual(dialog.table.item(0, 0).checkState(), Qt.CheckState.Unchecked)
        dialog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        dialog.table.item(0, 3).setText('Korrigierter Titel')
        dialog.accept()
        self.assertEqual(dialog.book.title, 'Korrigierter Titel')
        self.assertEqual(book.title, 'Bestehender Titel')
        dialog.close()

    def test_review_dialog_saves_incomplete_selection_as_draft(self):
        book = self.proposal()
        dialog = ReviewDialog(book, self.store, photo=self.photo)
        for row in range(dialog.table.rowCount()):
            dialog.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        dialog.save_draft()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.book.status, 'needs_manual_review')
        self.assertIsNone(dialog.book.title)
        self.assertIsNotNone(dialog.book.vision['reviewed_at'])
        dialog.close()

    def test_review_dialog_confirm_is_leftmost_default_action(self):
        dialog = ReviewDialog(self.proposal(), self.store, photo=self.photo)
        self.assertEqual([button.text() for button in dialog.action_buttons],
                         ['Speichern und bestätigen', 'Als Entwurf speichern',
                          'Nachscan nötig', 'Später prüfen'])
        self.assertTrue(dialog.confirm_button.isDefault())
        self.assertTrue(all(not button.autoDefault() for button in dialog.action_buttons[1:]))
        dialog.close()

    def test_background_gui_analysis_can_be_reviewed_later(self):
        window = MainDialog()
        window.show()
        self.addCleanup(window.close)
        self.assertTrue(window.load_project(self.store.path))
        fake = Mock()
        fake.model = DEFAULT_MODEL
        fake.analyze.return_value = self.result
        with patch.object(window,'selected_provider',return_value=(fake,'OpenAI')), \
             patch('papierbibliothek.ui.main.CropDialog') as crop, \
             patch('papierbibliothek.ui.main.ReviewDialog') as review:
            crop.return_value.exec.return_value = QDialog.DialogCode.Accepted
            crop.return_value.jpeg, crop.return_value.box = self.jpeg, self.box
            review.return_value.exec.return_value = QDialog.DialogCode.Rejected
            window.analyze_new()
            deadline = time.monotonic() + 10
            while window.task is not None and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.01)
            self.assertIsNone(window.task)
            self.assertIsNone(window.pending_error)
            self.assertEqual(len(window.project.books), 1)
            self.assertEqual(window.project.books[0].status, 'needs_manual_review')
            fake.analyze.assert_called_once()
            self.assertTrue(fake.analyze.call_args.kwargs['consent'])
        window.close()
        self.assertIsNotNone(ProjectStore(self.store.root).load().books[0].vision)
