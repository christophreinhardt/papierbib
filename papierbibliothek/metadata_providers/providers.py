import re
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree as ET

from .base import (BookMetadataProvider, ProviderError, MetadataRecord, isbn_pair,
                   text, year, query_url)
from ..isbn import normalize, to_isbn13


def items(value):
    if value is None:return []
    return value if isinstance(value,list) else [value]


def values(value):
    result=[]
    for entry in items(value):
        if isinstance(entry,dict):entry=entry.get('label') or entry.get('name')
        cleaned=text(entry)
        if cleaned:result.append(cleaned)
    return result


def person(value):
    value=text(value)
    if value and ',' in value:
        family,given=value.split(',',1)
        value=(given.strip()+' '+family.strip()).strip()
    return value


class LobidProvider(BookMetadataProvider):
    name='lobid-resources'; hosts=('lobid.org',)
    endpoint='https://lobid.org/resources/search'

    def search(self,title=None,author=None,isbn=None,publisher=None):
        if isbn:
            query='isbn:'+normalize(isbn)
        elif title:
            query='title:"'+str(title).replace('"','\\"')[:500]+'"'
            if author:query+=' AND contribution.agent.label:'+str(author).split()[-1][:200]
        else:return []
        data=self.json(query_url(self.endpoint,[('q',query),('format','json'),('size','10')])) or {}
        if not isinstance(data,dict) or not isinstance(data.get('member',[]),list):
            raise ProviderError(self.name+': unerwartetes Antwortformat.')
        wanted=to_isbn13(isbn) if isbn else None
        result=[]
        for entry in data.get('member',[])[:10]:
            if not isinstance(entry,dict):continue
            try:
                i10,i13=isbn_pair(items(entry.get('isbn')))
                if wanted and (i13 or (to_isbn13(i10) if i10 else None))!=wanted:continue
                authors=[]
                for contribution in items(entry.get('contribution')):
                    if not isinstance(contribution,dict):continue
                    role_ids=[str(x.get('id') or '').rsplit('/',1)[-1].casefold()
                              for x in items(contribution.get('role')) if isinstance(x,dict)]
                    role_labels=[(text(x.get('label')) or '').casefold()
                                 for x in items(contribution.get('role')) if isinstance(x,dict)]
                    if 'aut' not in role_ids and not set(role_labels)&{'autor/in','autor','verfasser/in','verfasser','author'}:
                        continue
                    agent=contribution.get('agent') or {}
                    label=person(agent.get('label')) if isinstance(agent,dict) else None
                    if label and label not in authors:authors.append(label)
                publications=[x for x in items(entry.get('publication')) if isinstance(x,dict)]
                publishers=[x for publication in publications
                            for x in values(publication.get('publishedBy'))]
                dates=[publication.get('startDate') or publication.get('dateStatement')
                       for publication in publications]
                title_value=items(entry.get('title'))
                subtitle=items(entry.get('otherTitleInformation'))
                languages=items(entry.get('language'))
                language=None
                if languages:
                    language=languages[0].get('id') if isinstance(languages[0],dict) else languages[0]
                    language=text(str(language).rsplit('/',1)[-1])
                source=str(entry.get('id') or '').removesuffix('#!')
                source=re.sub(r'^http:', 'https:', source)
                provider_id=source.rsplit('/',1)[-1] if source else (i13 or i10)
                record=MetadataRecord(
                    self.name,provider_id,text(title_value[0]) if title_value else None,
                    authors,text(subtitle[0]) if subtitle else None,
                    publishers[0] if publishers else None,year(dates[0] if dates else None),
                    language,i10,i13,None,source or None).validate()
                if record.title:result.append(record)
            except (TypeError,ValueError,ProviderError):continue
        if wanted and result:
            # lobid can expose several catalogue copies for the same edition.
            # An exact ISBN identifies the edition; keep the most complete copy
            # so internal catalogue variance does not become a false conflict.
            result.sort(key=lambda record:(
                -sum(bool(value) for value in (
                    record.title,record.authors,record.publisher,
                    record.publication_year,record.language,record.isbn13)),
                record.provider_id))
            return result[:1]
        return result


