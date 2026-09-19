from copy import deepcopy
import io
import json
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from qt.core import QApplication, QDialog, QImage, QColor, QDialogButtonBox
from papierbibliothek.vision.gemini import GeminiVisionProvider, DEFAULT_GEMINI_MODEL, GEMINI_ENDPOINT, parse_response, request_schema
from papierbibliothek.vision.shelf import SHELF_SCHEMA
from papierbibliothek.vision.schema import VisionError, VisionCancelled
from papierbibliothek.ui.vision import SettingsDialog, CropDialog
from papierbibliothek.ui.main import MainDialog
import test_vision
from test_vision import sample
from test_shelf import shelf


def interaction(extraction=None):
    return {'candidates': [{'finishReason':'STOP','content':{'parts':[
            {'thought':True,'text':'ignored reasoning'}, {'text':json.dumps(extraction if extraction is not None else sample())}]}}],
            'usageMetadata': {'promptTokenCount': 321,'candidatesTokenCount': 123,'totalTokenCount': 444}}


def prefs():
    return dict(provider='openai', model='gpt-5.6-luna', gemini_model=DEFAULT_GEMINI_MODEL,
                review_threshold=.8, metadata_threshold=.88, metadata_offline=False,
                use_lobid=True, use_openlibrary=True, use_googlebooks=False,
                use_dnb=True, custom_url='')


