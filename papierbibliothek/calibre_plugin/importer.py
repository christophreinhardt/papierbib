"""Calibre database boundary. No UI and no project mutation before a DB call succeeds."""
from copy import deepcopy
from datetime import datetime, timezone
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from calibre.ebooks.metadata.book.base import Metadata
from calibre.utils.localization import canonicalize_lang

from ..models import now
from ..vision.provider import NoRedirect


class CalibreImportError(ValueError):
    pass


def authors(value):
    result=[part.strip() for part in re.split(r'[ ]*&[ ]*',value or '') if part.strip()]
    return result or ['Unbekannt']


def metadata_for(book):
    if not book.title or not book.title.strip():raise CalibreImportError('Titel fehlt.')
    mi=Metadata(book.title.strip(),authors(book.author))
    if book.publisher:mi.publisher=book.publisher
    if book.publication_year:mi.pubdate=datetime(book.publication_year,1,1,tzinfo=timezone.utc)
    if book.language:
        language=canonicalize_lang(book.language) or book.language
        mi.languages=[language]
    mi.tags=list(dict.fromkeys([*book.tags,'Papierbuch']))
    if book.notes:mi.comments=book.notes
    isbn=book.isbn13 or book.isbn10
    if isbn:mi.set_identifier('isbn',isbn)
    return mi


def duplicate_ids(db,book):
    isbn=book.isbn13 or book.isbn10
    if not isbn:return []
    return sorted(db.search('identifiers:"=isbn:'+isbn+'"'))


def source_names(book):
    names=[]
    def visit(value):
        if isinstance(value,dict):
            provider=value.get('provider')
            if isinstance(provider,str) and provider not in names:names.append(provider)
            for source in value.get('sources',[]):visit(source)
    for value in book.provider_matches:visit(value)
    return names


def custom_values(book,store):
    image=book.title_page_path or book.crop_path or book.image_path
    return {'#scan_status':book.status,
            '#scan_confidence':book.confidence.get('overall'),
            '#scan_source':' + '.join(source_names(book)) or None,
            '#scan_image':str(store.asset(image)) if image else None,
            '#scan_review_note':book.notes}


def set_custom_fields(db,book_id,book,store):
    warnings=[]
    try:available=db.field_metadata.custom_field_metadata()
    except Exception:return ['Benutzerdefinierte Calibre-Felder konnten nicht gelesen werden.']
    for key,value in custom_values(book,store).items():
        if value is None or key not in available:continue
        datatype=available[key].get('datatype')
        try:
            if datatype=='text':value=str(value)
            elif datatype=='float':value=float(value)
            elif datatype=='int':value=int(round(value))
            elif datatype=='bool':value=bool(value)
            else:
                warnings.append(key+': nicht unterstützter Spaltentyp '+str(datatype));continue
            db.set_field(key,{book_id:value})
        except Exception:
            warnings.append(key+': Wert konnte nicht gesetzt werden.')
    return warnings


def update_existing(db,book_id,book):
    values={}
    for field,value in (('title',book.title),('authors',authors(book.author) if book.author else None),
                        ('publisher',book.publisher),('languages',[canonicalize_lang(book.language) or book.language] if book.language else None),
                        ('pubdate',datetime(book.publication_year,1,1,tzinfo=timezone.utc) if book.publication_year else None)):
        if value is not None:values[field]=value
    current=db.get_metadata(book_id)
    identifiers=current.get_identifiers()
    if book.isbn13 or book.isbn10:
        identifiers['isbn']=book.isbn13 or book.isbn10;values['identifiers']=identifiers
    values['tags']=list(dict.fromkeys([*(current.tags or []),*book.tags,'Papierbuch']))
    for field,value in values.items():db.set_field(field,{book_id:value})


def cover_url(book):
    found=[]
    def visit(value):
        if isinstance(value,dict):
            url=value.get('cover_url')
            if isinstance(url,str):found.append(url)
            for source in value.get('sources',[]):visit(source)
    for value in book.provider_matches:visit(value)
    return found[0] if found else None


