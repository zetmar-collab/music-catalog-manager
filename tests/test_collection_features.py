import json
from pathlib import Path
from threading import Event

import pytest

from music_catalog_manager.database.store import Store
from music_catalog_manager.services import (backup, portable_backup, backup_retention,
    smart_playlists, playlists, playlist_revisions, session, replaygain, folder_watch)
from music_catalog_manager.services.scanner import scan


def catalog(store, tmp_path, audio_factory):
    root = tmp_path / 'music'
    for name in ('one.wav', 'two.wav'):
        audio_factory(root / name)
    rid = store.add_root(root)
    scan(store, rid)
    return root, rid, store.tracks()


def test_portable_roundtrip_remaps_paths_and_preserves_repeats(store, tmp_path, audio_factory):
    root, rid, rows = catalog(store, tmp_path, audio_factory)
    store.edit([rows[0]['id']], {'title': 'Łódź'})
    playlists.save(store, 'Twice', [rows[0]['id'], rows[1]['id'], rows[0]['id']])
    store.set_setting('watch_folders', True)
    archive = tmp_path / 'collection.zip'
    portable_backup.create(store, archive)
    original = store.path.read_bytes()
    profile = portable_backup.restore(archive, tmp_path / 'restored')
    other = Store(profile)
    assert store.path.read_bytes() == original
    assert all(Path(row['path']).is_file() for row in other.tracks())
    assert all(Path(row['path']).is_relative_to(tmp_path / 'restored') for row in other.tracks())
    assert other.track(rows[0]['id'])['tags']['title'] == 'Łódź'
    assert len(playlists.tracks(other, playlists.lists(other)[0]['id'])) == 3
    assert not other.setting('watch_folders')
    with pytest.raises(FileExistsError):
        portable_backup.restore(archive, tmp_path / 'restored')


def test_cancelled_portable_restore_never_creates_destination(store, tmp_path, audio_factory):
    catalog(store, tmp_path, audio_factory)
    archive = tmp_path / 'collection.zip'
    portable_backup.create(store, archive)
    cancel = Event()
    cancel.set()
    from music_catalog_manager.services.musicbrainz import Cancelled
    with pytest.raises(Cancelled):
        portable_backup.restore(archive, tmp_path / 'cancelled', cancel)
    assert not (tmp_path / 'cancelled').exists()


def test_smart_rules_are_dynamic_and_parameterized(store, tmp_path, audio_factory):
    _, _, rows = catalog(store, tmp_path, audio_factory)
    pid = smart_playlists.save(store, 'Jazz', 'all', [dict(field='genre', operator='equals', value='jazz')])
    from music_catalog_manager.services.library import Library
    assert list(Library(store).all(playlist=pid, sort='playlist_position')) == []
    store.edit([rows[0]['id']], {'genre': 'Jazz'})
    assert [r['id'] for r in Library(store).all(playlist=pid)] == [rows[0]['id']]
    smart_playlists.save(store, 'Injection', 'all', [dict(field='genre', operator='equals', value="' OR 1=1 --")], pid)
    assert list(Library(store).all(playlist=pid)) == []
    with pytest.raises(ValueError):
        smart_playlists.compile_rules(dict(rules=[dict(field='title);DROP TABLE tracks', operator='equals', value='x')]))


def test_reimport_diff_preserve_and_restore(store, tmp_path, audio_factory):
    root, _, rows = catalog(store, tmp_path, audio_factory)
    path = root / 'list.m3u8'
    path.write_text('one.wav\ntwo.wav\none.wav\n', encoding='utf-8')
    first = playlist_revisions.apply(store, playlist_revisions.plan(store, path))
    old = [r['id'] for r in playlists.tracks(store, first['id'])]
    path.write_text('two.wav\nunknown.wav\n', encoding='utf-8')
    plan = playlist_revisions.plan(store, path)
    assert (plan['added'], plan['removed'], len(plan['missing'])) == (0, 2, 1)
    playlist_revisions.apply(store, plan, preserve=True)
    assert len(playlists.tracks(store, first['id'])) == 3
    revision = playlist_revisions.revisions(store, first['id'])[0]
    playlist_revisions.restore(store, first['id'], revision)
    assert [r['id'] for r in playlists.tracks(store, first['id'])] == old
    stale = playlist_revisions.plan(store, path)
    path.write_text('one.wav\n', encoding='utf-8')
    with pytest.raises(ValueError, match='source changed'):
        playlist_revisions.apply(store, stale)


