import io
import sqlite3
import time
from pathlib import Path
from threading import Event

import pytest
from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from music_catalog_manager.services import audio_backups, backup, library_cleanup, metadata, playlists
from music_catalog_manager.services.artwork import cache_image
from music_catalog_manager.services.musicbrainz import Cancelled
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.ui.window import MainWindow


def wait(predicate):
    deadline = time.monotonic() + 8
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
        time.sleep(0.001)
    assert predicate()


@pytest.fixture
def catalog(store, tmp_path, audio_factory):
    first = audio_factory(tmp_path / 'Music' / 'one.wav')
    second = audio_factory(tmp_path / 'Other' / 'two.wav')
    root1, root2 = store.add_root(first.parent), store.add_root(second.parent)
    scan(store, root1)
    scan(store, root2)
    tracks = store.tracks()
    ids = {row['root_id']: row['id'] for row in tracks}
    store.edit([ids[root1], ids[root2]], {'artist': 'Pending'})
    pid = playlists.save(store, 'Mixed', [ids[root1], ids[root2], ids[root1]])
    store.set_setting('playlist_imports', {'source.m3u': pid})
    store.set_setting('language', 'pl')
    store.set_setting('theme', 'dark')
    image = io.BytesIO()
    Image.new('RGB', (16, 16), '#3269ae').save(image, 'PNG')
    for row in tracks:
        cache_image(store, row['id'], image.getvalue())
        path = metadata.write_safe(row['path'], {}, backup_dir=store.profile / 'audio-backups')
        audio_backups.register(store, row['id'], row['path'], path)
    originals = {path: path.read_bytes() for path in (first, second)}
    copies = {path: path.read_bytes() for path in (store.profile / 'audio-backups').iterdir()}
    return dict(roots=(root1, root2), ids=ids, playlist=pid, files=originals, copies=copies)


def assert_files_untouched(catalog):
    for path, data in {**catalog['files'], **catalog['copies']}.items():
        assert path.read_bytes() == data


def test_remove_folder_only_removes_its_records_and_references(store, catalog):
    root1, root2 = catalog['roots']
    counts = library_cleanup.summary(store, root1)
    assert counts['tracks'] == 1 and counts['pending'] == 1 and counts['playlist_entries'] == 2
    result = library_cleanup.remove(store, root1)
    assert Path(result['backup']).is_file()
    assert [r['id'] for r in store.roots()] == [root2]
    assert [r['id'] for r in store.tracks()] == [catalog['ids'][root2]]
    assert [r['id'] for r in playlists.tracks(store, catalog['playlist'])] == [catalog['ids'][root2]]
    assert len(audio_backups.entries(store)) == 1
    with store.connection() as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT count(*) FROM scan_jobs WHERE root_id=?', (root1,)).fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM operation_history WHERE track_id=?', (catalog['ids'][root1],)).fetchone()[0] == 0
    assert store.undo_count() == 1
    assert_files_untouched(catalog)


def test_clear_all_library_records_preserves_preferences_and_disk_files(store, catalog):
    cache_files = set(store.cache.iterdir())
    result = library_cleanup.remove(store)
    with store.connection() as db:
        for table in ('tracks', 'library_roots', 'playlists', 'playlist_tracks', 'artwork', 'scan_jobs', 'operation_history', 'audio_backups'):
            assert db.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert store.setting('language') == 'pl'
    assert store.setting('theme') == 'dark'
    assert store.setting('playlist_imports') is None
    assert set(store.cache.iterdir()) == cache_files
    assert_files_untouched(catalog)
    # The automatically created snapshot restores the catalog and its relationships.
    backup.restore(store, result['backup'])
    assert len(store.tracks()) == 2 and len(store.roots()) == 2
    assert len(playlists.tracks(store, catalog['playlist'])) == 3
    assert len(audio_backups.entries(store)) == 2


def test_backup_failure_and_missing_root_leave_catalog_unchanged(store, catalog, monkeypatch):
    before = store.tracks()
    def failure(*args, **kwargs):
        raise OSError('backup disk full')
    monkeypatch.setattr(backup, 'create', failure)
    with pytest.raises(OSError, match='disk full'):
        library_cleanup.remove(store)
    assert store.tracks() == before
    with pytest.raises(KeyError):
        library_cleanup.remove(store, 9999)
    assert_files_untouched(catalog)


