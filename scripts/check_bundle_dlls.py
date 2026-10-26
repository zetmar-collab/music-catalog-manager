"""Read-only PE import/export diagnostic (requires build dependency pefile)."""
import os
from pathlib import Path
import pefile

root = Path(__file__).resolve().parents[1] / 'dist/MusicCatalogManager/_internal'
paths = list(root.rglob('*.dll')) + list(root.rglob('*.pyd'))
exports = {}
for path in paths:
    try:
        pe = pefile.PE(str(path), fast_load=True, max_symbol_exports=100000)
        pe.parse_data_directories(directories=[0])
        exports.setdefault(path.name.lower(), set()).update(e.name for e in getattr(pe, 'DIRECTORY_ENTRY_EXPORT', type('Empty', (), {'symbols': []})()).symbols)
    except pefile.PEFormatError:
        continue
for path in paths:
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(directories=[1])
        for lib in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
            name = lib.dll.decode().lower()
            if name not in exports:
                continue
            missing = [entry.name.decode() for entry in lib.imports if entry.name and entry.name not in exports[name]]
            if missing:
                print(path.relative_to(root), 'requires', name, missing)
    except pefile.PEFormatError:
        continue
