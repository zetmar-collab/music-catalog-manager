import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / 'dist/MusicCatalogManager-0.2.0-source.zip'
names = ['pyproject.toml', 'requirements-lock.txt', 'MusicCatalogManager.spec', 'README.md', 'ARCHITECTURE.md', 'LICENSE', 'LICENSES.md', 'CHANGELOG.md', '.gitignore']
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in names:
        archive.write(root / name, 'MusicCatalogManager/' + name)
    for directory in ('src', 'tests', 'scripts', 'third_party_licenses', 'docs', 'reports'):
        for path in (root / directory).rglob('*'):
            public_report = directory != 'reports' or path.name in ('IMPLEMENTATION.md', 'PLAYBACK.md', 'pytest.xml', 'packaged-result.json', 'installer-result.json', 'playback-result.json')
            if path.is_file() and public_report and '__pycache__' not in path.parts and '.egg-info' not in str(path) and path.suffix not in ('.pyc', '.log'):
                archive.write(path, 'MusicCatalogManager/' + path.relative_to(root).as_posix())
print(target)
