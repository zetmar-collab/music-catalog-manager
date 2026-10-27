import json
import math
import sqlite3
import struct
import time
import wave
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from music_catalog_manager.database.store import Store, normalized
from music_catalog_manager.services import audio_backups, backup, metadata, organize, playlists, rename
from music_catalog_manager.services.library import Library
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.ui.models import TrackModel
from music_catalog_manager.ui.window import MainWindow


def wait(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
        time.sleep(0.001)
    assert predicate()


def seed(store, count=3):
    with store.connection() as db:
        for i in range(count):
            db.execute('INSERT INTO tracks(path,tags,duration,format,dirty,available) VALUES(?,?,?,?,?,?)',
                       (normalized(store.profile / f'{i}.mp3'), json.dumps(dict(title=f'Title {i:06}', artist='Łódź', album='Album', tracknumber=str(i+1))),
                        200+i%3, 'MP3', i%2, int(i%3 != 0)))
    return store.tracks()


def test_migrate_v1_preserves_library_and_legacy_undo(tmp_path):
    store = Store(tmp_path)
    rows = seed(store)
    store.edit([rows[0]['id']], {'title': 'legacy'})
    with store.connection() as db:
        db.executescript('''DROP INDEX history_operation; ALTER TABLE operation_history DROP COLUMN operation_id;
            DROP TABLE playlist_tracks; DROP TABLE playlists; DROP TABLE audio_backups; PRAGMA user_version=1;''')
    upgraded = Store(tmp_path)
    assert len(upgraded.tracks()) == 3
    assert upgraded.undo()
    assert upgraded.track(rows[0]['id'])['tags']['title'] == 'Title 000000'
    with upgraded.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2


def test_group_undo_survives_restart_and_keeps_earlier_edit(tmp_path):
    store = Store(tmp_path)
    rows = seed(store)
    ids = [r['id'] for r in rows]
    store.edit([ids[0]], {'genre': 'Jazz'})
    group = store.edit(ids[:2], {'artist': 'New'})
    store.edit([ids[2]], {'artist': 'New'}, group)
    restarted = Store(tmp_path)
    assert restarted.undo_count() == 3
    assert restarted.undo()
    assert all(r['tags']['artist'] == 'Łódź' for r in restarted.tracks())
    assert restarted.track(ids[0])['tags']['genre'] == 'Jazz'
    assert restarted.undo_count() == 1


def test_sql_pages_filters_unicode_sort_and_injection(store):
    rows = seed(store, 600)
    library = Library(store)
    first, count = library.page(limit=250)
    second, _ = library.page(limit=250, offset=250)
    assert count == 600 and len(first) == len(second) == 250
    assert {r['id'] for r in first}.isdisjoint(r['id'] for r in second)
    assert library.page(query='łÓDŹ', limit=1000)[1] == 600
    assert library.page(query="' OR 1=1 --")[1] == 0
    assert library.page(quick='pending')[1] == 300
    assert library.page(quick='unavailable')[1] == 200
    assert library.page(quick='artwork')[1] == 600
    assert library.page(sort='tracknumber')[0][1]['tags']['tracknumber'] == '2'
    ascending, _ = library.page(sort='status')
    assert all(not row['available'] for row in ascending[:200])
    with pytest.raises(ValueError):
        library.page(sort='title;DROP TABLE tracks')
    with pytest.raises(ValueError):
        library.page(filters={'injection': 'x'})
    assert library.facets()['artist'] == ['Łódź']
    store.edit([rows[0]['id']], {'title': ''})
    assert library.page(quick='missing')[1] == 1


def test_status_sort_keys_distinguish_states(store):
    rows = seed(store, 4)
    model = TrackModel()
    model.replace(rows)
    keys = [model.data(model.index(i, 8), Qt.UserRole) for i in range(4)]
    assert keys == [0, 1, 3, 0]


def test_audio_backup_restores_bytes_tags_and_can_be_reversed(store, tmp_path, audio_factory):
    path = audio_factory(tmp_path / 'music' / 'track.mp3')
    scan(store, store.add_root(path.parent))
    row = store.tracks()[0]
    original = path.read_bytes()
    saved = metadata.write_safe(path, {'title': 'Changed'}, backup_dir=store.profile / 'audio-backups')
    changed = path.read_bytes()
    audio_backups.register(store, row['id'], path, saved)
    first = audio_backups.entries(store)[0]
    audio_backups.restore(store, first['id'])
    assert path.read_bytes() == original
    assert store.track(row['id'])['tags']['title'] == ''
    safety = audio_backups.entries(store)[0]
    audio_backups.restore(store, safety['id'])
    assert path.read_bytes() == changed
    assert store.track(row['id'])['tags']['title'] == 'Changed'
    saved.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum'):
        audio_backups.restore(store, first['id'])
    assert path.read_bytes() == changed


def test_backup_and_rename_cancellation_leave_originals(store, tmp_path, audio_factory):
    cancel = Event()
    cancel.set()
    from music_catalog_manager.services.musicbrainz import Cancelled
    with pytest.raises(Cancelled):
        backup.create(store, tmp_path / 'cancelled.zip', cancel)
    assert not (tmp_path / 'cancelled.zip').exists()
    for i in range(2):
        audio_factory(tmp_path / 'music' / f'{i}.wav')
    scan(store, store.add_root(tmp_path / 'music'))
    rows = store.tracks()
    plan = rename.preview(rows, '{title}') if all(r['tags'].get('title') for r in rows) else [(r['id'], Path(r['path']), Path(r['path']).with_name('new' + Path(r['path']).name)) for r in rows]
    cancel.clear()
    with pytest.raises(Cancelled):
        rename.execute(store, plan, cancel, lambda _: cancel.set())
    assert all(Path(r['path']).exists() for r in rows)
    assert [r['path'] for r in store.tracks()] == [r['path'] for r in rows]


def test_playlists_preserve_order_and_m3u_roundtrip(store, tmp_path):
    rows = seed(store)
    order = [rows[2]['id'], rows[0]['id'], rows[2]['id']]
    pid = playlists.save(store, 'My list', order)
    assert [r['id'] for r in playlists.tracks(store, pid)] == order
    target = tmp_path / 'list.m3u8'
    playlists.export_m3u(target, playlists.tracks(store, pid))
    ids, missing = playlists.import_m3u(store, target)
    assert ids == order and missing == []
    target.write_text('#EXTM3U\nhttps://example.test/stream\nmissing.mp3\n', encoding='utf-8-sig')
    assert len(playlists.import_m3u(store, target)[1]) == 2
    playlists.save(store, 'Renamed', order[::-1], pid)
    assert playlists.lists(store)[0]['name'] == 'Renamed'
    playlists.remove(store, pid)
    assert playlists.lists(store) == []


def test_filename_parser_quality_and_candidate_detection(store):
    assert organize.parse_filename('01 - Łódź - Song.mp3') == {'tracknumber': '1', 'artist': 'Łódź', 'title': 'Song'}
    with pytest.raises(ValueError):
        organize.parse_filename('Song.mp3')
    with pytest.raises(ValueError):
        organize.parse_filename('Song.mp3', '{title.__class__}')
    rows = seed(store)
    rows[0]['tags'].update(tracknumber='1/4', title='Same', artist='ŁÓDŹ')
    rows[1]['tags'].update(tracknumber='3/4', title='same')
    rows[2]['tags']['tracknumber'] = '3/4'
    issues = organize.quality(rows)
    assert any(i['kind'] == 'artist_variants' for i in issues)
    numbering = next(i for i in issues if i['kind'] == 'album_numbering')
    assert numbering['missing'] == [2, 4] and numbering['repeated'] == [3]
    assert len(organize.similar(rows)) == 1


def test_window_pages_async_filters_layout_and_queue_modes(store):
    app = QApplication.instance() or QApplication([])
    rows = seed(store, 520)
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    assert window.model.rowCount() == 250
    assert window.next_page.isEnabled()
    window.next_page.click()
    wait(lambda: not window.loading_library)
    assert window.page_offset == 250 and window.model.rowCount() == 250
    window.quick_filter.setCurrentIndex(window.quick_filter.findData('pending'))
    wait(lambda: not window.loading_library)
    assert window.page_offset == 0
    assert all(r['dirty'] for r in window.model.rows)
    window.search.setText('Title 000519')
    wait(lambda: window.model.rowCount() == 1)
    window.clear_filters()
    wait(lambda: not window.loading_library)
    assert window.model.rowCount() == 250
    window.table.setColumnHidden(7, True)
    window.table.setColumnWidth(0, 310)
    window.playback.shuffle.setChecked(True)
    window.playback.repeat.setCurrentIndex(2)
    assert store.setting('shuffle') is True and store.setting('repeat') == 'all'
    window.close()
    reopened = MainWindow(store)
    wait(lambda: not reopened.loading_library)
    assert reopened.table.isColumnHidden(7)
    assert reopened.table.columnWidth(0) == 310
    reopened.close()


def test_audio_comparison_discriminates_frequencies(tmp_path):
    app = QApplication.instance() or QApplication([])
    from music_catalog_manager.services.audio_compare import fingerprint, similarity
    def tone(name, frequency):
        path = tmp_path / name
        with wave.open(str(path), 'wb') as out:
            out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            out.writeframes(b''.join(struct.pack('<h', int(15000*math.sin(2*math.pi*frequency*i/8000))) for i in range(24000)))
        return path
    first = fingerprint(tone('one.wav', 440))
    second = fingerprint(tone('two.wav', 1320))
    assert similarity(first, first) >= 99
    assert similarity(first, second) < 50


def test_audio_comparison_runs_in_worker_and_supports_cancel(tmp_path):
    app = QApplication.instance() or QApplication([])
    from music_catalog_manager.services.audio_compare import compare
    from music_catalog_manager.services.musicbrainz import Cancelled
    from music_catalog_manager.ui.worker import Worker
    path = tmp_path / 'tone.wav'
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        out.writeframes(b''.join(struct.pack('<h', int(12000*math.sin(2*math.pi*440*i/8000))) for i in range(24000)))
    rows = [dict(id=i, path=str(path)) for i in (1, 2)]
    results, errors = [], []
    worker = Worker(lambda cancel, progress: compare(rows, cancel, progress))
    worker.result.connect(results.append)
    worker.failed.connect(errors.append)
    worker.start()
    wait(lambda: bool(results or errors), timeout=10)
    worker.wait()
    assert not errors and results[0][0][0]['score'] >= 99
    cancel = Event()
    cancel.set()
    with pytest.raises(Cancelled):
        compare(rows, cancel)


def test_album_release_api_mapping_and_escaping(store):
    import httpx
    from music_catalog_manager.services.musicbrainz import MusicBrainz
    release_id = '12345678-1234-1234-1234-123456789012'
    requests = []
    def respond(request):
        requests.append(request)
        if request.url.path.endswith('/' + release_id):
            return httpx.Response(200, json={'id': release_id, 'title': 'Album', 'date': '2026',
                'artist-credit': [{'name': 'Łódź'}], 'media': [{'position': 1, 'tracks': [
                    {'position': 1, 'recording': {'id': release_id, 'title': 'Song'}}]}]})
        return httpx.Response(200, json={'releases': [{'id': release_id, 'title': 'Album'}]})
    client = MusicBrainz(store.profile, 'https://example.test/contact', client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert client.releases('Łódź', 'Album "x"')[0]['id'] == release_id
    assert '\\"' in requests[0].url.params['query']
    tracks = client.release_tracks(release_id)
    assert tracks[0]['tracknumber'] == '1/1'
    assert tracks[0]['discnumber'] == '1/1'
    assert tracks[0]['artist'] == 'Łódź'
    assert tracks[0]['title'] == 'Song'
    client.client.close()


def test_feature_dialogs_construct_and_close(store, monkeypatch):
    from PySide6.QtWidgets import QDialog
    app = QApplication.instance() or QApplication([])
    seed(store)
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    titles = []
    monkeypatch.setattr(QDialog, 'exec', lambda dialog: (titles.append(dialog.windowTitle()), QDialog.Rejected)[1])
    window.albums_dialog()
    window.folders_dialog()
    window.backups_dialog()
    window.restore_audio_dialog()
    window.playlists_dialog()
    window.playback.queue_dialog()
    window.history()
    assert len(titles) == 7
    window.close()


def test_bulk_disk_edits_share_undo_and_backup_records(store, tmp_path, audio_factory):
    app = QApplication.instance() or QApplication([])
    for i in range(2):
        audio_factory(tmp_path / 'audio' / f'{i}.mp3')
    scan(store, store.add_root(tmp_path / 'audio'))
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    window.write_changes(store.tracks(), {'artist': 'Changed'}, disk=True)
    wait(lambda: window.worker is None)
    assert store.undo_count() == 2
    assert len(audio_backups.entries(store)) == 2
    assert all(metadata.read(row['path'])['tags']['artist'] == 'Changed' for row in store.tracks())
    store.undo()
    assert all(row['tags']['artist'] == '' for row in store.tracks())
    # Database undo deliberately leaves the files as written.
    assert all(metadata.read(row['path'])['tags']['artist'] == 'Changed' for row in store.tracks())
    window.close()


def test_export_all_pages_and_cancel_preserves_destination(store, tmp_path):
    from music_catalog_manager.services.export import export_library
    from music_catalog_manager.services.musicbrainz import Cancelled
    seed(store, 600)
    path = tmp_path / 'library.json'
    cancel = Event()
    assert export_library(store, {}, path, cancel, lambda _: None) == 600
    assert len(json.loads(path.read_text(encoding='utf-8'))) == 600
    original = path.read_bytes()
    with pytest.raises(Cancelled):
        export_library(store, {}, path, cancel, lambda _: cancel.set())
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('.mcm-export-*'))


def test_folder_artwork_written_once_per_folder(store, tmp_path, audio_factory, monkeypatch):
    import io
    from PIL import Image
    from PySide6.QtWidgets import QInputDialog
    from music_catalog_manager.ui import window as window_module
    app = QApplication.instance() or QApplication([])
    for i in range(2):
        audio_factory(tmp_path / 'audio' / f'{i}.mp3')
    scan(store, store.add_root(tmp_path / 'audio'))
    store.set_setting('language', 'en')
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs: ('Save folder.jpg', True))
    monkeypatch.setattr(window, 'preview', lambda *args: True)
    calls = []
    original = window_module.folder_image
    def record(*args):
        calls.append(args[0])
        return original(*args)
    monkeypatch.setattr(window_module, 'folder_image', record)
    image = io.BytesIO()
    Image.new('RGB', (32, 32), '#3269ae').save(image, 'PNG')
    window.apply_artwork(store.tracks(), image.getvalue())
    wait(lambda: window.worker is None)
    assert len(calls) == 1
    assert (tmp_path / 'audio' / 'folder.jpg').exists()
    assert all(row['artwork'] for row in store.tracks())
    window.close()


def test_removing_current_queue_track_releases_source(store, tmp_path, audio_factory, monkeypatch):
    from PySide6.QtWidgets import QDialog, QListWidget
    from music_catalog_manager.ui.playback import PlaybackBar
    app = QApplication.instance() or QApplication([])
    for i in range(2):
        audio_factory(tmp_path / 'audio' / f'{i}.wav')
    scan(store, store.add_root(tmp_path / 'audio'))
    rows = store.tracks()
    bar = PlaybackBar(store, lambda: [], lambda: rows)
    bar.volume.setValue(0)
    bar.set_queue(rows)
    def edit(dialog):
        dialog.findChild(QListWidget).takeItem(0)
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, 'exec', edit)
    bar.queue_dialog()
    wait(lambda: bar.retiring == 0)
    assert bar.player is None
    assert [r['id'] for r in bar.queue] == [rows[1]['id']]
    bar.toggle()
    assert normalized(bar.player.source().toLocalFile()) == rows[1]['path']
    bar.release()
    wait(lambda: bar.retiring == 0)
    bar.close()
