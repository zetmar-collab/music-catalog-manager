import hashlib
import json
import os
import stat
import uuid
from pathlib import Path
from threading import Event

from music_catalog_manager.database.store import normalized, owner
from music_catalog_manager.paths import windows_path
from music_catalog_manager.services import metadata
from music_catalog_manager.services.artwork import cache_image


def file_hash(path, cancel=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            if cancel is not None and cancel.is_set():
                from music_catalog_manager.services.musicbrainz import Cancelled
                raise Cancelled()
            h.update(block)
    return h.hexdigest()


def scan(store, root_id, cancel=None, progress=None, hashes=False, folders=None):
    cancel = cancel or Event()
    progress = progress or (lambda stats: None)
    roots = store.roots()
    root = next(r for r in roots if r['id'] == root_id)
    scopes = [Path(windows_path(normalized(p))) for p in folders] if folders is not None else [Path(windows_path(root['path']))]
    if any(not p.is_relative_to(Path(windows_path(root['path']))) for p in scopes):
        raise ValueError('Scan scope outside registered root')
    stats = dict(scanned=0, new=0, changed=0, skipped=0, errors=0)
    token = uuid.uuid4().hex
    with store.connection() as db:
        job = db.execute('INSERT INTO scan_jobs(root_id) VALUES(?)', (root_id,)).lastrowid

    def error(exc):
        stats['errors'] += 1
        store.log('scan_error', after=str(exc))

    if not Path(root['path']).is_dir():
        with store.connection() as db:
            db.execute('UPDATE tracks SET available=0 WHERE root_id=?', (root_id,))
    else:
        def walks():
            for scope in scopes:
                if scope.is_symlink() or scope.is_junction():
                    continue
                yield from os.walk(scope, followlinks=False, onerror=error)
        for folder, dirs, files in walks():
            dirs[:] = [d for d in dirs if not Path(folder, d).is_symlink() and not Path(folder, d).is_junction()]
            if cancel.is_set():
                break
            for name in files:
                if cancel.is_set():
                    break
                path = Path(folder, name)
                if path.suffix.lower() not in metadata.EXTENSIONS or path.is_symlink():
                    continue
                stats['scanned'] += 1
                try:
                    st = path.stat()
                    identity = f'{st.st_dev}:{st.st_ino}' if st.st_ino else None
                    norm = normalized(path)
                    owner_id = owner(norm, roots)
                    with store.connection() as db:
                        row = db.execute('SELECT * FROM tracks WHERE path=?', (norm,)).fetchone()
                        if not row and identity:
                            candidates = db.execute('SELECT * FROM tracks WHERE file_key=? AND size=? AND mtime=?', (identity, st.st_size, st.st_mtime_ns)).fetchall()
                            missing = [r for r in candidates if not Path(r['path']).exists()]
                            if len(missing) == 1:
                                row = missing[0]
                        if row and row['mtime'] == st.st_mtime_ns and row['size'] == st.st_size and all(k in json.loads(row['tags']) for k in metadata.REPLAYGAIN_FIELDS):
                            db.execute('UPDATE tracks SET path=?,root_id=?,seen=?,available=1 WHERE id=?', (norm, owner_id, token, row['id']))
                            if hashes and not row['sha256']:
                                db.execute('UPDATE tracks SET sha256=? WHERE id=?', (file_hash(path, cancel), row['id']))
                            stats['skipped'] += 1
                            progress(stats.copy())
                            continue
                    data = metadata.read(path)
                    digest = file_hash(path, cancel) if hashes else None
                    with store.connection() as db:
                        if not row and digest:
                            candidates = db.execute('SELECT * FROM tracks WHERE sha256=?', (digest,)).fetchall()
                            missing = [r for r in candidates if not Path(r['path']).exists()]
                            if len(missing) == 1:
                                row = missing[0]
                        if row and row['dirty']:
                            pending = json.loads(row['tags'])
                            pending.update({key: data['tags'].get(key, '') for key in metadata.REPLAYGAIN_FIELDS})
                            tags = json.dumps(pending, ensure_ascii=False)
                        else:
                            tags = json.dumps(data['tags'], ensure_ascii=False)
                        values = (owner_id, norm, st.st_size, st.st_mtime_ns, identity, digest, data['format'], data['duration'], data['bitrate'], tags, token)
                        if row:
                            db.execute('UPDATE tracks SET root_id=?,path=?,size=?,mtime=?,file_key=?,sha256=?,format=?,duration=?,bitrate=?,tags=?,seen=?,available=1 WHERE id=?', values + (row['id'],))
                            tid = row['id']
                            stats['changed'] += 1
                        else:
                            tid = db.execute('INSERT INTO tracks(root_id,path,size,mtime,file_key,sha256,format,duration,bitrate,tags,seen) VALUES(?,?,?,?,?,?,?,?,?,?,?)', values).lastrowid
                            stats['new'] += 1
                    if data['image']:
                        try:
                            cache_image(store, tid, data['image'])
                        except Exception as exc:
                            error(exc)
                except Exception as exc:
                    if cancel.is_set():
                        break
                    error(exc)
                progress(stats.copy())
        if not cancel.is_set():
            # Verify existence individually: unreadable folders must not mark known files as deleted.
            for registered in roots:
                if Path(registered['path']).is_relative_to(Path(root['path'])):
                    store.mark_availability(registered['id'], cancel, scopes if folders is not None else None)
    with store.connection() as db:
        db.execute('UPDATE scan_jobs SET finished=CURRENT_TIMESTAMP,stats=?,cancelled=? WHERE id=?', (json.dumps(stats), int(cancel.is_set()), job))
    return stats
