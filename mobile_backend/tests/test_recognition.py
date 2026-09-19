import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from mobile_backend import isbn, lobid, ocr
from mobile_backend.tests import test_backend as base
photograph = base.photograph


class ISBNTests(unittest.TestCase):
    def test_equivalent_and_unicode(self):
        self.assertEqual(isbn.canonical('ISBN-10: 0-306-40615-2'), '9780306406157')
        self.assertEqual(isbn.canonical('ISBN ９７８‐０‐３０６‐４０６１５‐７'), '9780306406157')
        self.assertEqual(isbn.isbn10('9780804429573'), '080442957X')
        self.assertEqual(isbn.canonical('080442957X'), '9780804429573')

    def test_invalid_never_repaired(self):
        for value in ('9780306406158','1234567890123','abc9780306406157','030640615X','978O306406157'):
            self.assertFalse(isbn.valid(value))
            with self.assertRaises(ValueError):
                isbn.canonical(value)

    def test_extract_only_isbns_no_embedded_substrings(self):
        text='Titel Müller Straße\nISBN-13: 978-0-306-40615-7\nISBN 0-306-40615-2\n123978030640615799\n9780306406158'
        self.assertEqual(isbn.extract(text), ['9780306406157'])
        self.assertEqual(isbn.extract('Müller, 2026. Preis 19,95 EUR'), [])


class LobidTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((Path(__file__).parent/'fixtures/lobid-990021367710206441.json').read_text(encoding='utf-8'))

    def test_official_fixture(self):
        record=lobid.parse({'member':[self.fixture]},'0256018243')[0]
        self.assertEqual(record['title'],'Labor economics')
        self.assertEqual(record['publication_year'],1976)
        self.assertEqual(record['publisher'],'Irwin')
        self.assertIn('Marshall, Ray',record['authors'])
        self.assertEqual(record['isbn13'],'9780256018240')
        self.assertEqual(record['edition'],'3. ed')

    def test_roles_and_alternative_editions(self):
        first=dict(self.fixture, title='Straße – Müller / Æ é ö ß',
                   contribution=[{'role':{'id':'http://id.loc.gov/vocabulary/relators/edt'},'agent':{'label':'Müller'}}])
        second=dict(first,edition=['4. Auflage'])
        records=lobid.parse({'member':[first,first,second,{},None]},'0256018243')
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]['authors'],[])
        self.assertEqual(records[0]['editors'],['Müller'])
        self.assertEqual(lobid.parse({'member':[self.fixture]},'9780306406157'),[])

    def test_bad_shape(self):
        for data in ([],{}, {'member':'bad'}):
            with self.assertRaises(lobid.ProviderError):lobid.parse(data,'9780306406157')

    def response(self,body,content_type='application/json'):
        response=Mock();response.headers={'Content-Type':content_type};response.read1.side_effect=[body,b'']
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        return response

    @patch('mobile_backend.lobid.build_opener')
    def test_timeout_bad_json_and_bot_page(self,opener):
        opener.return_value.open.side_effect=TimeoutError()
        with self.assertRaises(lobid.ProviderError):lobid.lookup('9780306406157')
        opener.return_value.open.side_effect=None
        for body,mime in ((b'{bad','application/json'),(b'<html>challenge</html>','text/html'),(b'x'*2_000_001,'application/json')):
            opener.return_value.open.return_value=self.response(body,mime)
            with self.assertRaises(lobid.ProviderError):lobid.lookup('9780306406157')

    @patch('mobile_backend.lobid.build_opener')
    def test_encoded_isbn_variants_and_timeout(self,opener):
        opener.return_value.open.return_value=self.response(b'{"member":[]}')
        self.assertEqual(lobid.lookup('0-306-40615-2'),[])
        args,kwargs=opener.return_value.open.call_args
        self.assertTrue(args[0].full_url.startswith('https://lobid.org/resources/search?'))
        self.assertIn('isbn%3A9780306406157',args[0].full_url)
        self.assertIn('isbn%3A0306406152',args[0].full_url)
        self.assertEqual(kwargs['timeout'],12)


class OCRTests(unittest.TestCase):
    @patch('mobile_backend.ocr.subprocess.run')
    def test_only_isbns_returned_stdin_timeout(self,run):
        run.return_value=Mock(stdout=b'Title secret\nISBN 978-0-306-40615-7\n')
        self.assertEqual(ocr.recognize_isbns(photograph()),['9780306406157'])
        args,kwargs=run.call_args
        self.assertEqual(args[0][1:3],['stdin','stdout'])
        self.assertLessEqual(kwargs['timeout'],4)
        self.assertEqual(kwargs['stderr'],subprocess.DEVNULL)
        self.assertTrue(kwargs['input'].startswith(b'\x89PNG'))

    @patch('mobile_backend.ocr.subprocess.run',side_effect=FileNotFoundError())
    def test_unavailable(self,run):
        with self.assertRaises(ocr.OCRUnavailable):ocr.recognize_isbns(photograph())


