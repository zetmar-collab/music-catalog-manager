"""Preview imports and retain bounded, transactional revisions in settings."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from music_catalog_manager.database.store import normalized
from music_catalog_manager.services import playlists


def plan(store, path, root=None, cancel=None, name=None):
    ids, missing = playlists.import_file(store, path, cancel)
    path = Path(path)
    key = normalized(path)
    registry = store.setting('playlist_imports', {})
    pid = registry.get(key)
    with store.connection() as db:
        row = db.execute('SELECT name FROM playlists WHERE id=?', (pid,)).fetchone() if pid else None
        old = [r[0] for r in db.execute('SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position', (pid,))] if row else []
    label = name or (str(path.relative_to(root).with_suffix('')) if root else path.stem)
    return dict(path=str(path), key=key, id=pid if row else None, name=row[0] if row else label,
                old=old, ids=ids, missing=missing, added=sum((Counter(ids)-Counter(old)).values()),
                removed=sum((Counter(old)-Counter(ids)).values()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def remember(db, pid, name, ids):
    row = db.execute("SELECT value FROM settings WHERE key='playlist_revisions'").fetchone()
    records = json.loads(row[0]) if row else {}
    key = str(pid)
    records[key] = (records.get(key, []) + [dict(created=datetime.now(timezone.utc).isoformat(), name=name, ids=ids)])[-10:]
    # Only keep revisions for existing lists.
    existing = {str(r[0]) for r in db.execute('SELECT id FROM playlists')}
    records = {k: v for k, v in records.items() if k in existing}
    db.execute("INSERT OR REPLACE INTO settings VALUES('playlist_revisions',?)", (json.dumps(records),))


def apply(store, item, preserve=False, cancel=None):
    playlists.check_cancel(cancel)
    if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('Playlist source changed. Preview again.')
    ids = list(item['ids'])
    if preserve:
        remaining = Counter(item['old']) - Counter(ids)
        for tid in item['old']:
            if remaining[tid] > 0:
                ids.append(tid)
                remaining[tid] -= 1
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        pid, name = item['id'], item['name']
        if pid is not None:
            old = [r[0] for r in db.execute('SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position', (pid,))]
            row = db.execute('SELECT name FROM playlists WHERE id=?', (pid,)).fetchone()
            if old != item['old'] or not row or row[0] != name:
                raise ValueError('Playlist changed. Preview again.')
            remember(db, pid, name, old)
            db.execute('DELETE FROM playlist_tracks WHERE playlist_id=?', (pid,))
        else:
            base, suffix = name, 2
            while db.execute('SELECT 1 FROM playlists WHERE name=?', (name,)).fetchone():
                name, suffix = f'{base} ({suffix})', suffix + 1
            pid = db.execute('INSERT INTO playlists(name) VALUES(?)', (name,)).lastrowid
        if cancel is not None:
            db.set_progress_handler(lambda: int(cancel.is_set()), 1000)
        db.executemany('INSERT INTO playlist_tracks VALUES(?,?,?)', ((pid, tid, pos) for pos, tid in enumerate(ids)))
        row = db.execute("SELECT value FROM settings WHERE key='playlist_imports'").fetchone()
        registry = json.loads(row[0]) if row else {}
        registry[item['key']] = pid
        db.execute("INSERT OR REPLACE INTO settings VALUES('playlist_imports',?)", (json.dumps(registry),))
        playlists.check_cancel(cancel)
    return dict(path=item['path'], name=name, id=pid, matched=len(ids), missing=item['missing'], error=None)


def revisions(store, pid):
    return store.setting('playlist_revisions', {}).get(str(pid), [])


def restore(store, pid, revision):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT name FROM playlists WHERE id=?', (pid,)).fetchone()
        if not row:
            raise KeyError(pid)
        old = [r[0] for r in db.execute('SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position', (pid,))]
        remember(db, pid, row[0], old)
        existing = {r[0] for r in db.execute('SELECT id FROM tracks')}
        ids = [tid for tid in revision['ids'] if tid in existing]
        db.execute('DELETE FROM playlist_tracks WHERE playlist_id=?', (pid,))
        db.executemany('INSERT INTO playlist_tracks VALUES(?,?,?)', ((pid, tid, pos) for pos, tid in enumerate(ids)))
    return len(ids)
