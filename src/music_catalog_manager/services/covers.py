"""Album/artist cover search; providers return previews, never apply them."""
import hashlib
import uuid

from music_catalog_manager.services.artwork import validate_image
from music_catalog_manager.services.musicbrainz import Cancelled


def search(client, artist, album, progress=None, limit=8):
    artist, album = artist.strip(), album.strip()
    if not artist or not album:
        raise ValueError('Enter both album and artist')
    if not 1 <= limit <= 8:
        raise ValueError('Invalid cover limit')
    releases = client.releases(artist, album)[:12]
    candidates, errors, seen, groups = [], [], set(), set()
    for index, release in enumerate(releases):
        if client.cancel.is_set():
            raise Cancelled()
        if progress:
            progress({'checked': index + 1, 'total': len(releases), 'covers': len(candidates)})
        try:
            data = client.cover(release['id'])
            group = release.get('release-group', {}).get('id')
            if not data and group and group not in groups:
                groups.add(group)
                data = client.request(f'https://coverartarchive.org/release-group/{uuid.UUID(group)}/front-500', binary=True)
            if not data:
                continue
            data = validate_image(data)
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            credit = ''.join(x.get('name', x.get('artist', {}).get('name', '')) + x.get('joinphrase', '') for x in release.get('artist-credit', []))
            candidates.append(dict(data=data, release_id=release['id'], album=release.get('title', album),
                artist=credit or artist, date=release.get('date', ''), country=release.get('country', ''),
                source='Cover Art Archive', url=f"https://musicbrainz.org/release/{release['id']}"))
            if len(candidates) >= limit:
                break
        except Cancelled:
            raise
        except Exception as exc:
            errors.append(release.get('title', album) + ': ' + str(exc))
    return {'covers': candidates, 'errors': errors}