class GeminiContractTests(unittest.TestCase):
    def test_identifier_uses_strict_schema(self):
        extraction={'raw_text':'9783150099001','isbn_candidates':['9783150099001'],
                    'confidence':.9,'evidence':'barcode','warnings':[]}
        transport=Mock(return_value=io.BytesIO(json.dumps(interaction(extraction)).encode()))
        result=GeminiVisionProvider('test',transport=transport).scan_identifier(
            bytes.fromhex('ffd8')+b'image',consent=True,cancel=threading.Event())
        payload=json.loads(transport.call_args.args[0].data)
        schema=payload['generationConfig']['responseJsonSchema']
        self.assertIn('isbn_candidates',schema['properties'])
        self.assertNotIn('maxItems',schema['properties']['isbn_candidates'])
        self.assertEqual(result['extraction'],extraction)

    def test_schema_projection_keeps_strict_structure_without_mutation(self):
        original = deepcopy(SHELF_SCHEMA)
        wire = request_schema(SHELF_SCHEMA)
        self.assertEqual(SHELF_SCHEMA,original)
        self.assertNotIn('maxItems',wire['properties']['regions'])
        self.assertFalse(wire['additionalProperties'])
        region = wire['properties']['regions']['items']
        self.assertFalse(region['additionalProperties'])
        self.assertEqual(region['required'],original['properties']['regions']['items']['required'])
        self.assertEqual(region['properties']['box']['properties']['x']['type'],'integer')
        self.assertNotIn('maximum',region['properties']['box']['properties']['x'])

    def test_projected_schema_still_enforces_limits_on_response(self):
        for mutation in ('too_many', 'outside', 'confidence'):
            extraction = shelf()
            if mutation == 'too_many': extraction['regions'] *= 31
            if mutation == 'outside': extraction['regions'][0]['box']['x'] = 999
            if mutation == 'confidence': extraction['regions'][0]['confidence'] = 1.1
            transport = Mock(return_value=io.BytesIO(json.dumps(interaction(extraction)).encode()))
            provider = GeminiVisionProvider('test',transport=transport)
            with self.assertRaises(VisionError):
                provider.detect_shelf(b'\xff\xd8x',consent=True,cancel=threading.Event())

    def test_image_schema_request_and_safe_auth(self):
        transport = Mock(return_value=io.BytesIO(json.dumps(interaction()).encode()))
        result = GeminiVisionProvider('gemini-test-secret',transport=transport).analyze(b'\xff\xd8image',consent=True,cancel=threading.Event())
        request = transport.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url,GEMINI_ENDPOINT+DEFAULT_GEMINI_MODEL+':generateContent')
        self.assertNotIn('?',request.full_url)
        self.assertEqual(request.get_header('X-goog-api-key'),'gemini-test-secret')
        self.assertIsNone(request.get_header('Authorization'))
        self.assertNotIn('cachedContent',payload)
        self.assertEqual(payload['contents'][0]['parts'][1]['inlineData']['mimeType'],'image/jpeg')
        self.assertEqual(payload['generationConfig']['responseMimeType'],'application/json')
        self.assertFalse(payload['generationConfig']['responseJsonSchema']['additionalProperties'])
        self.assertEqual(payload['generationConfig']['maxOutputTokens'],3000)
        self.assertEqual(result['provider'],'gemini')
        self.assertEqual(result['extraction'],sample())
        self.assertEqual(result['usage'],dict(input_tokens=321,output_tokens=123,total_tokens=444))
        self.assertNotIn('gemini-test-secret',request.data.decode())
        self.assertNotIn('gemini-test-secret',json.dumps(result))

    def test_shelf_uses_its_own_schema(self):
        transport = Mock(return_value=io.BytesIO(json.dumps(interaction(shelf())).encode()))
        result = GeminiVisionProvider('test',transport=transport).detect_shelf(b'\xff\xd8image',consent=True,cancel=threading.Event())
        payload = json.loads(transport.call_args.args[0].data)
        self.assertEqual(payload['generationConfig']['maxOutputTokens'],12000)
        self.assertIn('regions',payload['generationConfig']['responseJsonSchema']['properties'])
        self.assertEqual(result['extraction'],shelf())

    def test_missing_key_invalid_model_and_key_characters(self):
        for key in ('','\n','test\nsecret','ümlaut'):
            with self.assertRaises(VisionError): GeminiVisionProvider(key)
        for model in ('gpt-5.6-luna','gemini-foo?key=secret','gemini-foo/../x',None):
            with self.assertRaises(VisionError): GeminiVisionProvider('test',model)

    def test_consent_cancel_and_bad_image_prevent_network(self):
        transport = Mock()
        provider = GeminiVisionProvider('test',transport=transport)
        cancel = threading.Event()
        for consent in (False,None,1):
            with self.assertRaises(VisionError): provider.analyze(b'\xff\xd8image',consent=consent,cancel=cancel)
        with self.assertRaises(VisionError): provider.analyze(b'PNG',consent=True,cancel=cancel)
        cancel.set()
        with self.assertRaises(VisionCancelled): provider.detect_shelf(b'\xff\xd8image',consent=True,cancel=cancel)
        transport.assert_not_called()

    def test_incomplete_blocked_refusal_ambiguous_and_malformed(self):
        candidates = [None,{}, {'error':{'code':400}}, {'candidates':None}]
        for change in ('empty','refusal','duplicate','missing_text','null_part','max_tokens','blocked','thought_only'):
            data = interaction()
            if change == 'empty': data['candidates'] = []
            if change == 'refusal': data['candidates'][0]['finishReason'] = 'SAFETY'
            if change == 'max_tokens': data['candidates'][0]['finishReason'] = 'MAX_TOKENS'
            if change == 'blocked': data['promptFeedback'] = {'blockReason':'SAFETY'}
            if change == 'duplicate': data['candidates'].append(deepcopy(data['candidates'][0]))
            if change == 'missing_text': del data['candidates'][0]['content']['parts'][1]['text']
            if change == 'null_part': data['candidates'][0]['content']['parts'] = [None]
            if change == 'thought_only': data['candidates'][0]['content']['parts'] = [{'thought':True,'text':'not output'}]
            candidates.append(data)
        for data in candidates:
            with self.assertRaises(VisionError): parse_response(data)

    def test_strict_json_and_local_schema_validation(self):
        for value in ('{"x":1,"x":2}','{"x":NaN}','not json',json.dumps({'fields': {}})):
            data = interaction()
            data['candidates'][0]['content']['parts'][1]['text'] = value
            with self.assertRaises(VisionError): parse_response(data)
        data = sample()
        data['overall'] = 9
        with self.assertRaises(VisionError): parse_response(interaction(data))

    def test_http_errors_sanitized_no_automatic_retry(self):
        for code in (301,307,400,401,403,404,429,500):
            transport = Mock(side_effect=HTTPError(GEMINI_ENDPOINT,code,'sensitive raw error',{},io.BytesIO(b'secret response')))
            provider = GeminiVisionProvider('sensitive-key',transport=transport)
            with self.assertRaises(VisionError) as error:
                provider.analyze(b'\xff\xd8image',consent=True,cancel=threading.Event())
            self.assertNotIn('sensitive',str(error.exception))
            self.assertNotIn('secret',str(error.exception))
            self.assertEqual(transport.call_count,1)

    def test_transport_errors_and_oversized_response(self):
        for exc in (URLError('secret'),TimeoutError('secret'),RuntimeError('secret')):
            transport = Mock(side_effect=exc)
            with self.assertRaises(VisionError) as error:
                GeminiVisionProvider('key',transport=transport).analyze(b'\xff\xd8x',consent=True,cancel=threading.Event())
            self.assertNotIn('secret',str(error.exception))
        transport = Mock(return_value=io.BytesIO(b'x'*(2*1024*1024+1)))
        with self.assertRaises(VisionError):
            GeminiVisionProvider('key',transport=transport).analyze(b'\xff\xd8x',consent=True,cancel=threading.Event())

    def test_cancel_after_response_discards_result(self):
        cancel = threading.Event()
        def transport(*args,**kwargs):
            cancel.set()
            return io.BytesIO(json.dumps(interaction()).encode())
        with self.assertRaises(VisionCancelled):
            GeminiVisionProvider('key',transport=transport).analyze(b'\xff\xd8x',consent=True,cancel=cancel)


