import hashlib
import io
import os
import tempfile
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
    image = validate_image(data)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.jpg')
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(image)
            out.flush()
            os.fsync(out.fileno())
        if overwrite:
            os.replace(temporary, path)
        elif os.name == 'nt':
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path
