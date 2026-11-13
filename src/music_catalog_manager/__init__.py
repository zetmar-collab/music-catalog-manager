import json
from pathlib import Path

RELEASE = json.loads((Path(__file__).parent / 'resources' / 'release.json').read_text(encoding='utf-8'))
__version__ = RELEASE['version']
