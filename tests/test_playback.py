import os
import time
import wave
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QAudioBufferOutput, QMediaPlayer
from PySide6.QtTest import QTest

from music_catalog_manager.database.store import Store
from music_catalog_manager.database.store import normalized
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.ui.playback import PlaybackBar, timestamp
from music_catalog_manager.ui.window import MainWindow


def wait_until(predicate, timeout=5000):
    started = time.monotonic()
    while not predicate() and (time.monotonic() - started) * 1000 < timeout:
        QTest.qWait(10)
        time.sleep(0.001)
    assert predicate()


def test_real_decoding_all_formats(tmp_path, audio_factory):
    from music_catalog_manager.diagnostics import verify_playback
    app = QApplication.instance() or QApplication([])
    for ext in ('mp3', 'flac', 'm4a', 'ogg', 'opus', 'wav', 'wma', 'aiff'):
        audio_factory(tmp_path / 'audio' / ('sample.' + ext))
    result = verify_playback(tmp_path / 'audio')
    assert result['passed'], result
    assert len(result['formats']) == 8
    assert all(r['decoded_samples'] > 0 and r['ended'] for r in result['formats'])


def test_pause_seek_volume_queue_and_release(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / 'audio'
    root.mkdir()
    for name in ('one.wav', 'two.wav'):
        with wave.open(str(root / name), 'wb') as f:
            f.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
            f.writeframes(b'\0\0' * 44100 * 2)
    store = Store(tmp_path / 'profile')
    scan(store, store.add_root(root))
    rows = store.tracks()
    chosen = [rows[0]]
    bar = PlaybackBar(store, lambda: chosen, lambda: rows)
    bar.volume.setValue(0)
    bar.toggle()
    wait_until(lambda: bar.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
    wait_until(bar.player.isSeekable)
    bar.toggle()
    assert bar.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    bar.seek_to(500)
    wait_until(lambda: bar.player.position() >= 400)
    bar.volume.setValue(35)
    assert abs(bar.output.volume() - 0.35) < 0.001
    wait_until(lambda: store.setting('volume') == 35)
    bar.output.setMuted(True)
    bar.toggle()
    assert bar.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    bar.next()
    assert normalized(bar.player.source().toLocalFile()) == rows[1]['path']
    wait_until(lambda: bar.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
    bar.toggle()
    assert bar.current == 1
    assert bar.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    bar.previous()
    assert bar.current == 0
    bar.stop()
    assert bar.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
    assert bar.player.position() == 0
    bar.set_busy(True)
    bar.toggle()
    assert bar.player is None
    assert not bar.play_button.isEnabled()
    bar.set_busy(False)
    assert bar.play_button.isEnabled()
    assert timestamp(125000) == '2:05'
    bar.close()


def test_missing_file_and_double_click(tmp_path, audio_factory):
    app = QApplication.instance() or QApplication([])
    path = audio_factory(tmp_path / 'audio' / 'sample.wav')
    store = Store(tmp_path / 'profile')
    store.set_setting('volume', 0)
    scan(store, store.add_root(path.parent))
    window = MainWindow(store)
    wait_until(lambda: not window.loading_library)
    window.show()
    app.processEvents()
    index = window.proxy.index(0, 0)
    window.table.selectRow(0)
    # Invoke the same signal used by a native double click, including proxy mapping.
    window.table.doubleClicked.emit(index)
    wait_until(lambda: window.worker is None and window.playback.player is not None)
    assert window.playback.player is not None
    assert window.playback.queue[0]['id'] == store.tracks()[0]['id']
    window.playback.release()
    wait_until(lambda: window.playback.retiring == 0)
    path.unlink()
    window.play_index(index)
    wait_until(lambda: window.worker is None)
    assert window.playback.last_error
    assert window.model.rowCount() == 1
    window.close()


def test_corrupt_file_reports_error_without_crashing(tmp_path, audio_factory):
    app = QApplication.instance() or QApplication([])
    path = audio_factory(tmp_path / 'audio' / 'sample.wav')
    store = Store(tmp_path / 'profile')
    scan(store, store.add_root(path.parent))
    rows = store.tracks()
    path.write_bytes(b'broken file')
    bar = PlaybackBar(store, lambda: rows, lambda: rows)
    bar.volume.setValue(0)
    bar.toggle()
    wait_until(lambda: bool(bar.last_error))
    assert bar.player.error() != QMediaPlayer.Error.NoError
    bar.release()
    bar.close()


def test_write_waits_for_playback_to_release_file(tmp_path, audio_factory):
    from music_catalog_manager.services import metadata
    app = QApplication.instance() or QApplication([])
    path = audio_factory(tmp_path / 'audio' / 'sample.mp3')
    store = Store(tmp_path / 'profile')
    store.set_setting('volume', 0)
    scan(store, store.add_root(path.parent))
    window = MainWindow(store)
    wait_until(lambda: not window.loading_library)
    window.table.selectRow(0)
    window.playback.toggle()
    wait_until(lambda: window.worker is None)
    window.write_changes(window.selected(), {'title': 'Po odtworzeniu'}, disk=True)
    assert not window.playback.play_button.isEnabled()
    wait_until(lambda: window.worker is None)
    assert metadata.read(path)['tags']['title'] == 'Po odtworzeniu'
    assert window.playback.play_button.isEnabled()
    assert window.playback.player is None
    window.close()


def test_selected_queue_advances_and_stops_at_end(tmp_path, audio_factory):
    app = QApplication.instance() or QApplication([])
    for i in range(3):
        audio_factory(tmp_path / 'audio' / (str(i) + '.wav'))
    store = Store(tmp_path / 'profile')
    scan(store, store.add_root(tmp_path / 'audio'))
    rows = store.tracks()
    chosen = [rows[2], rows[0]]
    bar = PlaybackBar(store, lambda: chosen, lambda: rows)
    bar.volume.setValue(0)
    assert bar.ensure_player()
    output = QAudioBufferOutput(bar.player)
    bar.player.setAudioBufferOutput(output)
    bar.player.setAudioOutput(None)
    bar.play_track(rows[2])
    wait_until(lambda: bar.current == 1 and bar.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia)
    assert [t['id'] for t in bar.queue] == [rows[2]['id'], rows[0]['id']]
    assert bar.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
    assert not bar.next_button.isEnabled()
    bar.release()
    wait_until(lambda: bar.retiring == 0)
    bar.close()


def test_diagnostic_returns_when_called_from_qt_callback(tmp_path, audio_factory):
    from music_catalog_manager.diagnostics import verify_playback
    app = QApplication.instance() or QApplication([])
    audio_factory(tmp_path / 'audio' / 'sample.wav')
    loop = QEventLoop()
    results = []
    def verify():
        results.append(verify_playback(tmp_path / 'audio'))
        loop.quit()
    QTimer.singleShot(0, verify)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    assert results and results[0]['passed']


@pytest.mark.parametrize('scope', ['album', 'folder'])
def test_play_new_album_or_folder_replaces_finished_single_track_queue(store, tmp_path, audio_factory, scope):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / 'Selected'
    for i in range(3):
        audio_factory(root / f'{i}.wav')
    audio_factory(tmp_path / 'Other' / 'other.wav')
    root_id = store.add_root(root)
    scan(store, root_id)
    scan(store, store.add_root(tmp_path / 'Other'))
    rows = [row for row in store.tracks() if row['root_id'] == root_id]
    for i, row in enumerate(rows):
        store.edit([row['id']], {'title': f'Track {i + 1}', 'album': 'Selected album'})
    store.set_setting('volume', 0)
    window = MainWindow(store)
    try:
        wait_until(lambda: not window.loading_library)
        window.search.setText('Track 1')
        wait_until(lambda: not window.loading_library and window.model.rowCount() == 1)
        window.table.selectRow(0)
        bar = window.playback
        # Exercise real decoding without depending on a physical Windows audio device.
        assert bar.ensure_player()
        decoded_output = QAudioBufferOutput(bar.player)
        bar.player.setAudioBufferOutput(decoded_output)
        bar.player.setAudioOutput(None)
        bar.toggle()
        wait_until(lambda: bar.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia)
        assert len(bar.queue) == 1
        # Changing the scope must build its full queue, including other pages.
        window.page_size = 1
        window.search.clear()
        key, value = ('album', 'Selected album') if scope == 'album' else ('root_id', str(root_id))
        window.combos[key].setCurrentIndex(window.combos[key].findData(value))
        wait_until(lambda: not window.loading_library)
        window.table.selectRow(0)
        played = []
        bar.player.sourceChanged.connect(lambda url: played.append(normalized(url.toLocalFile())))
        bar.toggle()
        wait_until(lambda: window.worker is None)
        assert [row['id'] for row in bar.queue] == [row['id'] for row in rows]
        wait_until(lambda: bar.current == 2 and bar.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia)
        assert played[-2:] == [row['path'] for row in rows[1:]]
        assert bar.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
        assert not bar.next_button.isEnabled()
    finally:
        window.close()
        wait_until(lambda: window.playback.retiring == 0)


@pytest.mark.parametrize('mode,expected', [('one', [0, 0, 0]), ('all', [0, 1, 0]), ('off', [0, 1, 2])])
def test_real_queue_repeats_and_consecutive_identical_sources(store, tmp_path, audio_factory, mode, expected):
    app = QApplication.instance() or QApplication([])
    for i in range(2):
        audio_factory(tmp_path / 'audio' / f'{i}.wav')
    scan(store, store.add_root(tmp_path / 'audio'))
    rows = store.tracks()
    bar = PlaybackBar(store, lambda: [], lambda: rows)
    try:
        assert bar.ensure_player()
        output = QAudioBufferOutput(bar.player)
        bar.player.setAudioBufferOutput(output)
        bar.player.setAudioOutput(None)
        bar.repeat.setCurrentIndex(bar.repeat.findData(mode))
        ended = []
        def finished(status):
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                ended.append(bar.current)
                if len(ended) == 3:
                    bar.stop()
        bar.player.mediaStatusChanged.connect(finished)
        queue = [rows[0], rows[0], rows[1]] if mode == 'off' else rows
        bar.set_queue(queue)
        wait_until(lambda: len(ended) == 3)
        QTest.qWait(30)
        assert ended == expected
        assert not bar.end_timer.isActive()
        assert bar.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
    finally:
        bar.release()
        wait_until(lambda: bar.retiring == 0)
        bar.close()


def test_changed_scope_ignores_old_selection_and_can_play_empty_view(store, tmp_path, audio_factory):
    app = QApplication.instance() or QApplication([])
    for i in range(3):
        audio_factory(tmp_path / 'audio' / f'{i}.wav')
    scan(store, store.add_root(tmp_path / 'audio'))
    rows = store.tracks()
    chosen, visible = [rows[0]], rows[:1]
    context = {'folder': 'old'}
    bar = PlaybackBar(store, lambda: chosen, lambda: visible, context=lambda: context)
    try:
        assert bar.ensure_player()
        output = QAudioBufferOutput(bar.player)
        bar.player.setAudioBufferOutput(output)
        bar.player.setAudioOutput(None)
        bar.toggle()
        wait_until(lambda: bar.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia)
        context['folder'] = 'new'
        visible = rows[1:]
        bar.toggle()
        assert [row['id'] for row in bar.queue] == [row['id'] for row in visible]
        wait_until(lambda: bar.current == 1 and bar.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia)
        context['folder'] = 'empty'
        visible = []
        bar.toggle()
        assert bar.queue == [] and bar.player is None
    finally:
        bar.release()
        wait_until(lambda: bar.retiring == 0)
        bar.close()


def test_skip_all_missing_tracks_terminates_even_when_repeating(store, tmp_path):
    app = QApplication.instance() or QApplication([])
    ids = []
    with store.connection() as db:
        for i in range(3):
            ids.append(db.execute('INSERT INTO tracks(path) VALUES(?)', (str(tmp_path / f'missing-{i}.wav'),)).lastrowid)
    rows = store.tracks()
    store.set_setting('skip_unavailable', True)
    bar = PlaybackBar(store, lambda: [], lambda: rows)
    bar.repeat.setCurrentIndex(bar.repeat.findData('all'))
    try:
        bar.set_queue(rows)
        wait_until(lambda: len(bar.skipped) == 3)
        QTest.qWait(50)
        assert len(bar.skipped) == 3
        assert len(bar.queue) == 3
        assert bar.player is None
    finally:
        bar.release()
        bar.close()


def test_enqueue_preserves_playback_and_duplicate_order(store, tmp_path, audio_factory):
    app = QApplication.instance() or QApplication([])
    for i in range(3):
        audio_factory(tmp_path / 'audio' / f'{i}.wav')
    scan(store, store.add_root(tmp_path / 'audio'))
    rows = store.tracks()
    bar = PlaybackBar(store, lambda: [], lambda: rows)
    try:
        assert bar.ensure_player()
        output = QAudioBufferOutput(bar.player)
        bar.player.setAudioBufferOutput(output)
        bar.player.setAudioOutput(None)
        bar.set_queue(rows[:1])
        source = bar.player.source()
        bar.enqueue([rows[1], rows[1]])
        bar.enqueue([rows[2]], next_up=True)
        assert bar.player.source() == source and bar.current == 0
        assert [r['id'] for r in bar.queue] == [rows[0]['id'], rows[2]['id'], rows[1]['id'], rows[1]['id']]
    finally:
        bar.release()
        wait_until(lambda: bar.retiring == 0)
        bar.close()
