import io
import json
import time
from pathlib import Path
from threading import Event

import httpx
import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QFileDialog, QLineEdit, QTextBrowser

from music_catalog_manager.database.store import normalized
from music_catalog_manager.services import covers, playlists
from music_catalog_manager.services.library import Library
from music_catalog_manager.services.musicbrainz import Cancelled, MusicBrainz
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.ui.help_view import help_path
from music_catalog_manager.ui.window import MainWindow


def wait(predicate, seconds=6):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
        time.sleep(0.001)
    assert predicate()


def picture(color='#3269ae'):
    out = io.BytesIO()
    Image.new('RGB', (32, 32), color).save(out, 'PNG')
    return out.getvalue()


@pytest.fixture
def music(store, tmp_path, audio_factory):
    root = tmp_path / 'Muzyka'
    paths = [audio_factory(root / name) for name in ('Łódź.wav', 'Other.wav')]
    scan(store, store.add_root(root))
    return root, paths, store.tracks()


@pytest.mark.parametrize('suffix', ['.m3u', '.m3u8', '.pls', '.wpl', '.xspf'])
def test_playlist_formats_preserve_order_repeats_and_resolve_paths(store, music, suffix):
    root, paths, rows = music
    folder = root / 'Lists'
    folder.mkdir()
    playlist = folder / ('mix' + suffix)
    if suffix in ('.m3u', '.m3u8'):
        content = '#EXTM3U\n../Other.wav\n../Łódź.wav\n../Other.wav\nhttps://example.test/stream\n'
    elif suffix == '.pls':
        content = '[playlist]\nFile3=../Other.wav\nFile2=../Łódź.wav\nFile1=../Other.wav\nFile4=https://example.test/stream\nNumberOfEntries=4\n'
    elif suffix == '.wpl':
        content = '<?xml version="1.0"?><smil><body><seq><media src="../Other.wav"/><media src="../Łódź.wav"/><media src="../Other.wav"/><media src="https://example.test/stream"/></seq></body></smil>'
    else:
        locations = [paths[1].as_uri(), paths[0].as_uri(), paths[1].as_uri(), 'https://example.test/stream']
        content = '<playlist xmlns="http://xspf.org/ns/0/"><trackList>' + ''.join('<track><location>'+p+'</location></track>' for p in locations) + '</trackList></playlist>'
    playlist.write_text(content, encoding='utf-8-sig')
    ids, missing = playlists.import_file(store, playlist)
    expected = {r['path']: r['id'] for r in rows}
    assert ids == [expected[normalized(paths[1])], expected[normalized(paths[0])], expected[normalized(paths[1])]]
    assert missing == ['https://example.test/stream']


def test_recursive_discovery_reimport_and_name_collisions(store, music):
    root, paths, rows = music
    child = root / 'Sub'
    child.mkdir()
    first, second = root / 'mix.m3u', child / 'mix.M3U8'
    first.write_text('Łódź.wav\nOther.wav\n', encoding='utf-8')
    second.write_text('../Other.wav\n', encoding='utf-8')
    (child / 'ignore.txt').write_text('not a playlist')
    found, errors = playlists.discover(root)
    assert set(found) == {first, second} and errors == []
    unrelated = playlists.save(store, 'mix', [rows[0]['id']])
    results = playlists.import_files(store, found, root)
    assert all(not r['error'] for r in results)
    assert len(playlists.lists(store)) == 3

    assert len({r['name'] for r in playlists.lists(store)}) == 3
    assert len(playlists.tracks(store, unrelated)) == 1
    pid = results[0]['id']
    first.write_text('Other.wav\nOther.wav\nOther.wav\n', encoding='utf-8')
    updated = playlists.import_files(store, [first], root)
    assert updated[0]['id'] == pid and updated[0]['matched'] == 3
    assert len(playlists.lists(store)) == 3

    # SQLite may reuse a deleted list ID; reimport must not replace its new owner.
    deleted = results[1]['id']
    playlists.remove(store, deleted)
    replacement = playlists.save(store, 'Unrelated replacement', [rows[0]['id']])
    reimported = playlists.import_files(store, [second], root)
    assert reimported[0]['id'] != replacement
    assert next(r for r in playlists.lists(store) if r['id'] == replacement)['name'] == 'Unrelated replacement'


def test_import_reports_invalid_and_missing_and_cancel_keeps_completed(store, music):
    root, paths, rows = music
    first = root / 'one.m3u'
    first.write_text('Other.wav\nmissing.wav', encoding='utf-8')
    bad = root / 'bad.wpl'
    bad.write_text('broken XML', encoding='utf-8')
    result = playlists.import_files(store, [first, bad], root)
    assert result[0]['matched'] == 1 and result[0]['missing'] == ['missing.wav']
    assert result[1]['error']
    cancel = Event()
    with pytest.raises(Cancelled):
        playlists.import_files(store, [first, bad], root, cancel, lambda _: cancel.set())
    assert len(playlists.lists(store)) == 1
    with pytest.raises(Cancelled):
        playlists.discover(root, cancel)


def test_playlist_legacy_encodings_and_xml_entities(store, music):
    root, paths, rows = music
    legacy = root / 'legacy.m3u'
    legacy.write_bytes('Łódź.wav'.encode('cp1250'))
    assert len(playlists.import_file(store, legacy)[0]) == 1
    legacy.write_bytes('Łódź.wav'.encode('utf-16'))
    assert len(playlists.import_file(store, legacy)[0]) == 1
    bad = root / 'entities.xspf'
    bad.write_bytes('<!DOCTYPE playlist [<!ENTITY a "bad">]><playlist>&a;</playlist>'.encode('utf-16-le'))
    with pytest.raises(ValueError, match='entities'):
        playlists.locations(bad)
    legacy.write_bytes(b'x' * (playlists.MAX_BYTES + 1))
    with pytest.raises(ValueError, match='8 MiB'):
        playlists.locations(legacy)


