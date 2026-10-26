import io
import shutil
from pathlib import Path
from unittest.mock import patch
import pytest
import mutagen
from mutagen.id3 import TXXX
from PIL import Image
from music_catalog_manager.services import metadata, rename
from music_catalog_manager.services.artwork import cache_image, folder_image, validate_image
from music_catalog_manager.services.scanner import scan


@pytest.mark.parametrize('extension', ['mp3', 'flac', 'm4a', 'ogg', 'opus', 'wav', 'aiff'])
def test_tag_and_artwork_roundtrip(tmp_path, audio_factory, extension, store):
    path = audio_factory(tmp_path / ('sample.' + extension))
    audio = mutagen.File(path)
    if audio.tags is None:
        audio.add_tags()
    if metadata.family(audio) == 'id3':
        audio.tags.add(TXXX(encoding=3, desc='UnknownCustom', text=['keep']))
    elif metadata.family(audio) == 'mp4':
        audio.tags['----:com.apple.iTunes:UnknownCustom'] = [b'keep']
    else:
        audio.tags['UnknownCustom'] = ['keep']
    audio.save()
    image = io.BytesIO()
    Image.new('RGB', (32, 32), '#538fe6').save(image, 'PNG')
    changes = {k: 'Żółć' for k in ('title', 'artist', 'album', 'albumartist', 'genre', 'composer', 'comment')}
    changes.update(date='2026', tracknumber='2/10', discnumber='1/2', isrc='PLTEST1234567', musicbrainz_albumid='a'*36, musicbrainz_recordingid='12345678-1234-1234-1234-123456789012')
    metadata.write_safe(path, changes, image.getvalue(), tmp_path / 'backups')
    result = metadata.read(path)
    for key, value in changes.items():
        assert result['tags'][key] == value
    assert result['image']
    assert len(list((tmp_path / 'backups').iterdir())) == 1
    audio = mutagen.File(path)
    assert 'keep' in str(audio.tags)
    cache_image(store, None, image.getvalue())
    target = folder_image(path, image.getvalue())
    assert target.exists()
    with pytest.raises(FileExistsError):
        folder_image(path, image.getvalue())


def test_failure_preserves_original(tmp_path, audio_factory):
    path = audio_factory(tmp_path / 'safe.mp3')
    original = path.read_bytes()
    with patch('music_catalog_manager.services.metadata._modify', side_effect=OSError('simulated disk failure')):
        with pytest.raises(OSError):
            metadata.write_safe(path, {'title': 'test'})
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('.mcm-*'))
    assert not metadata.writable('test.wma')
    with pytest.raises(ValueError):
        metadata.write_safe(tmp_path / 'file.wma', {})
    with pytest.raises(Exception):
        validate_image(b'not an image')


def test_rename_collision_and_rollback(store, tmp_path, audio_factory):
    root = tmp_path / 'music'
    audio_factory(root / '1.wav')
    audio_factory(root / '2.wav')
    scan(store, store.add_root(root))
    tracks = store.tracks()
    store.edit([tracks[0]['id']], {'title': 'CON', 'tracknumber': '1'})
    store.edit([tracks[1]['id']], {'title': 'a:b', 'tracknumber': '2'})
    plan = rename.preview(store.tracks(), '{track:02} - {title}')
    rename.execute(store, plan)
    assert all(p.exists() for _, _, p in plan)
    assert store.tracks()[0]['path'].lower().endswith('01 - con.wav')
    assert rename.safe_name('CON', '.mp3') == '_CON.mp3'
    with pytest.raises(FileExistsError):
        rename.preview(store.tracks(), 'same')
    before = store.tracks()
    plan = rename.preview(before, 'renamed {track:02}')
    import os
    original = os.rename
    calls = 0
    def fail_second(a, b):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('simulated')
        return original(a, b)
    with patch('music_catalog_manager.services.rename.os.rename', fail_second):
        with pytest.raises(OSError):
            rename.execute(store, plan)
    assert all(Path(t['path']).exists() for t in before)
    assert [t['path'] for t in before] == [t['path'] for t in store.tracks()]