def fetch_cover(url,timeout=15,transport=None):
    if not url:return None
    parsed=urlsplit(url)
    allowed=('covers.openlibrary.org','books.google.com','books.googleusercontent.com')
    if parsed.scheme!='https' or parsed.hostname not in allowed or parsed.username or parsed.password:
        raise CalibreImportError('Cover-URL ist nicht erlaubt.')
    request=Request(url,headers={'User-Agent':'Papierbibliothek-Calibre/0.5','Accept':'image/jpeg,image/png,image/webp'})
    try:
        with (transport or build_opener(NoRedirect()).open)(request,timeout=timeout) as response:data=response.read(10*1024*1024+1)
    except (HTTPError,URLError,OSError,socket.timeout):
        raise CalibreImportError('Cover konnte nicht geladen werden.') from None
    if len(data)>10*1024*1024 or not data.startswith((bytes.fromhex('ffd8'),bytes.fromhex('89504e47'),b'RIFF')):
        raise CalibreImportError('Coverdatei ist ungültig oder zu groß.')
    return data


def prepare_import(project,db,cancel,progress):
    rows=[]
    for index,book in enumerate(project.books,1):
        if cancel.is_set():return {'cancelled':True}
        if book.status not in ('matched','probable_match','manual_confirmed','import_error') or not book.title:continue
        progress(f'Calibre-Dublettenprüfung {index}/{len(project.books)} …')
        ids=duplicate_ids(db,book)
        if book.calibre_book_id and db.has_id(book.calibre_book_id) and book.calibre_book_id not in ids:
            ids.append(book.calibre_book_id);ids.sort()
        rows.append({'book_id':book.book_id,'title':book.title,'author':book.author,'isbn':book.isbn13 or book.isbn10,
                     'status':book.status,'duplicates':ids,'calibre_book_id':book.calibre_book_id})
    return {'import_preview':rows}


def import_books(store,project,plans,db,cancel,progress,include_cover=False,cover_fetcher=fetch_cover):
    candidate=deepcopy(project); results=[]; changed_ids=[]
    for index,plan in enumerate(plans,1):
        if cancel.is_set():break
        book=next((x for x in candidate.books if x.book_id==plan.get('book_id')),None)
        if not book:continue
        action=plan.get('action')
        if action=='skip':continue
        progress(f'Calibre-Import {index}/{len(plans)} …')
        try:
            if action=='create':
                duplicates=duplicate_ids(db,book)
                if duplicates:raise CalibreImportError('ISBN bereits in Calibre vorhanden: '+', '.join(map(str,duplicates)))
                cover=None
                if include_cover and cover_url(book):
                    try:cover=cover_fetcher(cover_url(book))
                    except CalibreImportError as exc:results.append({'book_id':book.book_id,'warning':str(exc)})
                calibre_id=db.create_book_entry(metadata_for(book),cover=cover,add_duplicates=True)
                if not isinstance(calibre_id,int):raise CalibreImportError('Calibre hat keinen Datensatz angelegt.')
            elif action=='update':
                calibre_id=plan.get('calibre_book_id')
                if not isinstance(calibre_id,int) or not db.has_id(calibre_id):raise CalibreImportError('Gewählter Calibre-Datensatz fehlt.')
                update_existing(db,calibre_id,book)
                if include_cover and cover_url(book):
                    try:db.set_cover({calibre_id:cover_fetcher(cover_url(book))})
                    except CalibreImportError as exc:results.append({'book_id':book.book_id,'warning':str(exc)})
            else:raise CalibreImportError('Unbekannte Importaktion.')
            book.calibre_book_id=calibre_id;book.status='imported';book.updated_at=now()
            warnings=set_custom_fields(db,calibre_id,book,store)
            store.save(candidate);changed_ids.append(calibre_id)
            results.append({'book_id':book.book_id,'calibre_book_id':calibre_id,'action':action,'warnings':warnings})
        except Exception as exc:
            message=str(exc) if isinstance(exc,CalibreImportError) else 'Calibre-Datenbankfehler.'
            book.status='import_error';book.updated_at=now()
            book.notes=((book.notes+'\n') if book.notes else '')+'Importfehler: '+message
            try:store.save(candidate)
            except Exception:pass
            results.append({'book_id':book.book_id,'error':message})
    return {'project':candidate,'calibre_import':True,'results':results,'changed_ids':changed_ids,
            'cancelled':cancel.is_set()}
