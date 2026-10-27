import base64
import os
import shutil
import tempfile
from pathlib import Path

import mutagen
from mutagen import id3
from mutagen.flac import Picture
from mutagen.mp4 import MP4Cover
from music_catalog_manager.database.store import FIELDS

EXTENSIONS = {'.mp3', '.flac', '.m4a', '.mp4', '.ogg', '.opus', '.wav', '.wma', '.aif', '.aiff'}
ID3 = dict(zip(FIELDS, ('TIT2', 'TPE1', 'TALB', 'TPE2', 'TCON', 'TDRC', 'TRCK', 'TPOS', 'TCOM', 'COMM')))
MP4 = dict(zip(FIELDS, ('\xa9nam', '\xa9ART', '\xa9alb', 'aART', '\xa9gen', '\xa9day', 'trkn', 'disk', '\xa9wrt', '\xa9cmt')))
ASF = dict(zip(FIELDS, ('Title', 'Author', 'WM/AlbumTitle', 'WM/AlbumArtist', 'WM/Genre', 'WM/Year', 'WM/TrackNumber', 'WM/PartOfSet', 'WM/Composer', 'Description')))


def family(audio):
    name = audio.__class__.__name__
    if name in ('MP3', 'WAVE', 'AIFF'):
        return 'id3'
    if name == 'MP4':
        return 'mp4'
    if name == 'ASF':
        return 'asf'
    return 'vorbis'


def read(path):
    audio = mutagen.File(path)
    if audio is None or not hasattr(audio.info, 'length'):
        raise ValueError('Unreadable audio')
    if audio.__class__.__name__ == 'MP4' and getattr(audio.info, 'codec', '').startswith(('avc', 'hvc')):
        raise ValueError('Video container')
    tags = audio.tags or {}
    kind = family(audio)
    mapping = {'id3': ID3, 'mp4': MP4, 'asf': ASF}.get(kind, {k: k for k in FIELDS})
    result = {}
    for field, key in mapping.items():
        val = tags.get(key, [])
        if kind == 'id3':
            frames = tags.getall(key) if audio.tags else []
            val = frames[0].text if frames else []
        if val:
            value = val[0]
            result[field] = '/'.join(str(v) for v in value) if isinstance(value, tuple) else str(value)
        else:
            result[field] = ''
    for field, desc in [('musicbrainz_recordingid', 'MusicBrainz Track Id'), ('musicbrainz_albumid', 'MusicBrainz Album Id'), ('isrc', 'ISRC')]:
        if kind == 'id3':
            v = tags.get('TSRC' if field == 'isrc' else 'TXXX:' + desc)
            result[field] = str(v.text[0]) if v and v.text else ''
            if field == 'musicbrainz_recordingid' and tags.get('UFID:http://musicbrainz.org'):
                result[field] = tags['UFID:http://musicbrainz.org'].data.decode('ascii', errors='replace')
        elif kind == 'mp4':
            v = tags.get('----:com.apple.iTunes:' + (desc if field != 'isrc' else 'ISRC'), [])
            result[field] = v[0].decode('utf-8', errors='replace') if v else ''
        else:
            v = tags.get('musicbrainz_trackid' if field == 'musicbrainz_recordingid' else field, []) or tags.get(field, [])
            result[field] = str(v[0]) if v else ''
    image = None
    if kind == 'id3' and audio.tags:
        pictures = audio.tags.getall('APIC')
        image = pictures[0].data if pictures else None
    elif kind == 'mp4':
        image = (tags.get('covr') or [None])[0]
    elif hasattr(audio, 'pictures'):
        image = audio.pictures[0].data if audio.pictures else None
    elif tags.get('metadata_block_picture'):
        try:
            image = Picture(base64.b64decode(tags['metadata_block_picture'][0])).data
        except (ValueError, TypeError):
            pass
    return {'tags': result, 'duration': audio.info.length, 'bitrate': getattr(audio.info, 'bitrate', 0),
            'format': Path(path).suffix[1:].upper(), 'image': image}


def writable(path):
    # WMA/ASF remains read-only until all mappings and image writes are tested.
    return Path(path).suffix.lower() in EXTENSIONS - {'.wma'}


