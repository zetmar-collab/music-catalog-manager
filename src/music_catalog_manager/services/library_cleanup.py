"""Transactional catalog-only removal. Never delete audio, images or backup files."""
from datetime import datetime
import uuid

from music_catalog_manager.services import backup
from music_catalog_manager.database.store import owner


def summary(store, root_id=None):
    with store.connection() as db:
        if root_id is not None:
            root = db.execute('SELECT path FROM library_roots WHERE id=?', (root_id,)).fetchone()
            if root is None:
                raise KeyError(root_id)
            roots = [dict(r) for r in db.execute('SELECT * FROM library_roots')]
            ids = [str(r['id']) for r in db.execute('SELECT id,path FROM tracks') if owner(r['path'], roots) == root_id]
            where, params = ' WHERE id IN (' + (','.join(ids) or 'NULL') + ')', ()
            scope, folders = root['path'], 1
        else:
            where, params = '', ()
            scope = None
            folders = db.execute('SELECT count(*) FROM library_roots').fetchone()[0]
        counts = db.execute('SELECT count(*),coalesce(sum(dirty),0) FROM tracks' + where, params).fetchone()
        selected = 'SELECT id FROM tracks' + where
        history = db.execute('SELECT count(*) FROM operation_history' + (' WHERE track_id IN (' + selected + ')' if root_id is not None else ''), params).fetchone()[0]
        copies = db.execute('SELECT count(*) FROM audio_backups' + (' WHERE track_id IN (' + selected + ')' if root_id is not None else ''), params).fetchone()[0]
        entries = db.execute('SELECT count(*) FROM playlist_tracks WHERE track_id IN (' + selected + ')', params).fetchone()[0]
        lists = db.execute('SELECT count(*) FROM playlists').fetchone()[0] if root_id is None else 0
        return dict(path=scope, folders=folders, tracks=counts[0], pending=counts[1],
                    playlists=lists, playlist_entries=entries, history=history, audio_backup_records=copies)


def remove(store, root_id=None, cancel=None, progress=None):
    backup.check_cancel(cancel)
    counts = summary(store, root_id)
    prefix = 'before-clear-library' if root_id is None else 'before-remove-folder'
    destination = store.profile / f'{prefix}-{datetime.now():%Y%m%d-%H%M%S-%f}-{uuid.uuid4().hex[:8]}.zip'
    # A failure or cancellation here leaves the catalog untouched.
    backup.create(store, destination, cancel, progress)
    backup.check_cancel(cancel)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if root_id is not None:
            current = db.execute('SELECT path FROM library_roots WHERE id=?', (root_id,)).fetchone()
            if current is None or current['path'] != counts['path']:
                raise ValueError('Folder changed before removal')
        if cancel is not None:
            db.set_progress_handler(lambda: int(cancel.is_set()), 1000)
        if root_id is None:
            for table in ('playlist_tracks', 'playlists', 'artwork', 'audio_backups', 'operation_history',
                          'scan_jobs', 'tracks', 'library_roots'):
                backup.check_cancel(cancel)
                db.execute('DELETE FROM ' + table)
            db.execute("DELETE FROM settings WHERE key IN ('playlist_imports','playlist_revisions','playback_session','library_view','smart_playlists')")
        else:
            # Remove references before tracks: audio_backups intentionally has no cascade.
            store.reconcile_roots(db)
            for table in ('audio_backups', 'operation_history'):
                backup.check_cancel(cancel)
                db.execute(f'DELETE FROM {table} WHERE track_id IN (SELECT id FROM tracks WHERE root_id=?)', (root_id,))
            db.execute('DELETE FROM tracks WHERE root_id=?', (root_id,))
            db.execute('DELETE FROM scan_jobs WHERE root_id=?', (root_id,))
            db.execute('DELETE FROM library_roots WHERE id=?', (root_id,))
        backup.check_cancel(cancel)
    return dict(backup=str(destination), removed=counts)
