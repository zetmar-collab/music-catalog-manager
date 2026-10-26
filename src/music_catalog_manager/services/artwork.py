import hashlib
import io
from pathlib import Path

from PIL import Image

MAX_BYTES = 20 * 1024 * 1024


def validate_image(data):
    if len(data) > MAX_BYTES:
        raise ValueError('Image exceeds 20 MB')
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in ('JPEG', 'PNG') or image.width * image.height > 25_000_000:
            raise ValueError('Invalid image format or dimensions')
        image.load()
        output = io.BytesIO()
        image.convert('RGB').save(output, 'JPEG', quality=92)
        return output.getvalue()


def cache_image(store, track_id, data, source='embedded', release_id=None):
    data = validate_image(data)
    name = hashlib.sha256(data).hexdigest() + '.jpg'
    target = store.cache / name
    if not target.exists():
        target.write_bytes(data)
    with store.connection() as db:
        db.execute('INSERT INTO artwork(track_id,path,source,release_id) VALUES(?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET path=excluded.path,source=excluded.source,release_id=excluded.release_id',
                   (track_id, name, source, release_id))
    return target


def folder_image(audio_path, data, overwrite=False):
    path = Path(audio_path).parent / 'folder.jpg'
    mode = 'wb' if overwrite else 'xb'
    with path.open(mode) as out:
        out.write(validate_image(data))
    return path
