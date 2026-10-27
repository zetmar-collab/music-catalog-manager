"""Recorded original files with verified, atomic restoration."""
import json
import os
import shutil
import tempfile
from pathlib import Path

from music_catalog_manager.services.scanner import file_hash


def register(store, track_id, original_path, backup_path):
    if backup_path is None:
        return
    with store.connection() as db:
        db.execute('INSERT INTO audio_backups(track_id,original_path,backup_path,sha256) VALUES(?,?,?,?)',
                   (track_id, str(original_path), str(backup_path), file_hash(backup_path)))


def entries(store):
    with store.connection() as db:
        return [dict(r) for r in db.execute('SELECT b.*,t.path AS current_path FROM audio_backups b LEFT JOIN tracks t ON t.id=b.track_id ORDER BY b.id DESC')]


def restore(store, backup_id):
    from music_catalog_manager.services import metadata
    with store.connection() as db:
        row = db.execute('SELECT b.*,t.path AS current_path FROM audio_backups b LEFT JOIN tracks t ON t.id=b.track_id WHERE b.id=?', (backup_id,)).fetchone()
    if row is None or not row['current_path']:
        raise ValueError('Track is no longer in the library')
    source, target = Path(row['backup_path']), Path(row['current_path'])
    if source.resolve().parent != (store.profile / 'audio-backups').resolve():
        raise ValueError('Backup is outside the profile')
    if file_hash(source) != row['sha256']:
        raise ValueError('Backup checksum mismatch')
    if not target.is_file():
        raise FileNotFoundError(str(target))
    old_stat = target.stat()
    fd, name = tempfile.mkstemp(prefix='.mcm-restore-', suffix=target.suffix, dir=target.parent)
    os.close(fd)
    staged = Path(name)
    try:
        shutil.copy2(source, staged)
        data = metadata.read(staged)
        # Preserve the file being replaced, making restoration reversible too.
        import uuid
        safety = store.profile / 'audio-backups' / (uuid.uuid4().hex + '-' + target.name)
        shutil.copy2(target, safety)
        register(store, row['track_id'], target, safety)
        if target.stat().st_mtime_ns != old_stat.st_mtime_ns or target.stat().st_size != old_stat.st_size:
            raise ValueError('File changed during restore')
        os.replace(staged, target)
        st = target.stat()
        with store.connection() as db:
            db.execute('UPDATE tracks SET tags=?,dirty=0,mtime=?,size=?,sha256=NULL,file_key=? WHERE id=?',
                       (json.dumps(data['tags'], ensure_ascii=False), st.st_mtime_ns, st.st_size, f'{st.st_dev}:{st.st_ino}', row['track_id']))
            db.execute('DELETE FROM artwork WHERE track_id=?', (row['track_id'],))
        if data['image']:
            from music_catalog_manager.services.artwork import cache_image
            cache_image(store, row['track_id'], data['image'])
        store.log('restore_audio', row['track_id'], before=row['backup_path'], after=str(target))
    finally:
        staged.unlink(missing_ok=True)
