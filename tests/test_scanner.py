import shutil
from threading import Event
import pytest
from music_catalog_manager.services.scanner import scan


def test_recursive_rescan_corrupt_missing_and_moved(store, tmp_path, audio_factory):
    root = tmp_path / 'Muzyka żółć'
    for ext in ('mp3', 'flac', 'm4a', 'ogg', 'opus', 'wav', 'wma', 'aiff'):
        audio_factory(root / 'podfolder' / ('test.' + ext))
    (root / 'broken.mp3').write_bytes(b'broken')
    rid = store.add_root(root)
    first = scan(store, rid, hashes=True)
    assert first['new'] == 8
    assert first['errors'] == 1
    second = scan(store, rid, hashes=True)
    assert second['new'] == 0 and second['skipped'] == 8
    assert len(store.tracks()) == 8
    source = root / 'podfolder/test.mp3'
    tid = next(t['id'] for t in store.tracks() if t['format'] == 'MP3')
    source.rename(root / 'przeniesiony.mp3')
    scan(store, rid)
    assert store.track(tid)['path'].endswith('przeniesiony.mp3')
    shutil.move(root, tmp_path / 'offline')
    scan(store, rid)
    assert len(store.tracks()) == 8
    assert not any(t['available'] for t in store.tracks())


def test_cancel_and_dirty_values(store, tmp_path, audio_factory):
    root = tmp_path / 'audio'
    audio_factory(root / 'one.wav')
    audio_factory(root / 'two.wav')
    rid = store.add_root(root)
    cancel = Event()
    result = scan(store, rid, cancel, lambda _: cancel.set())
    assert result['scanned'] == 1
    assert len(store.tracks()) == 1
    scan(store, rid)
    tid = store.tracks()[0]['id']
    store.edit([tid], {'title': 'Własny tytuł'})
    scan(store, rid)
    assert store.track(tid)['tags']['title'] == 'Własny tytuł'


def test_long_unicode_path(store, tmp_path, audio_factory):
    root = tmp_path / 'długie'
    nested = root
    for i in range(6):
        nested /= ('podfolder-żółć-' + str(i)) * 2
    path = audio_factory(nested / 'muzyka.wav')
    assert len(str(path)) > 260
    assert scan(store, store.add_root(root))['new'] == 1


def test_junction_loop_is_not_followed(store, tmp_path, audio_factory):
    import os
    import subprocess
    if os.name != 'nt':
        pytest.skip('Windows junction test')
    root = tmp_path / 'junction-root'
    audio_factory(root / 'sample.wav')
    link = root / 'loop'
    quote = lambda p: "'" + str(p).replace("'", "''") + "'"
    subprocess.run(['powershell', '-NoProfile', '-Command',
        'New-Item -ItemType Junction -Path ' + quote(link) + ' -Target ' + quote(root) + ' | Out-Null'], check=True, capture_output=True)
    try:
        assert link.is_junction()
        result = scan(store, store.add_root(root))
        assert result['scanned'] == 1 and result['new'] == 1
    finally:
        os.rmdir(link)
