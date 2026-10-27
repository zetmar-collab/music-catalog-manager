import shutil
import subprocess
import wave
from pathlib import Path
import pytest
from music_catalog_manager.database.store import Store
from music_catalog_manager.paths import windows_path


@pytest.fixture(autouse=True)
def fail_on_unexpected_window_errors(monkeypatch):
    """Report background failures instead of leaving unattended tests in a modal dialog."""
    from music_catalog_manager.ui.window import MainWindow
    errors = []
    monkeypatch.setattr(MainWindow, 'error', lambda self, detail: errors.append(str(detail)))
    yield
    assert not errors, 'Unexpected background error: ' + '\n'.join(errors)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'profile')


@pytest.fixture(scope='session')
def audio_factory(tmp_path_factory):
    folder = tmp_path_factory.mktemp('fixtures')
    wav = folder / 'source.wav'
    with wave.open(str(wav), 'wb') as f:
        f.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
        f.writeframes(b'\x00\x00' * 4410)
    ffmpeg = shutil.which('ffmpeg')
    def make(path):
        path = Path(windows_path(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == '.wav':
            shutil.copy2(wav, path)
        else:
            if not ffmpeg:
                pytest.skip('ffmpeg is required to generate audio fixtures')
            subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', str(wav), str(path)], check=True, capture_output=True)
        return path
    return make
