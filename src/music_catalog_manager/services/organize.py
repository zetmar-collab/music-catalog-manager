import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from music_catalog_manager.database.store import FIELDS


def parse_filename(path, template='{tracknumber} - {artist} - {title}'):
    """Literal separators and named fields only; never execute a format expression."""
    parts = re.split(r'(\{[^{}]+\})', template)
    pattern, used = [], set()
    for part in parts:
        if part.startswith('{') and part.endswith('}'):
            key = part[1:-1]
            if key not in FIELDS or key in used:
                raise ValueError('Unknown or repeated field')
            used.add(key)
            pattern.append(f'(?P<{key}>.+?)')
        else:
            if '{' in part or '}' in part:
                raise ValueError('Invalid template')
            pattern.append(re.escape(part))
    if not used:
        raise ValueError('Template needs at least one field')
    match = re.fullmatch(''.join(pattern), Path(path).stem)
    if not match:
        raise ValueError('Filename does not match template')
    result = {k: v.strip() for k, v in match.groupdict().items()}
    for key in ('tracknumber', 'discnumber'):
        if key in result:
            if not result[key].isdigit():
                raise ValueError('Invalid track/disc number')
            result[key] = str(int(result[key]))
    return result


def normalized_name(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def quality(rows, cancel=None):
    issues, albums, artists = [], defaultdict(list), defaultdict(set)
    for row in rows:
        tags = row['tags']
        missing = [k for k in ('title', 'artist', 'album', 'tracknumber') if not tags.get(k)]
        if missing:
            issues.append({'kind': 'missing_tags', 'path': row['path'], 'fields': missing})
        if not row.get('artwork'):
            issues.append({'kind': 'missing_artwork', 'path': row['path']})
        if not row['available']:
            issues.append({'kind': 'unavailable', 'path': row['path']})
        artist = tags.get('artist', '')
        if artist:
            artists[normalized_name(artist)].add(artist)
        if tags.get('album'):
            albums[(normalized_name(tags.get('albumartist') or artist), normalized_name(tags['album']), tags.get('discnumber', '').split('/')[0] or '1')].append(row)
    for variants in artists.values():
        if len(variants) > 1:
            issues.append({'kind': 'artist_variants', 'values': sorted(variants)})
    for key, tracks in albums.items():
        if cancel is not None and cancel.is_set():
            from music_catalog_manager.services.musicbrainz import Cancelled
            raise Cancelled()
        numbers, totals = [], []
        for row in tracks:
            parts = row['tags'].get('tracknumber', '').split('/')
            try:
                numbers.append(int(parts[0]))
                if len(parts) > 1 and int(parts[1]) > 0:
                    totals.append(int(parts[1]))
            except ValueError:
                continue
        if numbers:
            expected = max(totals or numbers)
            # Malformed external tags must not allocate unbounded lists.
            if expected > 10000:
                issues.append({'kind': 'invalid_track_total', 'album': key, 'total': expected})
                continue
            missing = sorted(set(range(1, expected + 1)) - set(numbers))
            repeated = sorted(n for n in set(numbers) if numbers.count(n) > 1)
            if missing or repeated:
                issues.append({'kind': 'album_numbering', 'album': key, 'missing': missing, 'repeated': repeated})
    return issues


def similar(rows, cancel=None):
    """Candidates only: metadata and duration do not establish recording identity."""
    groups = defaultdict(list)
    for row in rows:
        title = normalized_name(row['tags'].get('title', ''))
        artist = normalized_name(row['tags'].get('artist', ''))
        if title and artist:
            groups[(artist, title)].append(row)
    result = []
    for key, tracks in groups.items():
        for i, left in enumerate(tracks):
            if cancel is not None and cancel.is_set():
                from music_catalog_manager.services.musicbrainz import Cancelled
                raise Cancelled()
            for right in tracks[i + 1:]:
                if left['duration'] and right['duration'] and abs(left['duration'] - right['duration']) <= 3:
                    result.append({'artist': key[0], 'title': key[1], 'left': left['path'], 'right': right['path'],
                                   'duration_difference': round(abs(left['duration'] - right['duration']), 2)})
    return result
