from copy import deepcopy
import io,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.error import HTTPError,URLError

from papierbibliothek.models import Book,Project
from papierbibliothek.persistence.project import ProjectStore
from papierbibliothek.metadata_providers import *
from papierbibliothek.metadata_providers.cache import MetadataCache
from papierbibliothek.metadata_providers.matching import reconcile,apply_match,score_record
from papierbibliothek.metadata_providers.workflow import search_book,search_books
from papierbibliothek.ui.main import MainDialog
from papierbibliothek.ui.metadata import MetadataDialog
from qt.core import QMessageBox
from papierbibliothek.metadata_providers.base import text,isbn_pair


def record(provider='Open Library',pid='1',title='Die Verwandlung',author='Franz Kafka',isbn='9783150099001',publisher='Reclam',year=2015):
    return MetadataRecord(provider,pid,title,[author],publisher=publisher,publication_year=year,isbn13=isbn,source_url='https://example.org/book')


class ProviderParsingTests(unittest.TestCase):
    def test_lobid_real_shape_roles_publication_and_isbn_query(self):
        payload={'member':[{'id':'http://lobid.org/resources/990021434050206441#!',
            'title':'Die Verwandlung','isbn':['3150099005','9783150099001'],
            'contribution':{'agent':{'label':'Kafka, Franz'},
                            'role':{'id':'http://id.loc.gov/vocabulary/relators/aut','label':'Autor/in'}},
            'publication':{'startDate':'1978','publishedBy':['Reclam']},
            'language':{'id':'http://id.loc.gov/vocabulary/iso639-2/ger'}}]}
        transport=Mock(return_value=io.BytesIO(json.dumps(payload).encode()))
        row=LobidProvider(transport=transport).get_by_isbn('978-3-15-009900-1')[0]
        self.assertEqual((row.title,row.authors,row.publisher,row.publication_year),
                         ('Die Verwandlung',['Franz Kafka'],'Reclam',1978))
        self.assertEqual(row.isbn13,'9783150099001')
        self.assertTrue(row.source_url.startswith('https://lobid.org/resources/'))
        url=transport.call_args.args[0].full_url
        self.assertIn('q=isbn%3A9783150099001',url)

    def test_lobid_exact_isbn_deduplicates_catalogue_copies_by_completeness(self):
        sparse={'id':'http://lobid.org/resources/sparse#!','title':'Die Verwandlung',
                'isbn':['9783150099001']}
        complete={'id':'http://lobid.org/resources/complete#!','title':'Die Verwandlung',
                  'isbn':['9783150099001'],'publication':{'startDate':'1978','publishedBy':['Reclam']},
                  'contribution':{'agent':{'label':'Kafka, Franz'},
                                  'role':{'id':'http://id.loc.gov/vocabulary/relators/aut'}}}
        transport=Mock(return_value=io.BytesIO(json.dumps(
            {'member':[sparse,complete]}).encode()))
        rows=LobidProvider(transport=transport).get_by_isbn('9783150099001')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].provider_id,'complete')
        self.assertEqual(rows[0].authors,['Franz Kafka'])

    def test_control_markers_and_annotated_isbn_are_normalized(self):
        self.assertEqual(text('\u0098Die\u009c Verwandlung'),'Die Verwandlung')
        self.assertEqual(isbn_pair(['ISBN 978-3-15-009900-1 (kart.)'])[1],'9783150099001')
    def test_openlibrary_parsing_and_query(self):
        payload={'docs':[{'key':'/works/OL1W','title':'Die Verwandlung','author_name':['Franz Kafka'],'publisher':['Reclam'],'publish_year':[2015],'isbn':['9783150099001'],'language':['ger'],'cover_i':12}]}
        transport=Mock(return_value=io.BytesIO(json.dumps(payload).encode()))
        rows=OpenLibraryProvider(transport=transport).search(title='Die Verwandlung',author='Kafka')
        self.assertEqual(rows[0].isbn13,'9783150099001');self.assertEqual(rows[0].authors,['Franz Kafka'])
        url=transport.call_args.args[0].full_url
        self.assertIn('title=Die+Verwandlung',url);self.assertIn('author=Kafka',url);self.assertNotIn('fields=%2A',url)

    def test_openlibrary_isbn_uses_edition_endpoint(self):
        payload={'ISBN:9783150099001':{'title':'Die Verwandlung','authors':[{'name':'Franz Kafka'}],
                 'publishers':[{'name':'Reclam'}],'publish_date':'2015','url':'https://openlibrary.org/books/OL1M'}}
        transport=Mock(return_value=io.BytesIO(json.dumps(payload).encode()))
        row=OpenLibraryProvider(transport=transport).get_by_isbn('978-3-15-009900-1')[0]
        self.assertEqual(row.isbn13,'9783150099001');self.assertEqual(row.title,'Die Verwandlung')
        url=transport.call_args.args[0].full_url
        self.assertIn('/api/books?',url);self.assertIn('jscmd=data',url);self.assertNotIn('/search.json',url)

    def test_google_parsing_optional_key_and_https_cover(self):
        payload={'items':[{'id':'g1','volumeInfo':{'title':'Buch','authors':['Änne'],'publisher':'V','publishedDate':'2020-04','language':'de','industryIdentifiers':[{'type':'ISBN_13','identifier':'9783150099001'}],'imageLinks':{'thumbnail':'http://books.google.com/x'}}}]}
        transport=Mock(return_value=io.BytesIO(json.dumps(payload).encode()))
        row=GoogleBooksProvider('key',transport=transport).get_by_isbn('9783150099001')[0]
        self.assertEqual(row.language,'de');self.assertTrue(row.cover_url.startswith('https://'))
        self.assertIn('key=key',transport.call_args.args[0].full_url)

    def test_dnb_marc_parsing_and_cql_escaping(self):
        xml=b'''<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"><records><record><recordData><record xmlns="http://www.loc.gov/MARC21/slim"><controlfield tag="001">123</controlfield><datafield tag="020"><subfield code="a">9783150099001</subfield></datafield><datafield tag="100"><subfield code="a">Kafka, Franz</subfield></datafield><datafield tag="245"><subfield code="a">Die Verwandlung /</subfield><subfield code="b">Erz&#228;hlung</subfield></datafield><datafield tag="264"><subfield code="b">Reclam</subfield><subfield code="c">2015</subfield></datafield></record></recordData></record></records></searchRetrieveResponse>'''
        transport=Mock(return_value=io.BytesIO(xml))
        row=DNBProvider(transport=transport).search(isbn='9783150099001')[0]
        self.assertEqual((row.title,row.subtitle,row.publisher,row.publication_year),('Die Verwandlung','Erzählung','Reclam',2015))
        self.assertNotIn('"',DNBProvider.cql('bad" query')[1:-1])

    def test_custom_requires_https_and_normalized_contract(self):
        for url in ('http://example.org','https://user:pass@example.org','https://example.org/x?q=1'):
            with self.assertRaises(ProviderError):CustomJSONProvider(url)
        payload={'items':[{'id':'x','title':'Buch','authors':['A'],'isbn13':'9783150099001','source_url':'https://example.org/x'}]}
        transport=Mock(return_value=io.BytesIO(json.dumps(payload).encode()))
        provider=CustomJSONProvider('https://example.org/search','secret',transport=transport)
        self.assertEqual(provider.search(title='Buch')[0].title,'Buch')
        request=transport.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'),'Bearer secret');self.assertNotIn('secret',request.full_url)

    def test_http_network_json_xml_and_size_errors_sanitized(self):
        for exc in (HTTPError('https://openlibrary.org/search.json',429,'private',{},io.BytesIO(b'secret')),URLError('private')):
            with self.assertRaises(ProviderError) as error:OpenLibraryProvider(transport=Mock(side_effect=exc)).search(title='x')
            self.assertNotIn('private',str(error.exception));self.assertNotIn('secret',str(error.exception))
        with self.assertRaises(ProviderError):OpenLibraryProvider(transport=Mock(return_value=io.BytesIO(b'{bad'))).search(title='x')
        with self.assertRaises(ProviderError):DNBProvider(transport=Mock(return_value=io.BytesIO(b'<bad'))).search(title='x')
        with self.assertRaises(ProviderError):OpenLibraryProvider(transport=Mock(return_value=io.BytesIO(b'x'*(2*1024*1024+1)))).search(title='x')


