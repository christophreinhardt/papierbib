import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from calibre.ebooks.metadata.book.base import Metadata
from calibre.library import db as open_library
from qt.core import Qt,QInputDialog

from papierbibliothek.models import Book
from papierbibliothek.persistence.project import ProjectStore
from papierbibliothek.calibre_plugin.importer import (
    CalibreImportError, authors, duplicate_ids, fetch_cover, import_books,
    metadata_for, prepare_import,
)
from papierbibliothek.ui.calibre_import import ImportDialog
from papierbibliothek.ui.main import MainDialog


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store,self.project=ProjectStore.create(Path(self.temp.name)/'projekt','Test')
        self.book=Book(title='Die Verwandlung',author='Franz Kafka & Max Mustermann',
                       publisher='Reclam',publication_year=2015,language='de',
                       isbn13='9783150099001',tags=['Klassiker'],status='matched')
        self.book.confidence['overall']=.96
        self.book.provider_matches=[{'provider':'Open Library','cover_url':'https://covers.openlibrary.org/b/id/1-M.jpg'}]
        self.project.books.append(self.book);self.store.save(self.project)
        self.db=Mock();self.db.search.return_value=set();self.db.create_book_entry.return_value=42
        self.db.has_id.return_value=True
        current=Metadata('Alt',['Alt']);current.tags=['Vorhanden'];current.set_identifier('doi','10/x')
        self.db.get_metadata.return_value=current
        self.db.field_metadata.custom_field_metadata.return_value={
            '#scan_status':{'datatype':'text'},'#scan_confidence':{'datatype':'float'},
            '#scan_source':{'datatype':'text'},'#scan_review_note':{'datatype':'text'}}
        self.cancel=threading.Event()

    def test_metadata_mapping_authors_language_isbn_and_tags(self):
        mi=metadata_for(self.book)
        self.assertEqual(authors(self.book.author),['Franz Kafka','Max Mustermann'])
        self.assertEqual(mi.authors,['Franz Kafka','Max Mustermann'])
        self.assertEqual(mi.get_identifiers()['isbn'],'9783150099001')
        self.assertIn('Papierbuch',mi.tags);self.assertEqual(mi.pubdate.year,2015)

    def test_duplicate_search_is_exact(self):
        self.db.search.return_value={3,1}
        self.assertEqual(duplicate_ids(self.db,self.book),[1,3])
        self.db.search.assert_called_once_with('identifiers:"=isbn:9783150099001"')

    def test_create_and_custom_fields_are_persisted(self):
        result=import_books(self.store,self.project,[{'book_id':self.book.book_id,'action':'create'}],
                            self.db,self.cancel,lambda value:None)
        imported=result['project'].books[0]
        self.assertEqual((imported.status,imported.calibre_book_id),('imported',42))
        self.assertEqual(self.store.load().books[0].calibre_book_id,42)
        self.db.create_book_entry.assert_called_once()
        fields=[call.args[0] for call in self.db.set_field.call_args_list]
        self.assertIn('#scan_status',fields);self.assertIn('#scan_confidence',fields)

    def test_duplicate_blocks_create_without_writing(self):
        self.db.search.return_value={7}
        result=import_books(self.store,self.project,[{'book_id':self.book.book_id,'action':'create'}],
                            self.db,self.cancel,lambda value:None)
        self.db.create_book_entry.assert_not_called()
        self.assertEqual(result['project'].books[0].status,'import_error')
        self.assertIn('bereits in Calibre',result['results'][0]['error'])

    def test_explicit_update_merges_identifiers_and_tags(self):
        result=import_books(self.store,self.project,[{'book_id':self.book.book_id,'action':'update','calibre_book_id':7}],
                            self.db,self.cancel,lambda value:None)
        self.assertEqual(result['changed_ids'],[7]);self.db.create_book_entry.assert_not_called()
        mappings={call.args[0]:call.args[1] for call in self.db.set_field.call_args_list}
        self.assertEqual(mappings['identifiers'][7],{'doi':'10/x','isbn':'9783150099001'})
        self.assertEqual(mappings['tags'][7],['Vorhanden','Klassiker','Papierbuch'])

    def test_prepare_filters_status_and_reports_duplicates(self):
        self.db.search.return_value={9}
        self.project.books.append(Book(title='Ungeprüft',status='needs_manual_review'))
        result=prepare_import(self.project,self.db,self.cancel,lambda value:None)
        self.assertEqual(len(result['import_preview']),1)
        self.assertEqual(result['import_preview'][0]['duplicates'],[9])

    def test_cancel_keeps_completed_import(self):
        second=Book(title='Zwei',status='manual_confirmed');self.project.books.append(second);self.store.save(self.project)
        def create(*args,**kwargs):
            self.cancel.set();return 42
        self.db.create_book_entry.side_effect=create
        plans=[{'book_id':self.book.book_id,'action':'create'},{'book_id':second.book_id,'action':'create'}]
        result=import_books(self.store,self.project,plans,self.db,self.cancel,lambda value:None)
        self.assertTrue(result['cancelled']);self.assertEqual(result['project'].books[0].status,'imported')
        self.assertEqual(result['project'].books[1].status,'manual_confirmed')

    def test_cover_security_and_signature(self):
        self.assertEqual(fetch_cover('https://covers.openlibrary.org/x',
                         transport=Mock(return_value=io.BytesIO(bytes.fromhex('ffd8')+b'image'))),
                         bytes.fromhex('ffd8')+b'image')
        for url in ('http://covers.openlibrary.org/x','https://evil.example/x'):
            with self.assertRaises(CalibreImportError):fetch_cover(url)

    def test_import_dialog_defaults_and_explicit_update(self):
        rows=[{'book_id':'x','title':'Buch','author':'A','isbn':'9783150099001',
               'status':'matched','duplicates':[7],'calibre_book_id':None}]
        dialog=ImportDialog(rows);self.addCleanup(dialog.close)
        self.assertEqual(dialog.table.item(0,0).checkState(),Qt.CheckState.Unchecked)
        dialog.table.item(0,0).setCheckState(Qt.CheckState.Checked);dialog.actions[0].setCurrentIndex(1)
        dialog.accept()
        self.assertEqual(dialog.plans,[{'book_id':'x','action':'update','calibre_book_id':7}])

    def test_import_dialog_allows_manual_calibre_id(self):
        rows=[{'book_id':'x','title':'Buch','author':'A','isbn':None,
               'status':'manual_confirmed','duplicates':[],'calibre_book_id':None}]
        dialog=ImportDialog(rows);self.addCleanup(dialog.close)
        dialog.actions[0].setCurrentIndex(1)
        with patch.object(QInputDialog,'getInt',return_value=(23,True)):dialog.accept()
        self.assertEqual(dialog.plans,[{'book_id':'x','action':'update','calibre_book_id':23}])

    def test_real_temporary_calibre_library(self):
        with tempfile.TemporaryDirectory(prefix='pb-lib-',dir=Path.home()) as library_path:
            library=open_library(library_path)
            try:
                api=library.new_api
                result=import_books(self.store,self.project,[{'book_id':self.book.book_id,'action':'create'}],
                                    api,self.cancel,lambda value:None)
                book_id=result['changed_ids'][0]
                self.assertEqual(api.search('identifiers:"=isbn:9783150099001"'),{book_id})
                mi=api.get_metadata(book_id)
                self.assertEqual(mi.title,'Die Verwandlung');self.assertEqual(mi.authors,['Franz Kafka','Max Mustermann'])
                self.assertIn('Papierbuch',mi.tags)
            finally:
                library.close()

    def test_gui_refresh_announces_new_rows_before_refreshing_ids(self):
        model=Mock();gui=Mock();gui.library_view.model.return_value=model
        MainDialog.refresh_calibre(Mock(calibre_gui=gui),[42,43],2)
        model.books_added.assert_called_once_with(2)
        model.refresh_ids.assert_called_once_with({42,43})
        gui.tags_view.recount.assert_called_once_with()

    def test_gui_refresh_falls_back_to_full_model_refresh(self):
        model=Mock();model.books_added.side_effect=RuntimeError('changed API')
        gui=Mock();gui.library_view.model.return_value=model
        MainDialog.refresh_calibre(Mock(calibre_gui=gui),[42],1)
        model.refresh.assert_called_once_with()


if __name__=='__main__':unittest.main()
