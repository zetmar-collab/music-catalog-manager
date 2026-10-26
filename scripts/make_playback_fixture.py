import wave
from pathlib import Path

folder = Path(__file__).resolve().parents[1] / 'build/playback-smoke-audio'
folder.mkdir(parents=True, exist_ok=True)
with wave.open(str(folder / 'silence.wav'), 'wb') as out:
    out.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
    out.writeframes(b'\0\0' * 4410)