class RecognitionApiTests(unittest.TestCase):
    setUp=base.ApiTests.setUp
    tearDown=base.ApiTests.tearDown
    post=base.ApiTests.post
    login=base.ApiTests.login
    project=base.ApiTests.project
    upload=base.ApiTests.upload

    @patch('mobile_backend.lobid.lookup',side_effect=lobid.ProviderError('offline'))
    def test_isbn_saved_even_if_provider_fails_and_idempotent(self,lookup):
        project=self.project()
        response=self.post('/api/isbn/lookup',json={'isbn':'0306406152'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['error'])
        data=dict(book_id=str(uuid4()),isbn13=response.json()['isbn13'],status='draft')
        for _ in range(2):self.assertEqual(self.post(f'/api/projects/{project}/books',json=data).status_code,200)
        rows=self.client.get(f'/api/projects/{project}/books').json()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['isbn10'],'0306406152')
        self.assertIsNone(rows[0]['title'])
        self.assertEqual(rows[0]['status'],'draft')

    @patch('mobile_backend.lobid.lookup',return_value=[])
    def test_equivalent_queries_cached(self,lookup):
        self.login()
        for value in ('9780306406157','0-306-40615-2'):
            self.assertEqual(self.post('/api/isbn/lookup',json={'isbn':value}).status_code,200)
        lookup.assert_called_once()
        self.assertEqual(self.post('/api/isbn/lookup',json={'isbn':'9780306406158'}).status_code,422)
        lookup.assert_called_once()

    def test_confirm_needs_title_draft_does_not(self):
        project=self.project()
        data=dict(book_id=str(uuid4()),isbn13='9780306406157',status='confirmed')
        self.assertEqual(self.post(f'/api/projects/{project}/books',json=data).status_code,422)
        data.update(title='Müller – Straße',authors=['Müller, Anton','Goethe'],editors=['Æ é'])
        self.assertEqual(self.post(f'/api/projects/{project}/books',json=data).status_code,200)
        rows=self.client.get(f'/api/projects/{project}/books').json()
        self.assertEqual(rows[0]['authors'],['Müller, Anton','Goethe'])

    def test_cross_project_and_crop_integrity(self):
        project=self.project();photo=self.upload(project).json()
        other=self.post('/api/projects',json={'name':'Other'}).json()['project_id']
        data=dict(book_id=str(uuid4()),isbn13='9780306406157',**photo)
        self.assertEqual(self.post(f'/api/projects/{other}/books',json=data).status_code,422)
        self.assertEqual(self.post(f'/api/projects/{project}/books',json=data).status_code,200)
        data.update(photo_id=None,crop_id=None)
        self.assertEqual(self.post(f'/api/projects/{other}/books',json=data).status_code,422)

    @patch('mobile_backend.ocr.recognize_isbns',return_value=['9780306406157'])
    def test_ocr_consent_auth_no_image_persistence(self,recognize):
        self.assertEqual(self.post('/api/isbn/ocr?crop_confirmed=true',content=photograph()).status_code,401)
        project=self.project()
        self.assertEqual(self.post('/api/isbn/ocr',content=photograph()).status_code,400)
        recognize.assert_not_called()
        response=self.post('/api/isbn/ocr?crop_confirmed=true',content=photograph())
        self.assertEqual(response.json()['isbns'],['9780306406157'])
        self.assertFalse(response.json()['stored'])
        self.assertEqual(self.client.get(f'/api/projects/{project}/captures').json(),[])
        self.assertNotIn('raw_text',response.json())

    def test_migration_keeps_phase1_photos(self):
        project=self.project();photo=self.upload(project).json()
        with self.app.state.store.connect() as db:
            db.execute('DROP TABLE metadata_cache')
            db.execute('PRAGMA user_version=1')
        self.app.state.store.initialize()
        self.assertEqual(self.app.state.store.original(photo['photo_id'])[0],photograph())
        with self.app.state.store.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)

    def test_duplicates_reported_not_silently_overwritten(self):
        project=self.project()
        for index in range(2):
            result=self.post(f'/api/projects/{project}/books',json=dict(book_id=str(uuid4()),isbn13='9780306406157'))
            self.assertEqual(len(result.json()['duplicate_ids']),index)
        self.assertEqual(len(self.app.state.store.books(project)),2)


if __name__=='__main__':unittest.main()