def test_session_excludes_reused_ids_and_keeps_duplicate_positions(store, tmp_path, audio_factory):
    _, _, rows = catalog(store, tmp_path, audio_factory)
    session.save(store, [rows[0], rows[0], rows[1]], 1, 1234)
    queue, index, position, _ = session.load(store)
    assert len(queue) == 3 and index == 1 and position == 1234
    with store.connection() as db:
        db.execute('UPDATE tracks SET path=?,file_key=? WHERE id=?', (str(tmp_path / 'new.wav'), 'new', rows[0]['id']))
    queue, index, position, _ = session.load(store)
    assert len(queue) == 1 and position == 0


def test_incremental_snapshot_detects_change_and_missing_file(store, tmp_path, audio_factory):
    root, rid, rows = catalog(store, tmp_path, audio_factory)
    before, _, _ = folder_watch.snapshot(store.roots())
    (root / 'one.wav').unlink()
    after, changed, _ = folder_watch.snapshot(store.roots(), before)
    assert rid in changed
    scan(store, rid, folders=changed[rid])
    assert sum(r['available'] for r in store.tracks()) == 1
    assert len(after) < len(before)


def test_retention_protects_safety_and_requires_confirmation(store):
    for name in ('before-restore-safe.zip', 'a.zip', 'b.zip', 'c.zip'):
        backup.create(store, store.profile / name)
    paths = backup_retention.candidates(store, 1)
    assert len(paths) == 2 and all(not p.name.startswith('before-') for p in paths)
    with pytest.raises(ValueError, match='Confirm'):
        backup_retention.remove(store, paths)
    assert backup_retention.remove(store, paths, confirmed=True) == 2
    assert (store.profile / 'before-restore-safe.zip').exists()


def test_replaygain_handles_gain_peak_and_invalid_values():
    assert replaygain.multiplier({'replaygain_track_gain': '-6 dB'}, 'track') == pytest.approx(0.501187)
    assert replaygain.multiplier({'replaygain_album_gain': '6 dB', 'replaygain_album_peak': '0.8'}, 'album') == 1.25
    assert replaygain.multiplier({'replaygain_track_gain': '-6 dB'}, 'off') == 1
    for value in ('NaN', 'inf', 'bad', '10000 dB'):
        assert replaygain.multiplier({'replaygain_track_gain': value}, 'track') == 1


@pytest.mark.parametrize('suffix', ['mp3', 'flac', 'm4a', 'ogg', 'wav', 'aiff'])
def test_replaygain_read_from_real_formats(tmp_path, audio_factory, suffix):
    import mutagen
    from mutagen.id3 import TXXX
    from music_catalog_manager.services import metadata
    path = audio_factory(tmp_path / ('gain.' + suffix))
    audio = mutagen.File(path)
    if audio.tags is None:
        audio.add_tags()
    family = metadata.family(audio)
    if family == 'id3':
        audio.tags.add(TXXX(encoding=3, desc='REPLAYGAIN_TRACK_GAIN', text=['-6 dB']))
    elif family == 'mp4':
        audio.tags['----:com.apple.iTunes:replaygain_track_gain'] = [b'-6 dB']
    else:
        audio.tags['replaygain_track_gain'] = ['-6 dB']
    audio.save()
    assert replaygain.multiplier(metadata.read(path)['tags'], 'track') == pytest.approx(0.501187)


@pytest.mark.parametrize('pending', [False, True])
def test_rescan_old_catalog_populates_replaygain_without_losing_pending_tags(store, tmp_path, audio_factory, pending):
    import mutagen
    from mutagen.id3 import TXXX
    from music_catalog_manager.services import metadata
    path = audio_factory(tmp_path / 'music' / 'gain.wav')
    audio = mutagen.File(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TXXX(encoding=3, desc='REPLAYGAIN_TRACK_GAIN', text=['-6 dB']))
    audio.save()
    rid = store.add_root(path.parent)
    scan(store, rid)
    row = store.tracks()[0]
    old_tags = {k: v for k, v in row['tags'].items() if k not in metadata.REPLAYGAIN_FIELDS}
    if pending:
        old_tags['title'] = 'Pending title'
    with store.connection() as db:
        db.execute('UPDATE tracks SET tags=?,dirty=? WHERE id=?', (json.dumps(old_tags), int(pending), row['id']))
    assert scan(store, rid)['changed'] == 1
    updated = store.track(row['id'])
    assert updated['tags']['replaygain_track_gain'] == '-6 dB'
    assert updated['dirty'] == int(pending)
    if pending:
        assert updated['tags']['title'] == 'Pending title'
    assert scan(store, rid)['skipped'] == 1
