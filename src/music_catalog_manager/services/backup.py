import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA = 1


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 100_000:
            raise ValueError('Duplicate archive entries or too many files')
        total = 0
        for item in archive.infolist():
            p = PurePosixPath(item.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in item.filename or ':' in item.filename:
                raise ValueError('Unsafe archive path')
            if item.filename != 'manifest.json' and item.filename != 'library.sqlite' and not (len(p.parts) == 2 and p.parts[0] == 'artwork' and p.suffix == '.jpg'):
                raise ValueError('Unexpected archive entry')
            total += item.file_size
            if item.file_size > 512 * 1024 * 1024 or total > 2 * 1024**3:
                raise ValueError('Archive too large')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest['schema'] != SCHEMA or 'library.sqlite' not in manifest['files']:
            raise ValueError('Incompatible backup schema')
        if set(names) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Manifest mismatch')
        for name, checksum in manifest['files'].items():
            data = archive.read(name)
            if digest(data) != checksum:
                raise ValueError('Checksum mismatch: ' + name)
            if name.startswith('artwork/') and PurePosixPath(name).stem != digest(data):
                raise ValueError('Artwork filename does not match content')
        return manifest


def create(store, destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=store.profile) as folder:
        snapshot = Path(folder) / 'library.sqlite'
        with store.connection() as db, closing(sqlite3.connect(snapshot)) as out:
            db.backup(out)
        files = {'library.sqlite': snapshot.read_bytes()}
        for path in store.cache.glob('*.jpg'):
            files['artwork/' + path.name] = path.read_bytes()
        manifest = {'schema': SCHEMA, 'created': datetime.now(timezone.utc).isoformat(),
                    'audio_included': False, 'files': {name: digest(data) for name, data in files.items()}}
        fd, temp_name = tempfile.mkstemp(suffix='.zip', dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temp_name, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
                archive.writestr('manifest.json', json.dumps(manifest))
            inspect(temp_name)
            # No overwrite even when a destination appears during backup creation.
            if os.name == 'nt':
                os.rename(temp_name, destination)
            else:
                os.link(temp_name, destination)
        finally:
            Path(temp_name).unlink(missing_ok=True)
    return manifest


def restore(store, path):
    manifest = inspect(path)
    safety = store.profile / ('before-restore-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.zip')
    create(store, safety)
    with tempfile.TemporaryDirectory(dir=store.profile) as folder:
        staging = Path(folder)
        with zipfile.ZipFile(path) as archive:
            for name in manifest['files']:
                target = staging.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        candidate = staging / 'library.sqlite'
        with closing(sqlite3.connect(candidate)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA:
                raise ValueError('Invalid SQLite database')
            expected = {'tracks', 'library_roots', 'settings', 'artwork', 'scan_jobs', 'operation_history'}
            actual = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not expected <= actual or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Invalid database structure')
            for row in db.execute('SELECT path FROM artwork'):
                if Path(row[0]).name != row[0] or not (staging / 'artwork' / row[0]).is_file():
                    raise ValueError('Invalid artwork reference')
        # Cache is content-addressed: adding new images cannot invalidate existing references.
        for image in (staging / 'artwork').glob('*.jpg') if (staging / 'artwork').exists() else []:
            shutil.copy2(image, store.cache / image.name)
        os.replace(candidate, store.path)
    store.mark_availability()
    return safety
