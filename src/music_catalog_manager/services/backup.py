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


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        from music_catalog_manager.services.musicbrainz import Cancelled
        raise Cancelled()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stream_digest(stream, cancel=None):
    checksum = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        check_cancel(cancel)
        checksum.update(block)
    return checksum.hexdigest()


def describe(path):
    """Read only bounded manifest metadata for the backup picker (not validation)."""
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo('manifest.json').file_size > 16 * 1024 * 1024:
            raise ValueError('Manifest too large')
        return json.loads(archive.read('manifest.json'))


def validate_database(candidate, staging, cancel=None):
    """Validate against an independently created schema before opening as a Store."""
    from music_catalog_manager.database.store import Store
    with tempfile.TemporaryDirectory(dir=staging) as reference_folder:
        reference = Store(reference_folder)
        with closing(sqlite3.connect(candidate)) as db, reference.connection() as expected:
            if cancel is not None:
                db.set_progress_handler(lambda: int(cancel.is_set()), 1000)
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (1, 2) or db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Invalid SQLite database')
            objects = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            expected_objects = {(r['type'], r['name']) for r in expected.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            if version == 1:
                expected_objects -= {('table', n) for n in ('playlists', 'playlist_tracks', 'audio_backups')}
                expected_objects.discard(('index', 'history_operation'))
            if set(objects) != expected_objects:
                raise ValueError('Invalid database structure')
            for kind, name in expected_objects:
                import re
                def canonical(sql):
                    return re.sub(r'\s+', '', sql or '').replace('"', '').replace('[', '').replace(']', '').casefold()
                actual_sql = db.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0]
                expected_sql = expected.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0]
                if version == 1 and name == 'operation_history':
                    expected_sql = re.sub(r',\s*operation_id\s+TEXT', '', expected_sql, flags=re.I)
                if canonical(actual_sql) != canonical(expected_sql):
                    raise ValueError('Invalid database columns or constraints: ' + name)
                check = 'table_info' if kind == 'table' else 'index_info'
                wanted = [tuple(r) for r in expected.execute(f'PRAGMA {check}("{name}")')]
                if version == 1 and name == 'operation_history':
                    wanted = [r for r in wanted if r[1] != 'operation_id']
                if db.execute(f'PRAGMA {check}("{name}")').fetchall() != wanted:
                    raise ValueError('Invalid database columns or indexes: ' + name)
                if kind == 'table':
                    for pragma in ('foreign_key_list', 'index_list'):
                        wanted = [tuple(r) for r in expected.execute(f'PRAGMA {pragma}("{name}")')]
                        if version == 1 and pragma == 'index_list':
                            wanted = [r for r in wanted if r[1] != 'history_operation']
                        actual = db.execute(f'PRAGMA {pragma}("{name}")').fetchall()
                        # Index sequence numbers can change after dropping an index.
                        if {r[1:] for r in actual} != {r[1:] for r in wanted}:
                            raise ValueError('Invalid database constraints: ' + name)
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Invalid foreign key references')
            for table, fields in {'tracks': ('tags',), 'settings': ('value',),
                                  'operation_history': ('before_data', 'after_data'), 'scan_jobs': ('stats',)}.items():
                for field in fields:
                    for row in db.execute(f'SELECT {field} FROM {table} WHERE {field} IS NOT NULL'):
                        check_cancel(cancel)
                        value = json.loads(row[0])
                        if table == 'tracks' and (not isinstance(value, dict) or any(not isinstance(v, str) for v in value.values())):
                            raise ValueError('Invalid track tags')
            for row in db.execute('SELECT path FROM artwork'):
                if Path(row[0]).name != row[0] or not (staging / 'artwork' / row[0]).is_file():
                    raise ValueError('Invalid artwork reference')


def inspect(path, cancel=None):
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
        if archive.getinfo('manifest.json').file_size > 16 * 1024 * 1024:
            raise ValueError('Manifest too large')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest['schema'] != SCHEMA or 'library.sqlite' not in manifest['files']:
            raise ValueError('Incompatible backup schema')
        if set(names) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Manifest mismatch')
        for name, checksum in manifest['files'].items():
            check_cancel(cancel)
            with archive.open(name) as stream:
                actual = stream_digest(stream, cancel)
            if actual != checksum:
                raise ValueError('Checksum mismatch: ' + name)
            if name.startswith('artwork/') and PurePosixPath(name).stem != actual:
                raise ValueError('Artwork filename does not match content')
            if name.startswith('artwork/'):
                from music_catalog_manager.services.artwork import MAX_BYTES, validate_image
                if archive.getinfo(name).file_size > MAX_BYTES:
                    raise ValueError('Artwork too large')
                validate_image(archive.read(name))
        return manifest


def create(store, destination, cancel=None, progress=None):
    check_cancel(cancel)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=store.profile) as folder:
        snapshot = Path(folder) / 'library.sqlite'
        with store.connection() as db, closing(sqlite3.connect(snapshot)) as out:
            db.backup(out, pages=256, progress=lambda *_: check_cancel(cancel))
        files = {'library.sqlite': snapshot}
        with closing(sqlite3.connect(snapshot)) as db:
            names = [r[0] for r in db.execute('SELECT DISTINCT path FROM artwork')]
        for name in names:
            check_cancel(cancel)
            if Path(name).name != name:
                raise ValueError('Unsafe artwork path')
            files['artwork/' + name] = store.cache / name
        checksums = {}
        for name, path in files.items():
            with path.open('rb') as stream:
                checksums[name] = stream_digest(stream, cancel)
        manifest = {'schema': SCHEMA, 'created': datetime.now(timezone.utc).isoformat(),
                    'audio_included': False, 'files': checksums}
        fd, temp_name = tempfile.mkstemp(suffix='.zip', dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temp_name, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, path in files.items():
                    check_cancel(cancel)
                    with path.open('rb') as source, archive.open(name, 'w', force_zip64=True) as out:
                        for block in iter(lambda: source.read(1024 * 1024), b''):
                            check_cancel(cancel)
                            out.write(block)
                    if progress:
                        progress({'files': len(archive.namelist()), 'total': len(files)})
                archive.writestr('manifest.json', json.dumps(manifest))
            inspect(temp_name, cancel)
            check_cancel(cancel)
            # No overwrite even when a destination appears during backup creation.
            if os.name == 'nt':
                os.rename(temp_name, destination)
            else:
                os.link(temp_name, destination)
        finally:
            Path(temp_name).unlink(missing_ok=True)
    return manifest


def restore(store, path, cancel=None, progress=None):
    manifest = inspect(path, cancel)
    safety = store.profile / ('before-restore-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.zip')
    create(store, safety, cancel, progress)
    with tempfile.TemporaryDirectory(dir=store.profile) as folder:
        staging = Path(folder)
        with zipfile.ZipFile(path) as archive:
            for name in manifest['files']:
                check_cancel(cancel)
                target = staging.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open('wb') as out:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        check_cancel(cancel)
                        out.write(block)
        candidate = staging / 'library.sqlite'
        validate_database(candidate, staging, cancel)
        from music_catalog_manager.database.store import Store
        prepared = Store(staging)
        prepared.mark_availability(cancel=cancel)
        # Cache is content-addressed: adding new images cannot invalidate existing references.
        for image in (staging / 'artwork').glob('*.jpg') if (staging / 'artwork').exists() else []:
            check_cancel(cancel)
            shutil.copy2(image, store.cache / image.name)
        check_cancel(cancel)
        os.replace(candidate, store.path)
    return safety