def test_cancel_before_delete_keeps_all_records(store, catalog, monkeypatch):
    cancel = Event()
    cancel.set()
    with pytest.raises(Cancelled):
        library_cleanup.remove(store, cancel=cancel)
    assert not list(store.profile.glob('before-*.zip'))
    cancel.clear()
    original = backup.create
    def complete_then_cancel(*args, **kwargs):
        value = original(*args, **kwargs)
        cancel.set()
        return value
    monkeypatch.setattr(backup, 'create', complete_then_cancel)
    with pytest.raises(Cancelled):
        library_cleanup.remove(store, cancel=cancel)
    assert len(store.tracks()) == 2 and len(store.roots()) == 2
    assert_files_untouched(catalog)


@pytest.mark.parametrize('whole_library', [False, True])
def test_sql_failure_rolls_back_every_table(store, catalog, whole_library):
    with store.connection() as db:
        db.execute("CREATE TRIGGER stop_remove BEFORE DELETE ON library_roots BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='simulated failure'):
        library_cleanup.remove(store, None if whole_library else catalog['roots'][0])
    assert len(store.tracks()) == 2 and len(store.roots()) == 2
    assert len(audio_backups.entries(store)) == 2
    assert len(playlists.tracks(store, catalog['playlist'])) == 3
    assert store.undo_count() == 2
    assert_files_untouched(catalog)


def test_removed_track_id_reuse_cannot_undo_into_new_record(store, catalog, tmp_path, audio_factory):
    library_cleanup.remove(store)
    path = audio_factory(tmp_path / 'New' / 'new.wav')
    scan(store, store.add_root(path.parent))
    assert not store.undo()
    assert store.tracks()[0]['tags']['artist'] == ''


@pytest.mark.parametrize('whole_library', [False, True])
def test_cancel_during_delete_rolls_back_all_records(store, catalog, monkeypatch, whole_library):
    from contextlib import contextmanager
    cancel = Event()
    original = store.connection
    @contextmanager
    def connection():
        with original() as db:
            db.create_function('cancel_cleanup', 0, lambda: (cancel.set(), 0)[1])
            yield db
    with original() as db:
        db.execute('CREATE TRIGGER cancel_remove AFTER DELETE ON tracks BEGIN SELECT cancel_cleanup(); END')
    monkeypatch.setattr(store, 'connection', connection)
    with pytest.raises(Cancelled):
        library_cleanup.remove(store, None if whole_library else catalog['roots'][0], cancel=cancel)
    assert len(store.tracks()) == 2 and len(store.roots()) == 2
    assert len(playlists.tracks(store, catalog['playlist'])) == 3
    assert len(audio_backups.entries(store)) == 2
    assert store.undo_count() == 2
    assert_files_untouched(catalog)


def test_ui_decline_does_not_start_removal(store, catalog, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    previews = []
    monkeypatch.setattr(window, 'preview', lambda title, text: (previews.append((title, text)), False)[1])
    assert not window.clear_library_dialog()
    assert not window.remove_folder_dialog(catalog['roots'][0])
    assert window.worker is None and len(store.tracks()) == 2
    assert '2' in previews[0][1]
    assert not list(store.profile.glob('before-*.zip'))
    window.close()


def test_ui_clear_releases_queue_resets_filters_and_reports_backup(store, catalog, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    window.group.setCurrentIndex(4)
    window.groups.setCurrentIndex(window.groups.findData(catalog['playlist']))
    wait(lambda: not window.loading_library)
    window.playback.queue = store.tracks()
    window.playback.current = 0
    monkeypatch.setattr(window, 'preview', lambda *args: True)
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: messages.append(args[2]))
    assert window.clear_library_dialog()
    assert window.playback.queue == []
    wait(lambda: window.worker is None and not window.loading_library and bool(messages))
    assert window.model.rowCount() == 0 and window.active_playlist is None
    assert window.combos['root_id'].count() == 1
    assert 'before-clear-library-' in messages[0]
    window.close()
