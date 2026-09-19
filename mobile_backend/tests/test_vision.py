import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from mobile_backend.config import Settings
from mobile_backend.server import create_app
from mobile_backend import vision
from mobile_backend.tests.test_backend import PASSWORD, ORIGIN, photograph


VALID = dict(raw_text='Müller\nDas Buch\nISBN 978-0-306-40615-7', title='Das Buch', subtitle=None,
             authors=['Müller, Anne'], publisher='Verlag', language='de', publication_year=2024,
             isbn10='0306406152', isbn13='9780306406157',
             confidence=dict(author=.9,title=.95,publisher=.6,isbn=.98,overall=.9))


class VisionValidationTests(unittest.TestCase):
    def test_invalid_or_conflicting_isbn_is_never_kept(self):
        invalid = vision.VisionResult.model_validate(dict(VALID, isbn10='bad', isbn13='9780306406158'))
        self.assertIsNone(invalid.isbn10);self.assertIsNone(invalid.isbn13)
        conflict = vision.VisionResult.model_validate(dict(VALID, isbn10='080442957X', isbn13='9780306406157'))
        self.assertIsNone(conflict.isbn10);self.assertIsNone(conflict.isbn13)

    def test_extra_fields_and_bad_confidence_rejected(self):
        with self.assertRaises(Exception):vision.VisionResult.model_validate(dict(VALID, secret='no'))
        with self.assertRaises(Exception):vision.VisionResult.model_validate(dict(VALID, confidence=dict(VALID['confidence'],overall=2)))

    @patch('mobile_backend.vision.urlopen')
    def test_openai_request_is_image_structured_and_key_not_returned(self, urlopen):
        response=Mock();response.read.return_value=json.dumps({'output':[{'content':[{'type':'output_text','text':json.dumps(VALID)}]}]}).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);urlopen.return_value=response
        settings=Settings(password=PASSWORD,origin=ORIGIN,openai_api_key='test-secret',ai_provider='openai')
        parsed=vision.analyze(settings,'openai',photograph(),'spine')
        request=urlopen.call_args.args[0]
        self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
        self.assertNotIn('test-secret',request.data.decode())
        body=json.loads(request.data);self.assertEqual(body['text']['format']['type'],'json_schema')
        self.assertIn('input_image',str(body));self.assertEqual(parsed['isbn13'],'9780306406157')

    @patch('mobile_backend.vision.urlopen')
    def test_gemini_request_and_json_validation(self, urlopen):
        response=Mock();response.read.return_value=json.dumps({'candidates':[{'content':{'parts':[{'text':json.dumps(VALID)}]}}]}).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);urlopen.return_value=response
        settings=Settings(password=PASSWORD,origin=ORIGIN,gemini_api_key='test-secret',ai_provider='gemini')
        parsed=vision.analyze(settings,'gemini',photograph(),'titlepage')
        request=urlopen.call_args.args[0]
        self.assertIn(':generateContent',request.full_url);self.assertNotIn('test-secret',request.full_url)
        self.assertEqual(parsed['provider'],'gemini')


class VisionApiTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp=tempfile.TemporaryDirectory()
        self.settings=Settings(password=PASSWORD,origin=ORIGIN,database=Path(self.tmp.name)/'db.sqlite3',openai_api_key='fake-key')
        self.app=create_app(self.settings);self.client=TestClient(self.app,base_url=ORIGIN);self.client.__enter__()
        self.headers={'Origin':ORIGIN,'X-Papierbib':'1'}
        self.client.post('/api/login',headers=self.headers,json={'password':PASSWORD})

    def tearDown(self):self.client.__exit__(None,None,None);self.tmp.cleanup()

    def test_status_does_not_leak_key(self):
        response=self.client.get('/api/vision/status')
        self.assertEqual(response.json()['configured'],['openai'])
        self.assertNotIn('fake-key',response.text)

    @patch('mobile_backend.vision.analyze',return_value=dict(VALID,provider='openai',model='gpt-4o-mini',analyzed_at='2026-01-01T00:00:00Z'))
    def test_consent_kind_and_no_image_persistence(self, analyze):
        denied=self.client.post('/api/vision/analyze?kind=spine',headers=self.headers,content=photograph())
        self.assertEqual(denied.status_code,400);analyze.assert_not_called()
        response=self.client.post('/api/vision/analyze?kind=spine&consent=true',headers=self.headers,content=photograph())
        self.assertEqual(response.status_code,200,response.text);self.assertFalse(response.json()['stored'])
        self.assertEqual(response.json()['result']['title'],'Das Buch')
        self.assertNotIn('fake-key',response.text)
        self.assertEqual(self.client.post('/api/vision/analyze?kind=shelf&consent=true',headers=self.headers,content=photograph()).status_code,422)

    @patch('mobile_backend.vision.analyze',side_effect=vision.VisionError('KI-Anbieter hat die Anfrage abgelehnt oder ist nicht verfügbar (HTTP 401).'))
    def test_provider_error_is_actionable_and_secret_free(self, analyze):
        response=self.client.post('/api/vision/analyze?kind=spine&consent=true',headers=self.headers,content=photograph())
        self.assertEqual(response.status_code,503)
        self.assertIn('HTTP 401',response.text)
        self.assertNotIn('fake-key',response.text)


if __name__=='__main__':unittest.main()
