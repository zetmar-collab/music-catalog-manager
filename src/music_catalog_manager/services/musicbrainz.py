import hashlib
import json
import threading
import time
import uuid
from pathlib import Path

import httpx


class Cancelled(Exception):
    pass


class MusicBrainz:
    lock = threading.Lock()
    last_request = 0.0

    def __init__(self, profile, contact, cancel=None, client=None):
        if not contact or not ('@' in contact or contact.startswith('https://')):
            raise ValueError('Configure contact email or URL in Settings')
        self.cache = Path(profile) / 'http-cache'
        self.cache.mkdir(exist_ok=True)
        self.cancel = cancel or threading.Event()
        self.client = client or httpx.Client(timeout=15, follow_redirects=True,
                    headers={'User-Agent': f'MusicCatalogManager/0.1.0 ({contact})'})
        self.owns_client = client is None

    def close(self):
        if self.owns_client:
            self.client.close()

    def wait(self, seconds):
        if self.cancel.wait(seconds):
            raise Cancelled()

    def request(self, url, params=None, binary=False):
        key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        cached = self.cache / key
        if cached.exists() and time.time() - cached.stat().st_mtime < 7 * 86400:
            return cached.read_bytes() if binary else json.loads(cached.read_bytes())
        for attempt in range(3):
            if self.cancel.is_set():
                raise Cancelled()
            if url.startswith('https://musicbrainz.org/'):
                with MusicBrainz.lock:
                    self.wait(max(0, 1.05 - (time.monotonic() - MusicBrainz.last_request)))
                    MusicBrainz.last_request = time.monotonic()
            try:
                with self.client.stream('GET', url, params=params) as response:
                    if response.status_code == 404:
                        return None
                    if response.status_code in (429, 503):
                        if attempt == 2:
                            response.raise_for_status()
                        retry = response.headers.get('Retry-After', '')
                        self.wait(min(60, float(retry)) if retry.isdigit() else 2 ** (attempt + 1))
                        continue
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        if self.cancel.is_set():
                            raise Cancelled()
                        size += len(chunk)
                        if size > 20 * 1024 * 1024:
                            raise ValueError('Response too large')
                        chunks.append(chunk)
                    data = b''.join(chunks)
                result = data if binary else json.loads(data)
                temp = self.cache / (key + '-' + uuid.uuid4().hex)
                temp.write_bytes(data)
                temp.replace(cached)
                return result
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise
                self.wait(2 ** attempt)

    def search(self, tags):
        if tags.get('musicbrainz_recordingid'):
            mbid = str(uuid.UUID(tags['musicbrainz_recordingid']))
            data = self.request(f'https://musicbrainz.org/ws/2/recording/{mbid}', {'fmt': 'json', 'inc': 'artists+releases'})
            recordings = [data] if data else []
        elif tags.get('musicbrainz_albumid'):
            mbid = str(uuid.UUID(tags['musicbrainz_albumid']))
            release = self.request(f'https://musicbrainz.org/ws/2/release/{mbid}', {'fmt': 'json', 'inc': 'recordings+artist-credits'})
            recordings = []
            if release:
                for medium in release.get('media', []):
                    for track in medium.get('tracks', []):
                        rec = dict(track.get('recording', {}))
                        if not rec.get('id'):
                            continue
                        rec.setdefault('artist-credit', track.get('artist-credit', release.get('artist-credit', [])))
                        rec['releases'] = [{'id': mbid, 'title': release.get('title', ''), 'date': release.get('date', '')}]
                        recordings.append(rec)
        else:
            def quote(value):
                return '"' + ''.join('\\' + c if c in '+-&|!(){}[]^"~*?:\\/' else c for c in value) + '"'
            fields = [('recording', tags.get('title')), ('artist', tags.get('artist')), ('release', tags.get('album'))]
            query = ' AND '.join(f'{field}:{quote(value)}' for field, value in fields if value)
            if tags.get('isrc'):
                query = 'isrc:' + quote(tags['isrc'])
            if not query:
                raise ValueError('No search fields')
            data = self.request('https://musicbrainz.org/ws/2/recording', {'query': query, 'fmt': 'json', 'limit': 10})
            recordings = (data or {}).get('recordings', [])
        results = []
        for recording in recordings:
            artist = ''.join(x.get('name', x.get('artist', {}).get('name', '')) + x.get('joinphrase', '') for x in recording.get('artist-credit', []))
            releases = recording.get('releases') or [{}]
            for release in releases[:3]:
                results.append({'title': recording.get('title', ''), 'artist': artist, 'album': release.get('title', ''),
                    'date': release.get('date', ''), 'musicbrainz_recordingid': recording['id'],
                    'musicbrainz_albumid': release.get('id', ''), 'score': recording.get('score', '?'), 'source': 'MusicBrainz'})
        return results

    def cover(self, release_id):
        release_id = str(uuid.UUID(release_id))
        return self.request(f'https://coverartarchive.org/release/{release_id}/front-500', binary=True)