def _modify(path, changes, image=None):
    audio = mutagen.File(path)
    if audio is None:
        raise ValueError('Unreadable audio')
    if audio.tags is None:
        audio.add_tags()
    tags, kind = audio.tags, family(audio)
    for field, value in changes.items():
        if field in ('musicbrainz_recordingid', 'musicbrainz_albumid', 'isrc'):
            desc = {'musicbrainz_recordingid': 'MusicBrainz Track Id', 'musicbrainz_albumid': 'MusicBrainz Album Id', 'isrc': 'ISRC'}[field]
            if kind == 'id3':
                key = 'TSRC' if field == 'isrc' else 'TXXX:' + desc
                tags.delall(key)
                if value:
                    tags.add(id3.TSRC(encoding=3, text=[value]) if field == 'isrc' else id3.TXXX(encoding=3, desc=desc, text=[value]))
                if field == 'musicbrainz_recordingid':
                    tags.delall('UFID:http://musicbrainz.org')
                    if value:
                        tags.add(id3.UFID(owner='http://musicbrainz.org', data=value.encode('ascii')))
            elif kind == 'mp4':
                key = '----:com.apple.iTunes:' + desc
                if value:
                    tags[key] = [value.encode('utf-8')]
                else:
                    tags.pop(key, None)
            elif value:
                tags['musicbrainz_trackid' if field == 'musicbrainz_recordingid' else field] = [value]
            else:
                tags.pop(field, None)
                if field == 'musicbrainz_recordingid':
                    tags.pop('musicbrainz_trackid', None)
            continue
        if field not in FIELDS:
            continue
        if kind == 'id3':
            key = ID3[field]
            tags.delall(key)
            if value:
                cls = getattr(id3, key)
                tags.add(cls(encoding=3, text=[value], **({'lang': 'eng', 'desc': ''} if key == 'COMM' else {})))
        elif kind == 'mp4':
            key = MP4[field]
            if value:
                if field in ('tracknumber', 'discnumber'):
                    parts = [int(x) for x in value.split('/')]
                    if len(parts) > 2 or any(x < 0 or x > 65535 for x in parts):
                        raise ValueError('Invalid track/disc number')
                    tags[key] = [(parts[0], parts[1] if len(parts) == 2 else 0)]
                else:
                    tags[key] = [value]
            else:
                tags.pop(key, None)
        else:
            if value:
                tags[field] = [value]
            else:
                tags.pop(field, None)
    if image:
        from music_catalog_manager.services.artwork import validate_image
        image = validate_image(image)
        if kind == 'id3':
            tags.delall('APIC')
            tags.add(id3.APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=image))
        elif kind == 'mp4':
            tags['covr'] = [MP4Cover(image, imageformat=MP4Cover.FORMAT_JPEG)]
        else:
            pic = Picture()
            pic.type, pic.mime, pic.data = 3, 'image/jpeg', image
            if hasattr(audio, 'add_picture'):
                audio.clear_pictures()
                audio.add_picture(pic)
            else:
                tags['metadata_block_picture'] = [base64.b64encode(pic.write()).decode('ascii')]
    audio.save()


def write_safe(path, changes, image=None, backup_dir=None):
    path = Path(path)
    if not writable(path):
        raise ValueError('Read-only format')
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('Missing or empty file')
    original = path.stat()
    fd, name = tempfile.mkstemp(prefix='.mcm-', suffix=path.suffix, dir=path.parent)
    os.close(fd)
    temp = Path(name)
    backup_path = None
    try:
        shutil.copy2(path, temp)
        _modify(temp, changes, image)
        check = read(temp)
        for key, value in changes.items():
            if key in FIELDS and check['tags'].get(key, '') != value and not (key in ('tracknumber', 'discnumber') and check['tags'].get(key) == value + '/0'):
                raise ValueError('Tag verification failed: ' + key)
        if temp.stat().st_size == 0:
            raise ValueError('Empty output')
        if path.stat().st_mtime_ns != original.st_mtime_ns or path.stat().st_size != original.st_size:
            raise ValueError('File changed during write')
        if backup_dir:
            import uuid
            folder = Path(backup_dir)
            folder.mkdir(parents=True, exist_ok=True)
            backup_path = folder / (uuid.uuid4().hex + '-' + path.name)
            shutil.copy2(path, backup_path)
        os.replace(temp, path)
        return backup_path
    finally:
        temp.unlink(missing_ok=True)
