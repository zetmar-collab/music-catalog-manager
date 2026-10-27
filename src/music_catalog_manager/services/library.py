"""Bounded SQLite queries used by the library, album browser and reports."""
import json

from music_catalog_manager.database.store import FIELDS

MISSING = "(coalesce(json_extract(t.tags,'$.title'),'')='' OR coalesce(json_extract(t.tags,'$.artist'),'')='' OR coalesce(json_extract(t.tags,'$.album'),'')='')"
STATUS = f"CASE WHEN t.available=0 THEN 0 WHEN t.dirty=1 THEN 1 WHEN {MISSING} THEN 2 ELSE 3 END"
KEYS = {k: f"coalesce(json_extract(t.tags,'$.{k}'),'')" for k in FIELDS}
KEYS.update({k: f't.{k}' for k in ('path', 'format', 'duration', 'root_id')})
KEYS['status'] = STATUS
KEYS['album_identity'] = "coalesce(nullif(json_extract(t.tags,'$.albumartist'),''),json_extract(t.tags,'$.artist'),'')"
KEYS['playlist_position'] = 'pt.position'


class Library:
    def __init__(self, store):
        self.store = store

    def where(self, query='', filters=None, quick='', duplicates=False, playlist=None):
        terms, params = [], []
        if query.strip():
            terms.append("instr(CASEFOLD(t.path || ' ' || (SELECT coalesce(group_concat(value,' '),'') FROM json_each(t.tags))),?)>0")
            params.append(query.strip().casefold())
        for key, value in (filters or {}).items():
            if key not in KEYS or key == 'playlist_position':
                raise ValueError('Unknown filter')
            if value != '' and value is not None:
                terms.append(f'CASEFOLD(CAST({KEYS[key]} AS TEXT))=?')
                params.append(str(value).casefold())
        if quick == 'missing':
            terms.append(MISSING)
        elif quick == 'pending':
            terms.append('t.dirty=1')
        elif quick == 'unavailable':
            terms.append('t.available=0')
        elif quick == 'artwork':
            terms.append('a.path IS NULL')
        if duplicates:
            terms.append('t.sha256 IN (SELECT sha256 FROM tracks WHERE sha256 IS NOT NULL GROUP BY sha256 HAVING COUNT(*)>1)')
        if playlist is not None:
            terms.append('t.id IN (SELECT track_id FROM playlist_tracks WHERE playlist_id=?)')
            params.append(playlist)
        return (' WHERE ' + ' AND '.join(terms)) if terms else '', params

    def page(self, query='', filters=None, quick='', duplicates=False, playlist=None,
             sort='title', descending=False, offset=0, limit=250, cancel=None):
        if sort not in KEYS or limit < 1 or limit > 1000 or offset < 0:
            raise ValueError('Invalid page')
        where, params = self.where(query, filters, quick, duplicates, playlist)
        base = ' FROM tracks t LEFT JOIN artwork a ON a.track_id=t.id'
        if playlist is not None:
            base += ' JOIN playlist_tracks pt ON pt.track_id=t.id AND pt.playlist_id=?'
            params = [playlist, *params]
        elif sort == 'playlist_position':
            sort = 'title'
        key = KEYS[sort]
        if sort in ('tracknumber', 'discnumber'):
            key = f'CAST({key} AS INTEGER)'
        elif sort not in ('duration', 'status', 'playlist_position'):
            key = f'CASEFOLD(CAST({key} AS TEXT))'
        with self.store.connection() as db:
            if cancel is not None:
                db.set_progress_handler(lambda: int(cancel.is_set()), 1000)
            count = db.execute('SELECT count(*)' + base + where, params).fetchone()[0]
            rows = [dict(r) for r in db.execute('SELECT t.*,a.path AS artwork' + base + where + f" ORDER BY {key} {'DESC' if descending else 'ASC'},t.id LIMIT ? OFFSET ?", [*params, limit, offset])]
        for row in rows:
            row['tags'] = json.loads(row['tags'])
        return rows, count

    def all(self, cancel=None, **options):
        offset = 0
        while True:
            if cancel is not None and cancel.is_set():
                from music_catalog_manager.services.musicbrainz import Cancelled
                raise Cancelled()
            rows, count = self.page(**options, offset=offset, limit=1000, cancel=cancel)
            yield from rows
            offset += len(rows)
            if not rows or offset >= count:
                return

    def facets(self, cancel=None):
        with self.store.connection() as db:
            if cancel is not None:
                db.set_progress_handler(lambda: int(cancel.is_set()), 1000)
            return {key: [r[0] for r in db.execute(f"SELECT DISTINCT CAST({KEYS[key]} AS TEXT) AS value FROM tracks t WHERE {KEYS[key]} IS NOT NULL AND {KEYS[key]} != '' ORDER BY CASEFOLD(value)")]
                    for key in ('artist', 'album', 'genre', 'date', 'format', 'root_id')}

    def albums(self):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute("""
                SELECT coalesce(nullif(json_extract(t.tags,'$.albumartist'),''),json_extract(t.tags,'$.artist'),'') AS artist,
                  coalesce(json_extract(t.tags,'$.album'),'') AS album,count(*) AS tracks,
                  sum(t.duration) AS duration,min(a.path) AS artwork
                FROM tracks t LEFT JOIN artwork a ON a.track_id=t.id
                GROUP BY CASEFOLD(artist),CASEFOLD(album) ORDER BY CASEFOLD(artist),CASEFOLD(album)
                """)]

    def folders(self):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute('''SELECT r.id,r.path,count(t.id) AS tracks,
                coalesce(sum(t.available),0) AS available,
                (SELECT max(finished) FROM scan_jobs WHERE root_id=r.id) AS scanned
                FROM library_roots r LEFT JOIN tracks t ON t.root_id=r.id GROUP BY r.id''')]