class GeminiSettingsTests(unittest.TestCase):
    def test_settings_switch_preserves_separate_models_and_never_saves_keys(self):
        values = prefs()
        with patch('papierbibliothek.ui.vision.settings',return_value=values):
            dialog = SettingsDialog('openai-secret',gemini_session_key='gemini-secret')
            self.addCleanup(dialog.close)
            self.assertEqual(dialog.provider.currentData(),'openai')
            dialog.provider.setCurrentIndex(1)
            self.assertFalse(dialog.key.isEnabled())
            self.assertTrue(dialog.gemini_key.isEnabled())
            self.assertEqual(dialog.key.text(),'openai-secret')
            self.assertEqual(dialog.gemini_key.text(),'gemini-secret')
            dialog.gemini_model.setCurrentText('gemini-2.5-flash')
            dialog.accept()
            self.assertEqual(values['provider'],'gemini')
            self.assertEqual(values['gemini_model'],'gemini-2.5-flash')
            self.assertEqual(values['model'],'gpt-5.6-luna')
            self.assertNotIn('secret',json.dumps(values))

    def test_cancel_settings_does_not_change_configuration(self):
        values = prefs()
        with patch('papierbibliothek.ui.vision.settings',return_value=values):
            dialog = SettingsDialog()
            dialog.provider.setCurrentIndex(1)
            dialog.reject()
            self.assertEqual(values,prefs())
            dialog.close()

    def test_provider_selects_only_its_key_and_model(self):
        values = prefs()
        with patch('papierbibliothek.ui.main.settings',return_value=values), \
             patch('papierbibliothek.ui.main.OpenAIVisionProvider') as openai, \
             patch('papierbibliothek.ui.main.GeminiVisionProvider') as gemini, \
             patch.dict(os.environ,{'OPENAI_API_KEY':'openai-env','GEMINI_API_KEY':'gemini-env'},clear=True):
            window = MainDialog()
            self.addCleanup(window.close)
            self.assertEqual(window.selected_provider()[1],'OpenAI')
            openai.assert_called_once_with('openai-env',values['model'])
            gemini.assert_not_called()
            values['provider'] = 'gemini'
            self.assertEqual(window.selected_provider()[1],'Google Gemini')
            gemini.assert_called_once_with('gemini-env',values['gemini_model'])
            window.gemini_session_key = 'gemini-session'
            window.session_key = 'openai-session'
            window.selected_provider()
            gemini.assert_called_with('gemini-session',values['gemini_model'])
            self.assertEqual(openai.call_count,1)

    def test_missing_gemini_key_never_falls_back_to_openai(self):
        values = prefs()
        values['provider'] = 'gemini'
        with patch('papierbibliothek.ui.main.settings',return_value=values), \
             patch('papierbibliothek.ui.main.OpenAIVisionProvider') as openai, \
             patch.dict(os.environ,{'OPENAI_API_KEY':'openai-env'},clear=True):
            window = MainDialog()
            self.addCleanup(window.close)
            with self.assertRaises(VisionError): window.selected_provider()
            openai.assert_not_called()

    def test_unknown_provider_does_not_send(self):
        values = prefs()
        values['provider'] = 'unknown'
        with patch('papierbibliothek.ui.main.settings',return_value=values):
            window = MainDialog()
            self.addCleanup(window.close)
            with self.assertRaises(ValueError): window.selected_provider()

    def test_paid_action_identifies_recipient_for_both_workflows(self):
        image = QImage(100,100,QImage.Format.Format_RGB32)
        image.fill(QColor('white'))
        for shelf_mode in (False,True):
            dialog = CropDialog(image,DEFAULT_GEMINI_MODEL,shelf=shelf_mode,provider_name='Google Gemini')
            self.assertIn('Google Gemini',dialog.disclosure.text())
            self.assertNotIn('OpenAI',dialog.disclosure.text())
            self.assertIn('Kostenpflichtig auswerten',dialog.disclosure.text())
            self.assertEqual(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled(), shelf_mode)
            dialog.close()

    def test_close_discards_both_session_keys(self):
        window = MainDialog()
        window.session_key = 'openai-session'
        window.gemini_session_key = 'gemini-session'
        window.pending_result = {'provider':GeminiVisionProvider('gemini-session')}
        window.close()
        self.assertEqual(window.session_key,'')
        self.assertEqual(window.gemini_session_key,'')
        self.assertIsNone(window.pending_result)