class OpenLibraryProvider(BookMetadataProvider):
    name='Open Library'; hosts=('openlibrary.org',)
    def search(self,title=None,author=None,isbn=None,publisher=None):
        if isbn and not any((title,author,publisher)):return self.isbn_edition(isbn)
        params=[('limit','10'),('fields','key,title,subtitle,author_name,publisher,first_publish_year,publish_year,isbn,language,cover_i')]
        for key,value in (('isbn',isbn),('title',title),('author',author),('publisher',publisher)):
            if value: params.append((key,value))
        if len(params)==2: return []
        data=self.json(query_url('https://openlibrary.org/search.json',params)) or {}
        if not isinstance(data.get('docs',[]),list): raise ProviderError(self.name+': unerwartetes Antwortformat.')
        result=[]
        for doc in data.get('docs',[])[:10]:
            try:
                i10,i13=isbn_pair(doc.get('isbn'))
                record=MetadataRecord(self.name,str(doc['key']),text(doc['title']),[x for x in map(text,doc.get('author_name',[])) if x],
                    text(doc.get('subtitle')),text((doc.get('publisher') or [None])[0]),year((doc.get('publish_year') or [doc.get('first_publish_year')])[0]),
                    text((doc.get('language') or [None])[0]),i10,i13,
                    'https://covers.openlibrary.org/b/id/'+str(doc['cover_i'])+'-M.jpg' if doc.get('cover_i') else None,
                    'https://openlibrary.org'+str(doc['key'])).validate()
                if record.title: result.append(record)
            except (KeyError,TypeError,ProviderError): continue
        return result

    def isbn_edition(self,isbn):
        value=normalize(isbn)
        data=self.json(query_url('https://openlibrary.org/api/books',
             [('bibkeys','ISBN:'+value),('jscmd','data'),('format','json')])) or {}
        item=data.get('ISBN:'+value) if isinstance(data,dict) else None
        if not isinstance(item,dict):return []
        try:
            authors=[text(x.get('name')) for x in item.get('authors',[]) if isinstance(x,dict) and text(x.get('name'))]
            publishers=[text(x.get('name')) for x in item.get('publishers',[]) if isinstance(x,dict) and text(x.get('name'))]
            cover=(item.get('cover') or {}).get('medium')
            source=item.get('url') or item.get('info_url') or 'https://openlibrary.org/isbn/'+quote(value)
            if source:source=re.sub(r'^http:', 'https:', source)
            i10,i13=isbn_pair([value])
            rec=MetadataRecord(self.name,'ISBN:'+value,text(item.get('title')),authors,
                 text(item.get('subtitle')),publishers[0] if publishers else None,
                 year(item.get('publish_date')),None,i10,i13,text(cover),text(source)).validate()
            return [rec]
        except (TypeError,ProviderError):return []


class GoogleBooksProvider(BookMetadataProvider):
    name='Google Books'; hosts=('www.googleapis.com',)
    def __init__(self,api_key='',**kwargs): super().__init__(**kwargs); self.key=api_key.strip()
    def search(self,title=None,author=None,isbn=None,publisher=None):
        terms=[]
        if isbn: terms.append('isbn:'+isbn)
        if title: terms.append('intitle:'+title)
        if author: terms.append('inauthor:'+author)
        if publisher: terms.append('inpublisher:'+publisher)
        if not terms:return []
        params=[('q',' '.join(terms)),('maxResults','10'),('printType','books'),('projection','lite')]
        if self.key: params.append(('key',self.key))
        data=self.json(query_url('https://www.googleapis.com/books/v1/volumes',params)) or {}
        result=[]
        for item in data.get('items',[])[:10]:
            try:
                info=item['volumeInfo']; ids=[x.get('identifier') for x in info.get('industryIdentifiers',[]) if isinstance(x,dict)]
                i10,i13=isbn_pair(ids); images=info.get('imageLinks') or {}; cover=images.get('thumbnail')
                if isbn and (i13 or (to_isbn13(i10) if i10 else None)) != to_isbn13(isbn):continue
                if cover: cover=re.sub(r'^http:', 'https:', cover)
                record=MetadataRecord(self.name,str(item['id']),text(info['title']),[x for x in map(text,info.get('authors',[])) if x],
                    text(info.get('subtitle')),text(info.get('publisher')),year(info.get('publishedDate')),text(info.get('language')),i10,i13,
                    cover,'https://books.google.com/books?id='+quote(str(item['id']))).validate()
                if record.title: result.append(record)
            except (KeyError,TypeError,ProviderError): continue
        return result


