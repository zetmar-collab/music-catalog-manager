import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from music_catalog_manager.paths import windows_path, plain_path

FIELDS = ('title', 'artist', 'album', 'albumartist', 'genre', 'date', 'tracknumber', 'discnumber', 'composer', 'comment')


def normalized(path):
    value = os.path.normcase(plain_path(Path(windows_path(path)).resolve()))
    return windows_path(value) if os.name == 'nt' and len(value) >= 240 else value


class Store:
    def __init__(self, profile):
        self.profile = Path(profile)
        self.profile.mkdir(parents=True, exist_ok=True)
        self.cache = self.profile / 'artwork'
        self.cache.mkdir(exist_ok=True)
        self.path = self.profile / 'library.sqlite'
        self.migrate()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.create_function('CASEFOLD', 1, lambda x: (x or '').casefold(), deterministic=True)
        try:
            with db:
                yield db
        finally:
            db.close()

    def migrate(self):
        with self.connection() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise ValueError('Unsupported database schema')
            if version == 0:
                db.executescript('''
                CREATE TABLE library_roots(id INTEGER PRIMARY KEY,path TEXT NOT NULL UNIQUE);
                CREATE TABLE tracks(id INTEGER PRIMARY KEY,root_id INTEGER REFERENCES library_roots(id),
                  path TEXT NOT NULL UNIQUE,size INTEGER,mtime INTEGER,file_key TEXT,sha256 TEXT,
                  format TEXT,duration REAL,bitrate INTEGER,tags TEXT NOT NULL DEFAULT '{}',
                  available INTEGER NOT NULL DEFAULT 1,seen TEXT, dirty INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX track_identity ON tracks(file_key);
                CREATE INDEX track_hash ON tracks(sha256);
                CREATE INDEX track_root ON tracks(root_id);
                CREATE TABLE artwork(id INTEGER PRIMARY KEY,track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
                  path TEXT NOT NULL,source TEXT,release_id TEXT, UNIQUE(track_id));
                CREATE TABLE scan_jobs(id INTEGER PRIMARY KEY,root_id INTEGER REFERENCES library_roots(id),
                  started TEXT DEFAULT CURRENT_TIMESTAMP,finished TEXT,stats TEXT,cancelled INTEGER DEFAULT 0);
                CREATE TABLE operation_history(id INTEGER PRIMARY KEY,kind TEXT,track_id INTEGER,
                  before_data TEXT,after_data TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP,undone INTEGER DEFAULT 0);
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                PRAGMA user_version=1;
                ''')

    def setting(self, key, default=None):
        with self.connection() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))

    def roots(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM library_roots ORDER BY path')]

    def add_root(self, path):
        path = normalized(path)
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO library_roots(path) VALUES(?)', (path,))
            return db.execute('SELECT id FROM library_roots WHERE path=?', (path,)).fetchone()[0]

    def tracks(self):
        with self.connection() as db:
            rows = [dict(r) for r in db.execute('SELECT t.*,a.path AS artwork FROM tracks t LEFT JOIN artwork a ON a.track_id=t.id')]
        for row in rows:
            row['tags'] = json.loads(row['tags'])
        return rows

    def track(self, track_id):
        with self.connection() as db:
            row = db.execute('SELECT t.*,a.path AS artwork FROM tracks t LEFT JOIN artwork a ON a.track_id=t.id WHERE t.id=?', (track_id,)).fetchone()
        if row is None:
            raise KeyError(track_id)
        result = dict(row)
        result['tags'] = json.loads(result['tags'])
        return result

    def edit(self, ids, changes):
        if set(changes) - set(FIELDS) - {'musicbrainz_recordingid', 'musicbrainz_albumid', 'isrc'}:
            raise ValueError('Unknown field')
        with self.connection() as db:
            for tid in ids:
                row = db.execute('SELECT tags FROM tracks WHERE id=?', (tid,)).fetchone()
                before = row[0]
                tags = json.loads(before)
                tags.update(changes)
                after = json.dumps(tags, ensure_ascii=False)
                db.execute('UPDATE tracks SET tags=?,dirty=1 WHERE id=?', (after, tid))
                db.execute('INSERT INTO operation_history(kind,track_id,before_data,after_data) VALUES(?,?,?,?)',
                           ('edit', tid, before, after))

    def undo(self):
        with self.connection() as db:
            row = db.execute("SELECT * FROM operation_history WHERE kind='edit' AND undone=0 ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return False
            db.execute('UPDATE tracks SET tags=?,dirty=1 WHERE id=?', (row['before_data'], row['track_id']))
            db.execute('UPDATE operation_history SET undone=1 WHERE id=?', (row['id'],))
        return True

    def log(self, kind, tid=None, before=None, after=None):
        with self.connection() as db:
            db.execute('INSERT INTO operation_history(kind,track_id,before_data,after_data) VALUES(?,?,?,?)',
                       (kind, tid, json.dumps(before), json.dumps(after)))

    def mark_availability(self):
        with self.connection() as db:
            for row in db.execute('SELECT id,path FROM tracks').fetchall():
                db.execute('UPDATE tracks SET available=? WHERE id=?', (int(Path(row['path']).is_file()), row['id']))

    def relink(self, root_id, new_path):
        new_path = Path(new_path).resolve()
        with self.connection() as db:
            old = Path(db.execute('SELECT path FROM library_roots WHERE id=?', (root_id,)).fetchone()[0])
            rows = db.execute('SELECT id,path FROM tracks WHERE root_id=?', (root_id,)).fetchall()
            for row in rows:
                relative = Path(windows_path(row['path'])).relative_to(Path(windows_path(old)))
                target = Path(windows_path(new_path)) / relative
                db.execute('UPDATE tracks SET path=?,available=? WHERE id=?', (normalized(target), int(target.is_file()), row['id']))
            db.execute('UPDATE library_roots SET path=? WHERE id=?', (normalized(new_path), root_id))