class GeminiWorkflowTests(unittest.TestCase):
    setUp = test_vision.VisionWorkflowTests.setUp

    def run_workflow(self, shelf_mode):
        values = prefs()
        values['provider'] = 'gemini'
        ui_thread = threading.get_ident()
        def transport(*args,**kwargs):
            self.assertNotEqual(threading.get_ident(),ui_thread)
            return io.BytesIO(json.dumps(interaction(shelf() if shelf_mode else sample())).encode())
        provider = GeminiVisionProvider('synthetic-gemini-secret',transport=transport)
        with patch('papierbibliothek.ui.main.settings',return_value=values), \
             patch('papierbibliothek.ui.main.GeminiVisionProvider',return_value=provider), \
             patch('papierbibliothek.ui.main.OpenAIVisionProvider') as openai, \
             patch('papierbibliothek.ui.main.CropDialog') as crop, \
             patch('papierbibliothek.ui.main.ReviewDialog') as review, \
             patch('papierbibliothek.ui.main.RegionsDialog') as regions:
            crop.return_value.exec.return_value = QDialog.DialogCode.Accepted
            crop.return_value.jpeg = self.jpeg
            crop.return_value.box = self.box
            review.return_value.exec.return_value = QDialog.DialogCode.Rejected
            regions.return_value.exec.return_value = QDialog.DialogCode.Rejected
            window = MainDialog()
            window.show()
            self.addCleanup(window.close)
            self.assertTrue(window.load_project(self.store.path))
            if shelf_mode:
                window.prepare_shelf(True)
            else:
                window.analyze_new()
            deadline = time.monotonic()+10
            while window.task is not None and time.monotonic()<deadline:
                QApplication.processEvents()
                time.sleep(.01)
            self.assertIsNone(window.task)
            self.assertIsNone(window.pending_error)
            self.assertEqual(crop.call_args.kwargs['provider_name'],'Google Gemini')
            self.assertEqual(len(window.project.books),2 if shelf_mode else 1)
            book = window.project.books[0]
            self.assertEqual((book.detection if shelf_mode else book.vision)['provider'],'gemini')
            self.assertNotIn('synthetic-gemini-secret',self.store.path.read_text(encoding='utf-8'))
            openai.assert_not_called()
            window.close()

    def test_gemini_single_book_background_to_persistence(self):
        self.run_workflow(False)

    def test_gemini_shelf_background_to_persistence(self):
        self.run_workflow(True)
