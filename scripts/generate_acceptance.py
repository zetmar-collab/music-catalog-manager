import shutil
import subprocess
import wave
from pathlib import Path

folder = Path(__file__).resolve().parents[1] / 'build/acceptance-audio'
folder.mkdir(parents=True, exist_ok=False)
wav = folder / 'sample.wav'
with wave.open(str(wav), 'wb') as f:
    f.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
    f.writeframes(b'\0\0' * 4410)
ffmpeg = shutil.which('ffmpeg')
if not ffmpeg:
    raise RuntimeError('ffmpeg required')
for ext in ('mp3', 'flac', 'm4a', 'ogg', 'opus', 'wma', 'aiff'):
    subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', str(wav), str(folder / ('sample.' + ext))], check=True)
