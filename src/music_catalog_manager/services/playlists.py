"""Ordered playlists and portable UTF-8 M3U exchange."""
import os
import configparser
import locale
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit
from music_catalog_manager.database.store import normalized

EXTENSIONS = {'.m3u', '.m3u8', '.pls', '.wpl', '.xspf'}
MAX_BYTES = 8 * 1024 * 1024


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        from music_catalog_manager.services.musicbrainz import Cancelled
        raise Cancelled()


def lists(store):
    with store.connection() as db:
        return [dict(r) for r in db.execute('SELECT p.id,p.name,count(pt.track_id) AS tracks FROM playlists p LEFT JOIN playlist_tracks pt ON pt.playlist_id=p.id GROUP BY p.id ORDER BY p.name')]


def save(store, name, ids, playlist_id=None):
    name = name.strip()
    if not name:
        raise ValueError('Playlist name is required')
    with store.connection() as db:
        if playlist_id is None:
            playlist_id = db.execute('INSERT INTO playlists(name) VALUES(?)', (name,)).lastrowid
        else:
            db.execute('UPDATE playlists SET name=? WHERE id=?', (name, playlist_id))
            db.execute('DELETE FROM playlist_tracks WHERE playlist_id=?', (playlist_id,))
        for position, tid in enumerate(ids):
            db.execute('INSERT INTO playlist_tracks VALUES(?,?,?)', (playlist_id, tid, position))
    return playlist_id


def tracks(store, playlist_id):
    with store.connection() as db:
        ids = [r[0] for r in db.execute('SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position', (playlist_id,))]
    return [store.track(tid) for tid in ids]


def remove(store, playlist_id):
    with store.connection() as db:
        db.execute('DELETE FROM playlists WHERE id=?', (playlist_id,))
        row = db.execute("SELECT value FROM settings WHERE key='playlist_imports'").fetchone()
        if row:
            registry = {path: pid for path, pid in json.loads(row[0]).items() if pid != playlist_id}
            db.execute("UPDATE settings SET value=? WHERE key='playlist_imports'", (json.dumps(registry),))


def export_m3u(path, rows):
    path = Path(path)
    lines = ['#EXTM3U']
    for row in rows:
        title = (row['tags'].get('artist', '') + ' - ' + row['tags'].get('title', '')).replace('\n', ' ').replace('\r', ' ')
        lines.append(f"#EXTINF:{int(row['duration'] or 0)},{title}")
        try:
            location = os.path.relpath(row['path'], path.parent)
        except ValueError:
            location = row['path']
        if '\n' in location or '\r' in location:
            raise ValueError('Invalid playlist path')
        lines.append(location)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def import_m3u(store, path):
    return import_file(store, path)


def locations(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Playlist exceeds 8 MiB')
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError('Playlist exceeds 8 MiB')
    suffix = path.suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValueError('Unsupported playlist format')
    if suffix in ('.wpl', '.xspf'):
        if b'<!DOCTYPE' in data.replace(b'\x00', b'').upper() or b'<!ENTITY' in data.replace(b'\x00', b'').upper():
            raise ValueError('XML entities are not allowed')
        # Reject entity declarations in UTF-16 documents as well.
        probe = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig', errors='replace').upper()
        if '<!DOCTYPE' in probe or '<!ENTITY' in probe:
            raise ValueError('XML entities are not allowed')
        root = ET.fromstring(data)
        return [node.attrib['src'] for node in root.iter() if node.tag.rsplit('}', 1)[-1] == 'media' and 'src' in node.attrib] if suffix == '.wpl' else [node.text.strip() for node in root.iter() if node.tag.rsplit('}', 1)[-1] == 'location' and node.text and node.text.strip()]
    try:
        text = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode(locale.getencoding() if os.name == 'nt' else 'cp1250')
    if suffix == '.pls':
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(text)
        section = next((s for s in parser.sections() if s.casefold() == 'playlist'), None)
        if section is None:
            raise ValueError('Missing PLS playlist section')
        items = [(int(k[4:]), v) for k, v in parser.items(section) if re.fullmatch(r'file\d+', k)]
        return [v for _, v in sorted(items)]
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('#')]


def import_file(store, path, cancel=None):
    path = Path(path)
    ids, missing = [], []
    with store.connection() as db:
        for line in locations(path):
            check_cancel(cancel)
            if line.lower().startswith('file:'):
                parsed = urlsplit(line)
                if os.name == 'nt' and unquote(parsed.netloc) == '?':
                    line = '\\\\?\\' + unquote(parsed.path).lstrip('/').replace('/', '\\')
                elif parsed.netloc and parsed.netloc.lower() != 'localhost':
                    line = '//' + parsed.netloc + unquote(parsed.path)
                else:
                    line = unquote(parsed.path)
                    if os.name == 'nt' and re.match(r'^/[A-Za-z]:/', line):
                        line = line[1:]
            if '://' in line:
                missing.append(line)
                continue
            target = Path(line)
            if not target.is_absolute():
                target = path.parent / target
            row = db.execute('SELECT id FROM tracks WHERE path=?', (normalized(target),)).fetchone()
            if row:
                ids.append(row[0])
            else:
                missing.append(line)
    return ids, missing


def discover(root, cancel=None, progress=None):
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    paths, errors = [], []
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=lambda exc: errors.append(str(exc))):
        check_cancel(cancel)
        dirs[:] = sorted(d for d in dirs if not Path(folder, d).is_symlink() and not Path(folder, d).is_junction())
        for name in sorted(files):
            path = Path(folder, name)
            if path.suffix.lower() in EXTENSIONS and not path.is_symlink():
                paths.append(path)
        if progress:
            progress({'playlists': len(paths)})
    return paths, errors


def import_files(store, paths, root=None, cancel=None, progress=None, names=None):
    """Reimport updates lists identified by source path; unrelated names are preserved."""
    result = []
    for index, path in enumerate(paths):
        check_cancel(cancel)
        path = Path(path)
        try:
            ids, missing = import_file(store, path, cancel)
            key = normalized(path)
            label = (names or {}).get(key) or (str(path.relative_to(root).with_suffix('')) if root else path.stem)
            with store.connection() as db:
                record = db.execute("SELECT value FROM settings WHERE key='playlist_imports'").fetchone()
                registry = json.loads(record[0]) if record else {}
                pid = registry.get(key)
                previous = db.execute('SELECT name FROM playlists WHERE id=?', (pid,)).fetchone() if pid else None
                if previous:
                    name = previous[0]
                    db.execute('DELETE FROM playlist_tracks WHERE playlist_id=?', (pid,))
                else:
                    name, suffix = label, 2
                    while db.execute('SELECT 1 FROM playlists WHERE name=?', (name,)).fetchone():
                        name, suffix = f'{label} ({suffix})', suffix + 1
                    pid = db.execute('INSERT INTO playlists(name) VALUES(?)', (name,)).lastrowid
                db.executemany('INSERT INTO playlist_tracks VALUES(?,?,?)', ((pid, tid, pos) for pos, tid in enumerate(ids)))
                registry[key] = pid
                db.execute("INSERT OR REPLACE INTO settings VALUES('playlist_imports',?)", (json.dumps(registry),))
            result.append(dict(path=str(path), name=name, id=pid, matched=len(ids), missing=missing, error=None))
        except Exception as exc:
            check_cancel(cancel)
            result.append(dict(path=str(path), matched=0, missing=[], error=str(exc)))
        if progress:
            progress({'imported': index + 1, 'total': len(paths)})
    return result
