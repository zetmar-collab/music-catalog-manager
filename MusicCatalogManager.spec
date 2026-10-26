# PyInstaller one-directory bundle: Qt DLLs remain replaceable.
from pathlib import Path
import PySide6
root = Path(SPECPATH)
qt = Path(PySide6.__file__).parent
# Keep one compatible CRT version at the root and in the Qt directories.
crt = [(str(p), '.') for pattern in ('vcruntime140*.dll', 'msvcp140*.dll', 'concrt140.dll') for p in qt.glob(pattern)]
a = Analysis(['scripts/entry.py'], pathex=[str(root / 'src')],
    binaries=crt,
    datas=[('src/music_catalog_manager/resources', 'music_catalog_manager/resources'),
           ('src/music_catalog_manager/translations', 'music_catalog_manager/translations'),
           ('LICENSE', '.'), ('LICENSES.md', '.'), ('README.md', '.'), ('third_party_licenses', 'third_party_licenses')],
    hiddenimports=['mutagen.mp3', 'mutagen.flac', 'mutagen.mp4', 'mutagen.oggvorbis', 'mutagen.oggopus',
                   'mutagen.wave', 'mutagen.asf', 'mutagen.aiff'],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQml', 'PySide6.QtQuick', 'tkinter'],
    noarchive=False)
# Qt 6.12 uses the Windows ICU API. A foreign icuuc.dll (e.g. from Poppler on
# PATH) exposes version-suffixed symbols and breaks QtCore at startup.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in ('icuuc.dll', 'icudt78.dll')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MusicCatalogManager',
    debug=False, strip=False, upx=False, console=False,
    icon='src/music_catalog_manager/resources/icon.ico')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MusicCatalogManager')
