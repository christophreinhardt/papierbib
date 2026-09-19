"""Optional read-only smoke test against public metadata endpoints."""
from papierbibliothek.metadata_providers import (
    DNBProvider, LobidProvider, OpenLibraryProvider, ProviderError,
)

isbn = '9783150099001'
for provider in (LobidProvider(), OpenLibraryProvider(), DNBProvider()):
    try:
        rows = provider.get_by_isbn(isbn)
        print(provider.name, 'OK', len(rows),
              rows[0].title if rows else '-', rows[0].isbn13 if rows else '-')
    except ProviderError as exc:
        print(provider.name, 'HANDLED', str(exc))