class DNBProvider(BookMetadataProvider):
    name='Deutsche Nationalbibliothek'; hosts=('services.dnb.de',)
    def search(self,title=None,author=None,isbn=None,publisher=None):
        clauses=[]
        if isbn: clauses.append('num='+self.cql(isbn))
        if title: clauses.append('tit='+self.cql(title))
        if author: clauses.append('per='+self.cql(author))
        if publisher: clauses.append('vlg='+self.cql(publisher))
        if not clauses:return []
        url=query_url('https://services.dnb.de/sru/dnb',[('version','1.1'),('operation','searchRetrieve'),('query',' and '.join(clauses)),('recordSchema','MARC21-xml'),('maximumRecords','10')])
        raw=self.fetch(url,headers={'Accept':'application/xml'})
        if raw is None:return []
        try: root=ET.fromstring(raw)
        except ET.ParseError: raise ProviderError(self.name+': ungültige XML-Antwort.') from None
        ns='{http://www.loc.gov/MARC21/slim}'
        result=[]
        for record in root.iter(ns+'record'):
            controls={x.attrib.get('tag'):text(x.text) for x in record.findall(ns+'controlfield')}
            fields={}
            for data in record.findall(ns+'datafield'):
                fields.setdefault(data.attrib.get('tag'),[]).append({s.attrib.get('code'):text(s.text) for s in data.findall(ns+'subfield')})
            try:
                title_data=(fields.get('245') or [{}])[0]; title=text(title_data.get('a'))
                authors=[text(x.get('a')) for tag in ('100','700') for x in fields.get(tag,[]) if text(x.get('a'))]
                ids=[x.get('a') for x in fields.get('020',[])]
                i10,i13=isbn_pair(ids); pub=(fields.get('264') or fields.get('260') or [{}])[0]
                if isbn and (i13 or (to_isbn13(i10) if i10 else None)) != to_isbn13(isbn):continue
                rid=controls.get('001') or (i13 or i10)
                rec=MetadataRecord(self.name,rid,title,authors,text(title_data.get('b')),text(pub.get('b')),year(pub.get('c')),None,i10,i13,
                    None,'https://d-nb.info/'+quote(rid)).validate()
                if rec.title:result.append(rec)
            except (TypeError,ProviderError):continue
        return result
    @staticmethod
    def cql(value): return '"'+str(value).replace('\\',' ').replace('"',' ')[:500]+'"'


class CustomJSONProvider(BookMetadataProvider):
    """Configurable HTTPS GET API. Expected response: {items:[normalized records]}."""
    name='Eigener Anbieter'
    def __init__(self,base_url,api_key='',**kwargs):
        parsed=urlsplit(base_url); host=parsed.hostname
        if parsed.scheme!='https' or not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError('Der eigene Anbieter benötigt eine einfache HTTPS-Basis-URL.')
        self.base_url=base_url.rstrip('/'); self.hosts=(host,); self.key=api_key.strip(); super().__init__(**kwargs)
    def search(self,title=None,author=None,isbn=None,publisher=None):
        params=[(k,v) for k,v in (('title',title),('author',author),('isbn',isbn),('publisher',publisher)) if v]
        if not params:return []
        headers={'Authorization':'Bearer '+self.key} if self.key else {}
        raw=self.fetch(query_url(self.base_url,params),headers=headers)
        if raw is None:return []
        try:data=__import__('json').loads(raw.decode())
        except (ValueError,UnicodeError):raise ProviderError(self.name+': ungültige JSON-Antwort.') from None
        result=[]
        for item in data.get('items',[])[:10] if isinstance(data,dict) else []:
            try:
                i10,i13=isbn_pair([item.get('isbn10'),item.get('isbn13')])
                rec=MetadataRecord(self.name,text(item.get('id')),text(item.get('title')),[x for x in map(text,item.get('authors',[])) if x],text(item.get('subtitle')),text(item.get('publisher')),year(item.get('publication_year')),text(item.get('language')),i10,i13,text(item.get('cover_url')),text(item.get('source_url'))).validate()
                result.append(rec)
            except (TypeError,ProviderError):continue
        return result
