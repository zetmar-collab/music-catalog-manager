import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from music_catalog_manager.database.store import Store
from music_catalog_manager.services import backup, library_cleanup
from music_catalog_manager.services.artwork import folder_image
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.services.library import Library, album_identity
from music_catalog_manager.services.export import spreadsheet_text
from music_catalog_manager.services import playlists


def test_reject_wrong_columns_before_replacing_database(store, tmp_path):
    other = Store(tmp_path / 'other')
    with other.connection() as db:
        db.execute('ALTER TABLE tracks RENAME COLUMN path TO wrong_path')
    archive = tmp_path / 'bad.zip'
    backup.create(other, archive)
    store.set_setting('keep', 42)
    original = store.path.read_bytes()
    with pytest.raises(ValueError, match='columns'):
        backup.restore(store, archive)
    assert store.setting('keep') == 42
    assert store.path.read_bytes() == original


def test_overlap_scan_and_removal_preserve_child(store, tmp_path, audio_factory):
    parent = tmp_path / 'music'
    child = parent / 'album'
    audio_factory(child / 'one.wav')
    parent_id = store.add_root(parent)
    scan(store, parent_id)
    child_id = store.add_root(child)
    scan(store, child_id)
    scan(store, parent_id)
    assert store.tracks()[0]['root_id'] == child_id
    # Also repair ownership inherited from an older application.
    with store.connection() as db:
        db.execute('UPDATE tracks SET root_id=?', (parent_id,))
    assert library_cleanup.summary(store, parent_id)['tracks'] == 0
    library_cleanup.remove(store, parent_id)
    assert store.tracks()[0]['root_id'] == child_id
    assert (child / 'one.wav').exists()


def test_invalid_folder_image_never_truncates_existing(tmp_path):
    image = io.BytesIO()
    Image.new('RGB', (8, 8)).save(image, 'PNG')
    path = folder_image(tmp_path / 'one.wav', image.getvalue())
    original = path.read_bytes()
    with pytest.raises(Exception):
        folder_image(tmp_path / 'one.wav', b'broken', overwrite=True)
    assert path.read_bytes() == original
    with pytest.raises(FileExistsError):
        folder_image(tmp_path / 'one.wav', image.getvalue())
    assert path.read_bytes() == original


def test_album_identity_order_and_single_playlist_query(store, tmp_path):
    root = store.add_root(tmp_path / 'music')
    ids = []
    with store.connection() as db:
        for disc, number in ((2, 1), (1, 2), (1, 1), (2, 2)):
            tags = json.dumps(dict(discnumber=str(disc), tracknumber=str(number)))
            ids.append(db.execute('INSERT INTO tracks(root_id,path,tags) VALUES(?,?,?)',
                                 (root, str(tmp_path / f'{disc}-{number}.wav'), tags)).lastrowid)
    rows = list(Library(store).all(sort='album_order'))
    assert [(r['tags']['discnumber'], r['tags']['tracknumber']) for r in rows] == [('1','1'),('1','2'),('2','1'),('2','2')]
    assert album_identity(dict(album='Greatest Hits', artist='A')) != album_identity(dict(album='Greatest Hits', artist='B'))
    assert album_identity(dict(album='Mix', artist='A', albumartist='Various')) == album_identity(dict(album='Mix', artist='B', albumartist='Various'))
    pid = playlists.save(store, 'Repeats', [ids[0], ids[1], ids[0]])
    store.track = lambda *_: pytest.fail('N+1 lookup')
    assert [r['id'] for r in playlists.tracks(store, pid)] == [ids[0], ids[1], ids[0]]


@pytest.mark.parametrize('value', ['=1+1', '+cmd', '-1+2', '@SUM(A1)', '\ttext', '\rtext', '  =1'])
def test_csv_formula_prefixes(value):
    assert spreadsheet_text(value).startswith("'")


@pytest.mark.parametrize('damage', ['trigger', 'json'])
def test_invalid_backup_structure_preserves_current(store, tmp_path, damage):
    other = Store(tmp_path / 'other')
    with other.connection() as db:
        if damage == 'trigger':
            db.execute("CREATE TRIGGER unexpected AFTER INSERT ON tracks BEGIN DELETE FROM tracks; END")
        else:
            db.execute("INSERT INTO tracks(path,tags) VALUES('invalid','{bad json')")
    archive = tmp_path / 'bad.zip'
    backup.create(other, archive)
    store.set_setting('keep', True)
    original = store.path.read_bytes()
    with pytest.raises(ValueError):
        backup.restore(store, archive)
    assert store.path.read_bytes() == original


def test_atomic_cover_replace_failure_preserves_original(tmp_path, monkeypatch):
    import music_catalog_manager.services.artwork as artwork
    image = io.BytesIO()
    Image.new('RGB', (8,8)).save(image, 'PNG')
    path = folder_image(tmp_path / 'one.wav', image.getvalue())
    original = path.read_bytes()
    monkeypatch.setattr(artwork.os, 'replace', lambda *args: (_ for _ in ()).throw(OSError('disk error')))
    with pytest.raises(OSError):
        folder_image(tmp_path / 'one.wav', image.getvalue(), overwrite=True)
    assert path.read_bytes() == original


def test_partial_audio_write_keeps_pending_identifier_dirty(store, tmp_path, audio_factory):
    import time
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from music_catalog_manager.ui.window import MainWindow
    app = QApplication.instance() or QApplication([])
    path = audio_factory(tmp_path / 'audio' / 'one.wav')
    scan(store, store.add_root(path.parent))
    tid = store.tracks()[0]['id']
    store.edit([tid], {'musicbrainz_albumid': 'pending-album'})
    window = MainWindow(store)
    try:
        window.write_changes([store.track(tid)], {'title': 'Only title'}, disk=True)
        end = time.monotonic() + 10
        while window.worker and time.monotonic() < end:
            QTest.qWait(10)
            time.sleep(0.001)
        assert window.worker is None
        assert store.track(tid)['dirty'] == 1
        assert store.track(tid)['tags']['musicbrainz_albumid'] == 'pending-album'
    finally:
        window.close()
