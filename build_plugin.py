"""Build a clean installable ZIP, independent of Calibre and third-party packages."""
import ast
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def build():
    root = Path(__file__).resolve().parent
    source = root / 'papierbibliothek'
    tree = ast.parse((source / '__init__.py').read_text(encoding='utf-8'))
    version_tuple = next(
        ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'version'
                for target in node.targets)
    )
    version = '.'.join(str(part) for part in version_tuple)
    target = root / 'dist' / ('Papierbibliothek-' + version + '.zip')
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
