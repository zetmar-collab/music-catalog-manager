"""Explicit packaged acceptance check. Writes only to an isolated temp directory."""
import io
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from music_catalog_manager.database.store import Store
from music_catalog_manager.services import backup, metadata
from music_catalog_manager.services.scanner import file_hash, scan


def verify_audio(source):
    source = Path(source).resolve()
    files = [p for p in source.iterdir() if p.suffix.lower() in metadata.EXTENSIONS]
    if not files:
        raise ValueError('No audio fixtures found')
    originals = {p: file_hash(p) for p in files}
    with tempfile.TemporaryDirectory(prefix='mcm-acceptance-') as folder:
        folder = Path(folder)
        music = folder / 'audio'
        music.mkdir()
        for p in files:
            shutil.copy2(p, music / p.name)
        store = Store(folder / 'profile')
        rid = store.add_root(music)
        stats = scan(store, rid, hashes=True)
        assert stats['new'] == len(files) and stats['errors'] == 0, stats
        assert scan(store, rid)['new'] == 0
        image = io.BytesIO()
        Image.new('RGB', (20, 20), '#538fe6').save(image, 'PNG')
        written = []
        for track in store.tracks():
            if metadata.writable(track['path']):
                metadata.write_safe(track['path'], {'title': 'Żółć — packaged test'}, image.getvalue())
                result = metadata.read(track['path'])
                assert result['tags']['title'] == 'Żółć — packaged test'
                assert result['image']
                written.append(track['format'])
        store.edit([t['id'] for t in store.tracks()], {'title': 'Fixture'})
        target = folder / 'backup.zip'
        backup.create(store, target)
        other = Store(folder / 'restored')
        backup.restore(other, target)
        assert len(other.tracks()) == len(files)
    assert all(file_hash(path) == before for path, before in originals.items())
    return {'scanned_formats': sorted(p.suffix for p in files), 'written_formats': sorted(written),
            'backup_restore': True, 'originals_unchanged': True}


def verify_playback(source):
    """Decode synthetic fixtures through Qt Multimedia with the output muted."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtMultimedia import QAudioBufferOutput, QMediaPlayer
    from music_catalog_manager.ui.playback import PlaybackBar
    reports = []
    with tempfile.TemporaryDirectory(prefix='mcm-playback-') as folder:
        store = Store(folder)
        scan(store, store.add_root(source))
        bar = PlaybackBar(store, lambda: [], lambda: [])
        bar.volume.setValue(0)
        if not bar.ensure_player():
            raise RuntimeError(bar.last_error)
        output = QAudioBufferOutput(bar.player)
        bar.player.setAudioBufferOutput(output)
        for track in store.tracks():
            report = {'format': track['format'], 'decoded_samples': 0, 'ended': False, 'errors': []}
            loop = QEventLoop()
            def buffer_ready(buffer):
                report['decoded_samples'] += buffer.sampleCount()
            def status_changed(status):
                if status == QMediaPlayer.MediaStatus.EndOfMedia:
                    report['ended'] = True
                    loop.quit()
            def failed(error, detail):
                report['errors'].append(detail)
                loop.quit()
            output.audioBufferReceived.connect(buffer_ready)
            bar.player.mediaStatusChanged.connect(status_changed)
            bar.player.errorOccurred.connect(failed)
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(loop.quit)
            timeout.start(5000)
            bar.play_track(track)
            loop.exec()
            timeout.stop()
            report['passed'] = report['decoded_samples'] > 0 and report['ended'] and not report['errors']
            reports.append(report)
            output.audioBufferReceived.disconnect(buffer_ready)
            bar.player.mediaStatusChanged.disconnect(status_changed)
            bar.player.errorOccurred.disconnect(failed)
            bar.stop()
        bar.release()
        # Deferred deletion belongs to the caller's event loop. Waiting in a
        # nested loop here deadlocks when this diagnostic runs from a QTimer.
        bar.when_released(bar.deleteLater)
    return {'passed': bool(reports) and all(r['passed'] for r in reports), 'formats': reports, 'audible_output_verified': False}
