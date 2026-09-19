from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import re
import socket
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from ..isbn import normalize, valid, to_isbn13


class ProviderError(ValueError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def text(value):
    if not isinstance(value, str): return None
    value = ''.join(character for character in value if not unicodedata.category(character).startswith('C'))
    value = ' '.join(value.split()).strip(' /,;')
    return value[:2000] or None


def year(value):
    match = re.search(r'(?<!\d)(1[0-9]{3}|20[0-9]{2}|2100)(?!\d)', str(value or ''))
    return int(match.group(1)) if match else None


def isbn_pair(values):
    i10 = i13 = None
    for item in values or []:
        candidates=[normalize(item)]
        if isinstance(item,str):
            candidates.extend(normalize(part) for part in re.findall(r'[0-9Xx][0-9Xx\s-]{8,30}[0-9Xx]',item))
        for value in candidates:
            if valid(value):
                if len(value) == 10: i10 = i10 or value
                else: i13 = i13 or value
    if i10 and not i13: i13 = to_isbn13(i10)
    return i10, i13


@dataclass
class MetadataRecord:
    provider: str
    provider_id: str
    title: str
    authors: list = field(default_factory=list)
    subtitle: str | None = None
    publisher: str | None = None
    publication_year: int | None = None
    language: str | None = None
    isbn10: str | None = None
    isbn13: str | None = None
    cover_url: str | None = None
    source_url: str | None = None
    retrieved_at: str = field(default_factory=timestamp)

    def validate(self):
        if not all(isinstance(x, str) and x for x in (self.provider, self.provider_id, self.title, self.retrieved_at)):
            raise ProviderError('Ein Online-Treffer enthält unvollständige Pflichtangaben.')
        if not isinstance(self.authors, list) or any(not isinstance(x, str) or not x for x in self.authors):
            raise ProviderError('Ein Online-Treffer enthält ungültige Autorendaten.')
        for key in ('isbn10', 'isbn13'):
            value = getattr(self, key)
            if value and not valid(value): raise ProviderError('Eine Quelle lieferte eine ungültige ISBN.')
        if self.publication_year is not None and not 1 <= self.publication_year <= 2100:
            raise ProviderError('Eine Quelle lieferte ein ungültiges Erscheinungsjahr.')
        for url in (self.cover_url, self.source_url):
            if url and urlsplit(url).scheme != 'https': raise ProviderError('Unsichere URL in Metadaten verworfen.')
        return self

    def to_dict(self):
        self.validate()
        return asdict(self)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


class BookMetadataProvider(ABC):
    name = ''
    hosts = ()

    def __init__(self, timeout=15, transport=None):
        self.timeout = timeout
        self.transport = transport or build_opener(NoRedirect()).open

    @abstractmethod
    def search(self, title=None, author=None, isbn=None, publisher=None): ...

    def get_by_isbn(self, isbn):
        return self.search(isbn=isbn)

    def fetch(self, url, headers=None, maximum=2*1024*1024):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in self.hosts or parsed.username or parsed.password:
            raise ProviderError('Unsicherer oder nicht erlaubter Anbieter-Endpunkt.')
        request = Request(url, headers={'User-Agent':'Papierbibliothek-Calibre/0.4 (+local plugin)', 'Accept':'application/json, application/xml;q=0.9', **(headers or {})})
        try:
            with self.transport(request, timeout=self.timeout) as response:
                raw = response.read(maximum+1)
            if len(raw) > maximum: raise ProviderError('Antwort des Metadatenanbieters ist zu groß.')
            return raw
        except HTTPError as exc:
            code = exc.code; exc.close()
            if code == 404: return None
            if code == 429: raise ProviderError(self.name + ': Anfragelimit erreicht. Bitte später erneut versuchen.') from None
            raise ProviderError(self.name + ': Dienst antwortet mit HTTP ' + str(code) + '.') from None
        except (URLError, OSError, socket.timeout):
            raise ProviderError(self.name + ': Netzwerk- oder Zeitüberschreitungsfehler.') from None

    def json(self, url):
        raw = self.fetch(url)
        if raw is None: return None
        try: return json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeError, RecursionError): raise ProviderError(self.name + ': ungültige JSON-Antwort.') from None


def query_url(base, values):
    return base + '?' + urlencode([(k, v) for k, v in values if v is not None])
