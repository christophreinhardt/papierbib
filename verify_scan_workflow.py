"""Live ISBN-to-project smoke test using only a disposable project."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from papierbibliothek.metadata_providers import LobidProvider
from papierbibliothek.metadata_providers.workflow import search_book
from papierbibliothek.models import Book
from papierbibliothek.persistence.project import ProjectStore


with TemporaryDirectory(prefix='papierbibliothek-camera-') as temporary:
    store, project = ProjectStore.create(Path(temporary) / 'Projekt', 'Kameratest')
    book = Book(isbn13='9783150099001')
    project.books.append(book)
    store.save(project)
    result = search_book(
        store, project, book.book_id, [LobidProvider()], Event(),
        lambda message: print(message), auto_apply=True)
    saved = store.load().books[0]
    print('Automatisch übernommen:', result['auto_applied'])
    print('Titel:', saved.title)
    print('Autor:', saved.author)
    print('ISBN:', saved.isbn13)
    if not result['auto_applied'] or not saved.title or not saved.author:
        raise SystemExit('Der automatische Kamera-Metadatenpfad war nicht erfolgreich.')
print('Temporäres Projekt automatisch gelöscht; Calibre-Bibliothek unverändert.')
