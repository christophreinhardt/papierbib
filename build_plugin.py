"""Build a clean installable ZIP, independent of Calibre and third-party packages."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def build():
    root = Path(__file__).resolve().parent
    source = root / 'papierbibliothek'
    target = root / 'dist' / 'Papierbibliothek-0.6.11.zip'
    target.parent.mkdir(exist_ok=True)
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py', '.txt'):
                archive.write(path, path.relative_to(source).as_posix())
        archive.write(root / 'README.md', 'README.md')
    print(target)
    return target


if __name__ == '__main__':
    build()
