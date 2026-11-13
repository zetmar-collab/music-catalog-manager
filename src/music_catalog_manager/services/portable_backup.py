"""Streaming, hashed collection archives restored only into a new directory."""
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from music_catalog_manager.database.store import Store, normalized
from music_catalog_manager.paths import windows_path
from music_catalog_manager.services import backup


def safe_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or any(part.rstrip('. ') != part for part in path.parts):
        raise ValueError('Unsafe collection archive path')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if any(part.split('.')[0].upper() in reserved or any(c in part for c in '<>"|?*') or any(ord(c) < 32 for c in part) for part in path.parts):
        raise ValueError('Unsafe Windows archive filename')
    if path.parts[0] not in ('profile', 'music'):
        raise ValueError('Unexpected collection archive entry')
    if path.parts[0] == 'profile' and name != 'profile/library.sqlite' and not (len(path.parts) == 3 and path.parts[1] == 'artwork' and path.suffix == '.jpg'):
        raise ValueError('Unexpected collection profile entry')
    return path


def create(store, destination, cancel=None, progress=None):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=store.profile) as folder:
        folder = Path(folder)
        snapshot = folder / 'library.sqlite'
        with store.connection() as db, closing(sqlite3.connect(snapshot)) as out:
            db.backup(out, pages=256, progress=lambda *_: backup.check_cancel(cancel))
        files = {'profile/library.sqlite': snapshot}
        with closing(sqlite3.connect(snapshot)) as db:
            db.row_factory = sqlite3.Row
            roots = {r['id']: r['path'] for r in db.execute('SELECT * FROM library_roots')}
            tracks = [dict(r) for r in db.execute('SELECT id,root_id,path FROM tracks')]
            for row in db.execute('SELECT DISTINCT path FROM artwork'):
                if Path(row[0]).name != row[0]:
                    raise ValueError('Unsafe artwork path')
                files['profile/artwork/' + row[0]] = store.cache / row[0]
        mapping, missing = {}, []
        for track in tracks:
            backup.check_cancel(cancel)
            source = Path(windows_path(track['path']))
            root = roots.get(track['root_id'])
            try:
                relative = source.relative_to(Path(windows_path(root))) if root else Path(str(track['id'])) / source.name
            except ValueError as exc:
                raise ValueError('Track outside its registered folder') from exc
            name = 'music/' + str(track['root_id'] or 'unassigned') + '/' + relative.as_posix()
            safe_name(name)
            mapping[str(track['id'])] = name
            if source.is_file():
                if source.is_symlink():
                    raise ValueError('Symbolic audio links are not included')
                files[name] = source
            else:
                missing.append(name)
        manifest = dict(kind='mcm-collection', schema=1, created=datetime.now(timezone.utc).isoformat(),
                        roots={str(rid): 'music/' + str(rid) for rid in roots}, tracks=mapping, missing=missing, files={})
        fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix='.zip')
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for index, (name, source) in enumerate(files.items()):
                    backup.check_cancel(cancel)
                    before = source.stat()
                    import hashlib
                    checksum = hashlib.sha256()
                    with source.open('rb') as stream, archive.open(name, 'w', force_zip64=True) as out:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            backup.check_cancel(cancel)
                            out.write(block)
                            checksum.update(block)
                    after = source.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError('File changed during backup: ' + str(source))
                    manifest['files'][name] = checksum.hexdigest()
                    if progress:
                        progress(dict(files=index + 1, total=len(files)))
                archive.writestr('collection.json', json.dumps(manifest))
            backup.check_cancel(cancel)
            if os.name == 'nt':
                os.rename(temporary, destination)
            else:
                os.link(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return manifest


def inspect(path):
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo('collection.json')
        if info.file_size > 64 * 1024 * 1024:
            raise ValueError('Collection manifest too large')
        manifest = json.loads(archive.read(info))
        if manifest.get('kind') != 'mcm-collection' or manifest.get('schema') != 1:
            raise ValueError('Unsupported collection format')
        names = archive.namelist()
        if len(names) > 1_000_000 or len(set(n.casefold() for n in names)) != len(names) or set(names) != set(manifest['files']) | {'collection.json'}:
            raise ValueError('Collection manifest mismatch')
        total = 0
        for item in archive.infolist():
            if item.filename != 'collection.json':
                safe_name(item.filename)
                if item.filename.startswith('profile/artwork/'):
                    if item.file_size > 20 * 1024 * 1024 or PurePosixPath(item.filename).stem != manifest['files'][item.filename]:
                        raise ValueError('Invalid collection artwork')
            total += item.file_size
        for name in [*manifest['roots'].values(), *manifest['tracks'].values()]:
            if safe_name(name).parts[0] != 'music':
                raise ValueError('Invalid audio mapping')
        if 'profile/library.sqlite' not in manifest['files']:
            raise ValueError('Collection database is missing')
        manifest['uncompressed_bytes'] = total
        return manifest


def restore(path, destination, cancel=None, progress=None):
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError('Choose a new folder; existing collections are never overwritten')
    manifest = inspect(path)
    if shutil.disk_usage(destination.parent).free < manifest['uncompressed_bytes'] + 64 * 1024 * 1024:
        raise OSError('Insufficient free disk space')
    with tempfile.TemporaryDirectory(prefix='.mcm-restore-', dir=destination.parent) as folder:
        staging = Path(folder) / 'collection'
        staging.mkdir()
        with zipfile.ZipFile(path) as archive:
            for index, (name, checksum) in enumerate(manifest['files'].items()):
                backup.check_cancel(cancel)
                target = staging.joinpath(*safe_name(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                import hashlib
                digest = hashlib.sha256()
                with archive.open(name) as source, target.open('xb') as out:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        backup.check_cancel(cancel)
                        digest.update(block)
                        out.write(block)
                if digest.hexdigest() != checksum:
                    raise ValueError('Collection checksum mismatch: ' + name)
                if name.startswith('profile/artwork/'):
                    from music_catalog_manager.services.artwork import validate_image
                    validate_image(target.read_bytes())
                if progress:
                    progress(dict(files=index + 1, total=len(manifest['files'])))
        profile = staging / 'profile'
        for name in manifest['roots'].values():
            staging.joinpath(*safe_name(name).parts).mkdir(parents=True, exist_ok=True)
        backup.validate_database(profile / 'library.sqlite', profile, cancel)
        restored = Store(profile)
        with restored.connection() as db:
            roots = {str(r[0]) for r in db.execute('SELECT id FROM library_roots')}
            ids = {str(r[0]) for r in db.execute('SELECT id FROM tracks')}
            if roots != set(manifest['roots']) or ids != set(manifest['tracks']):
                raise ValueError('Incomplete collection mapping')
            for rid, name in manifest['roots'].items():
                db.execute('UPDATE library_roots SET path=? WHERE id=?', (normalized(destination / name), int(rid)))
            for tid, name in manifest['tracks'].items():
                db.execute('UPDATE tracks SET path=?,available=? WHERE id=?',
                           (normalized(destination / name), int((staging / name).is_file()), int(tid)))
            db.execute('DELETE FROM audio_backups')
            db.execute("DELETE FROM settings WHERE key IN ('playback_session','playlist_imports','playlist_revisions')")
            db.execute("INSERT OR REPLACE INTO settings VALUES('watch_folders','false')")
        backup.check_cancel(cancel)
        if destination.exists():
            raise FileExistsError(str(destination))
        os.rename(staging, destination)
    return destination / 'profile'
