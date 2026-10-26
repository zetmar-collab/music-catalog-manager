import importlib.metadata as metadata
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'third_party_licenses'
root.mkdir(exist_ok=True)
inventory = []
for name in ('PySide6-Essentials', 'PySide6-Addons', 'shiboken6', 'mutagen', 'httpx', 'httpcore', 'anyio', 'certifi', 'idna', 'h11', 'Pillow', 'typing_extensions'):
    dist = metadata.distribution(name)
    inventory.append({'name': name, 'version': dist.version, 'license': dist.metadata.get('License-Expression') or dist.metadata.get('License'), 'homepage': dist.metadata.get('Home-page')})
    for file in dist.files or []:
        if any(token in str(file).lower() for token in ('license', 'copying', 'copyright', 'notice')) and str(file).lower().endswith(('.txt', '.md', 'license', 'copying', 'copyright', 'notice')):
            source = Path(dist.locate_file(file))
            if source.is_file():
                destination = root / name / str(file).replace('../', '').replace('..\\', '')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
(root / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
