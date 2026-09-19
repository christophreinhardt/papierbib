"""Bounded ISBN lookup of structured lobid JSON, no scraping or other providers."""
import json
import re
import socket
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .isbn import canonical, isbn10, valid

ENDPOINT = 'https://lobid.org/resources/search'


class ProviderError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def many(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def texts(value):
    result = []
    for item in many(value):
        if isinstance(item, dict):
            item = item.get('label') or item.get('name')
        if isinstance(item, str) and item.strip():
            result.append(' '.join(item.split())[:500])
    return list(dict.fromkeys(result))


def first(value):
    return next(iter(texts(value)), None)


def parse(data, wanted):
    if not isinstance(data, dict) or not isinstance(data.get('member'), list):
        raise ProviderError('lobid hat kein gültiges Ergebnisformat geliefert.')
    wanted = canonical(wanted)
    result, seen = [], set()
    for entry in data['member'][:10]:
        if not isinstance(entry, dict):
            continue
        numbers = [canonical(x) for x in many(entry.get('isbn')) if isinstance(x, str) and valid(x)]
        if wanted not in numbers or not first(entry.get('title')):
            continue
        authors, editors = [], []
        for contribution in many(entry.get('contribution')):
            if not isinstance(contribution, dict):
                continue
            roles = {str(r.get('id', '')).rsplit('/', 1)[-1] for r in many(contribution.get('role')) if isinstance(r, dict)}
            names = texts(contribution.get('agent'))
            target = authors if 'aut' in roles else editors if 'edt' in roles else None
            if target is not None:
                target.extend(names)
        publications = [x for x in many(entry.get('publication')) if isinstance(x, dict)]
        # Keep publisher/year from the same publication statement.
        publication = next((x for x in publications if x.get('publishedBy')), publications[0] if publications else {})
        date = first(publication.get('startDate')) or first(publication.get('dateStatement')) or ''
        year = re.search(r'(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)', date)
        language = next(iter(many(entry.get('language'))), {})
        language = str(language.get('id', '')).rsplit('/', 1)[-1] if isinstance(language, dict) else None
        url = str(entry.get('id') or '').removesuffix('#!')
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        url = 'https://lobid.org' + parsed.path if parsed.hostname == 'lobid.org' and parsed.path.startswith('/resources/') else None
        record = dict(title=first(entry.get('title')), subtitle=first(entry.get('otherTitleInformation')),
                      authors=list(dict.fromkeys(authors)), editors=list(dict.fromkeys(editors)),
                      publisher=first(publication.get('publishedBy')), publication_place=first(publication.get('location')),
                      publication_year=int(year[0]) if year else None, language=language or None,
                      edition=first(entry.get('edition')), extent=first(entry.get('extent')),
                      isbn13=wanted, isbn10=isbn10(wanted), source='lobid-resources', source_url=url,
                      fetched_at=datetime.now(timezone.utc).isoformat())
        # Do not combine different editions/years merely because an ISBN is shared.
        key = tuple(str(record[k]) for k in ('title','authors','editors','publisher','publication_year','edition'))
        if key not in seen:
            result.append(record)
            seen.add(key)
    return result


def lookup(value, timeout=12):
    value = canonical(value)
    variants = [value] + ([isbn10(value)] if isbn10(value) else [])
    query = ' OR '.join('isbn:' + number for number in variants)
    url = ENDPOINT + '?' + urlencode({'q': query, 'format': 'json', 'size': 10})
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Papierbibliothek-Mobile/0.3.0'})
    try:
        deadline = time.monotonic() + timeout
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if 'json' not in response.headers.get('Content-Type', ''):
                raise ProviderError('lobid liefert derzeit keine JSON-Daten (möglicherweise Zugriffsschutz). ISBN kann trotzdem gespeichert werden.')
            chunks, size = [], 0
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError()
                chunk = response.read1(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > 2_000_000:
                    raise ProviderError('lobid-Antwort überschreitet das Größenlimit.')
                chunks.append(chunk)
            return parse(json.loads(b''.join(chunks)), value)
    except HTTPError as exc:
        raise ProviderError('lobid ist derzeit nicht erreichbar (HTTP %s). ISBN kann trotzdem gespeichert werden.' % exc.code) from exc
    except (URLError, socket.timeout, TimeoutError, OSError, ValueError, RecursionError) as exc:
        raise ProviderError('lobid-Abfrage fehlgeschlagen. ISBN kann trotzdem gespeichert werden.') from exc
