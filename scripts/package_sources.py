import zipfile
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = json.loads((root / 'src/music_catalog_manager/resources/release.json').read_text(encoding='utf-8'))['version']
target = root / f'dist/MusicCatalogManager-{version}-source.zip'
names = ['pyproject.toml', 'requirements-lock.txt', 'MusicCatalogManager.spec', 'README.md', 'ARCHITECTURE.md', 'LICENSE', 'LICENSES.md', 'CHANGELOG.md', '.gitignore']
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in names:
        archive.write(root / name, 'MusicCatalogManager/' + name)
    for directory in ('src', 'tests', 'scripts', 'packaging', 'third_party_licenses', 'docs', 'reports', '.github'):
        for path in (root / directory).rglob('*'):
            public_report = directory != 'reports' or path.name in ('IMPLEMENTATION.md', 'PLAYBACK.md', 'UPGRADE-0.3.0.md', 'UPGRADE-0.4.0.md', 'UPGRADE-0.5.0.md', 'UPGRADE-0.5.1.md', 'IMPLEMENTATION-0.6.0.md', 'CODE-AUDIT-2026-11-13.md', 'playlist-benchmark-0.6.0.json', 'packaged-0.6.0.json', 'playback-0.6.0.json', 'pytest-0.6.0.xml', 'installer-0.6.0.json', 'msix-validation-1.6.0.0.json', 'cover-live.json', 'library-benchmark.json', 'ui-review.json', 'pytest.xml', 'packaged-result.json', 'installer-result.json', 'playback-result.json', 'msix-acceptance.json', 'msix-validation-1.5.1.0.json')
            if path.is_file() and public_report and '__pycache__' not in path.parts and '.egg-info' not in str(path) and path.suffix not in ('.pyc', '.log'):
                archive.write(path, 'MusicCatalogManager/' + path.relative_to(root).as_posix())
print(target)