class MatchingTests(unittest.TestCase):
    def test_metadata_dialog_requires_explicit_confirmation(self):
        book=Book(title='OCR')
        book.provider_matches=reconcile(Book(title='Die Verwandlung',author='Franz Kafka'),[record(isbn=None)])['matches']
        dialog=MetadataDialog(book);self.addCleanup(dialog.close)
        self.assertEqual(dialog.table.rowCount(),1)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            dialog.accept_match()
        self.assertEqual(dialog.book.title,'Die Verwandlung')
        self.assertEqual(book.title,'OCR')

    def test_setting_new_isbn_clears_contradictory_isbn10(self):
        book=Book(isbn10='3150099005',isbn13='9783150099001')
        MainDialog.set_book_isbn(book,'9780141187761')
        self.assertIsNone(book.isbn10);self.assertEqual(book.isbn13,'9780141187761')

    def test_exact_isbn_unique_match(self):
        book=Book(title='OCR wrong',isbn13='9783150099001')
        result=reconcile(book,[record(),record('Google Books','2')])
        self.assertEqual(result['status'],'matched');self.assertEqual(result['matches'][0]['score'],1);self.assertEqual(len(result['matches'][0]['sources']),2)

    def test_title_author_probable_weak_and_no_input(self):
        book=Book(title='Die Verwandlung',author='Franz Kafka')
        self.assertEqual(reconcile(book,[record(isbn=None)])['status'],'matched')
        self.assertEqual(reconcile(Book(title='Verwandlung',author='Kafka'),[record(isbn=None)])['status'],'probable_match')
        self.assertEqual(reconcile(Book(title='Ganz anders'),[record(isbn=None)])['status'],'needs_manual_review')
        self.assertEqual(reconcile(Book(),[])['status'],'needs_scan')

    def test_conflict_blocks_match_and_apply(self):
        a=record(isbn=None);b=record('Google Books','2',isbn=None,publisher='Anderer Verlag')
        result=reconcile(Book(title='Die Verwandlung',author='Franz Kafka'),[a,b])
        self.assertIn('publisher',result['matches'][0]['conflicts']);self.assertNotEqual(result['status'],'matched')
        with self.assertRaises(ProviderError):apply_match(Book(),result['matches'][0])

    def test_explicit_apply_preserves_original_and_sources(self):
        original=Book(title='OCR-Titel',notes='Behalten')
        proposal=reconcile(Book(title='Die Verwandlung',author='Franz Kafka'),[record(isbn=None)])['matches'][0]
        result=apply_match(original,proposal)
        self.assertEqual(result.title,'Die Verwandlung');self.assertEqual(result.notes,'Behalten');self.assertEqual(original.title,'OCR-Titel');self.assertTrue(result.provider_matches)


class CacheWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store,self.project=ProjectStore.create(Path(self.temp.name)/'p','Test')
        self.project.books.append(Book(title='Die Verwandlung',author='Franz Kafka'))
        self.store.save(self.project);self.cancel=threading.Event()

    def test_cache_roundtrip_key_has_no_query_and_corruption_safe(self):
        cache=MetadataCache(self.store);query={'isbn':'9783150099001'};cache.put('x',query,[record().to_dict()])
        raw=cache.path.read_text(encoding='utf-8');self.assertNotIn('9783150099001',next(iter(json.loads(raw)['entries'])))
        self.assertEqual(len(cache.get('x',query)),1);cache.path.write_text('{bad',encoding='utf-8');self.assertIsNone(MetadataCache(self.store).get('x',query))

    def test_workflow_cache_offline_errors_and_persistence(self):
        provider=Mock(name='provider');provider.name='Test';provider.search.return_value=[record('Test')]
        result=search_book(self.store,self.project,self.project.books[0].book_id,[provider],self.cancel,lambda x:None)
        self.assertEqual(result['project'].books[0].status,'matched');provider.search.assert_called_once()
        self.project=result['project'];provider.search.reset_mock()
        cached=search_book(self.store,self.project,self.project.books[0].book_id,[provider],self.cancel,lambda x:None,offline=True)
        provider.search.assert_not_called();self.assertTrue(cached['project'].books[0].provider_matches)

    def test_workflow_uses_isbn_first_and_falls_back(self):
        self.project.books[0].isbn13='9783150099001';self.store.save(self.project)
        provider=Mock();provider.name='Test';provider.search.side_effect=[[],[record('Test')]]
        result=search_book(self.store,self.project,self.project.books[0].book_id,[provider],self.cancel,lambda x:None)
        calls=provider.search.call_args_list
        self.assertEqual(calls[0].kwargs,{'isbn':'9783150099001'})
        self.assertEqual(calls[1].kwargs,{'title':'Die Verwandlung','author':'Franz Kafka'})
        self.assertEqual(result['project'].books[0].status,'matched')

    def test_provider_failures_are_partial_and_cancel_does_not_save(self):
        good=Mock();good.name='good';good.search.return_value=[record('good')]
        bad=Mock();bad.name='bad';bad.search.side_effect=ProviderError('bad: offline')
        result=search_book(self.store,self.project,self.project.books[0].book_id,[bad,good],self.cancel,lambda x:None)
        self.assertEqual(result['project'].books[0].status,'matched');self.assertEqual(result['errors'],['bad: offline'])
        before=self.store.path.read_bytes();self.cancel.set();cancelled=search_book(self.store,result['project'],self.project.books[0].book_id,[good],self.cancel,lambda x:None)
        self.assertTrue(cancelled['cancelled']);self.assertEqual(self.store.path.read_bytes(),before)

    def test_batch_saves_incrementally(self):
        second=Book(title='Zweites Buch');self.project.books.append(second);self.store.save(self.project)
        provider=Mock();provider.name='Test';provider.search.side_effect=[[record('Test')],[record('Test',pid='2',title='Zweites Buch',author='A')]]
        result=search_books(self.store,self.project,[x.book_id for x in self.project.books],[provider],
                            self.cancel,lambda x:None,pause=0)
        self.assertEqual(result['searched'],2);self.assertEqual(len(result['project'].books),2)
        self.assertEqual(len(self.store.load().books),2)