def test_playlist_sql_paging_and_ui_grouping_follow_positions(store, music):
    app = QApplication.instance() or QApplication([])
    root, paths, rows = music
    order = [rows[1]['id'], rows[0]['id'], rows[1]['id']] * 90
    pid = playlists.save(store, 'Test order', order)
    library = Library(store)
    result, count = library.page(playlist=pid, sort='playlist_position')
    assert count == 270
    assert [r['id'] for r in result] == order[:250]
    assert [r['id'] for r in library.page(playlist=pid, sort='playlist_position', offset=250)[0]] == order[250:]
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    window.group.setCurrentIndex(4)
    window.groups.setCurrentIndex(window.groups.findData(pid))
    wait(lambda: not window.loading_library)
    assert window.active_playlist == pid
    assert [r['id'] for r in window.model.rows] == order[:250]
    window.clear_filters()
    wait(lambda: not window.loading_library)
    assert window.active_playlist is None and window.model.rowCount() == 2
    window.close()


def test_folder_import_catalogs_unknown_audio_before_matching(store, tmp_path, audio_factory, monkeypatch):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / 'New music'
    audio_factory(root / 'new.wav')
    (root / 'mix.m3u').write_text('new.wav\nnew.wav\n', encoding='utf-8')
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *_: str(root))
    monkeypatch.setattr(QDialog, 'exec', lambda *_: QDialog.Accepted)
    errors = []
    monkeypatch.setattr(window, 'error', errors.append)
    window.import_playlist_folder()
    wait(lambda: len(playlists.lists(store)) == 1)
    wait(lambda: window.worker is None and not window.loading_library)
    assert not errors
    assert len(store.tracks()) == 1
    assert len(playlists.tracks(store, playlists.lists(store)[0]['id'])) == 2
    window.close()


def test_cover_search_fallback_deduplication_and_failed_source(store):
    release_ids = [f'00000000-0000-4000-8000-{i:012}' for i in range(1, 4)]
    group = '10000000-0000-4000-8000-000000000001'
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.host == 'musicbrainz.org':
            return httpx.Response(200, json={'releases': [dict(id=rid, title='Kind of Blue', **{'artist-credit':[{'name':'Miles Davis'}], 'release-group':{'id':group}}) for rid in release_ids]})
        if '/release/'+release_ids[0]+'/' in request.url.path:
            return httpx.Response(404)
        if release_ids[2] in request.url.path:
            return httpx.Response(200, content=b'not an image')
        return httpx.Response(200, content=picture())
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = MusicBrainz(store.profile, 'https://github.com/zetmar-collab/music-catalog-manager', client=http)
        result = covers.search(client, 'Miles Davis', 'Kind of Blue')
    assert len(result['covers']) == 1
    assert result['covers'][0]['artist'] == 'Miles Davis'
    assert len(result['errors']) == 1
    assert any('/release-group/' in r.url.path for r in calls)
    assert 'artist:' in calls[0].url.params['query'] and 'release:' in calls[0].url.params['query']


def test_cover_search_cancel_and_input_validation(store):
    cancel = Event()
    cancel.set()
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))) as http:
        client = MusicBrainz(store.profile, 'https://example.test', cancel, client=http)
        with pytest.raises(Cancelled):
            covers.search(client, 'Artist', 'Album')
        with pytest.raises(ValueError):
            covers.search(client, '', 'Album')


def test_online_and_local_cover_ui_and_help_language_switch(store, music, monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    root, paths, rows = music
    store.edit([rows[0]['id']], {'artist': 'Track artist', 'albumartist':'Album artist', 'album': 'Album title'})
    window = MainWindow(store)
    wait(lambda: not window.loading_library)
    window.table.selectRow(next(i for i, r in enumerate(window.model.rows) if r['id'] == rows[0]['id']))
    def accept_search(dialog):
        inputs = dialog.findChildren(QLineEdit)
        assert [x.text() for x in inputs] == ['Album artist', 'Album title']
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, 'exec', accept_search)
    calls = []
    monkeypatch.setattr(window, 'internet', lambda action, done, **kw: calls.append(kw))
    window.search_cover_dialog()
    assert calls[0]['contact'].startswith('https://github.com/') and calls[0]['with_progress']
    local = tmp_path / 'cover.png'
    local.write_bytes(picture())
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *_: (str(local), ''))
    applied = []
    monkeypatch.setattr(window, 'apply_artwork', lambda *args: applied.append(args))
    window.choose_local_cover()
    assert applied and applied[0][1].startswith(b'\xff\xd8')
    monkeypatch.setattr(QDialog, 'exec', lambda *_: QDialog.Accepted)
    window.cover_results(window.selected(), {'covers':[dict(data=picture(),release_id='id',album='Album',artist='Artist',date='',country='',source='Cover Art Archive',url='https://musicbrainz.org')], 'errors':[]})
    assert applied[-1][2] == 'id'
    def inspect_help(dialog):
        browser = dialog.findChild(QTextBrowser)
        languages = dialog.findChild(QComboBox)
        languages.setCurrentIndex(1)
        assert 'Playlist' in browser.toPlainText() and 'Troubleshooting' in browser.toPlainText()
        languages.setCurrentIndex(0)
        assert 'Rozwiązywanie problemów' in browser.toPlainText()
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, 'exec', inspect_help)
    window.show_help('pl')
    assert any(action.shortcut().toString() == 'F1' for menu in window.menuBar().actions() if menu.menu() for action in menu.menu().actions())
    assert all(help_path(lang).is_file() and help_path(lang).stat().st_size > 5000 for lang in ('pl', 'en'))
    window.close()
