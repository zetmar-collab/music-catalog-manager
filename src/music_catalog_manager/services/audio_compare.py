"""Local, bounded audio similarity. Scores suggest review, never deletion."""
import array
import math
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

from music_catalog_manager.services.musicbrainz import Cancelled


def decode(path, cancel=None, seconds=60):
    decoder = QAudioDecoder()
    requested = QAudioFormat()
    requested.setSampleRate(8000)
    requested.setChannelCount(1)
    requested.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    decoder.setAudioFormat(requested)
    loop = QEventLoop()
    samples, errors = [], []
    sample_rate = 8000
    def read():
        nonlocal sample_rate
        buffer = decoder.read()
        fmt = buffer.format()
        sample_rate = fmt.sampleRate()
        kind = {QAudioFormat.SampleFormat.Int16: ('h', 32768), QAudioFormat.SampleFormat.Int32: ('i', 2147483648),
                QAudioFormat.SampleFormat.Float: ('f', 1), QAudioFormat.SampleFormat.UInt8: ('B', 128)}.get(fmt.sampleFormat())
        if not kind or not fmt.channelCount() or not sample_rate:
            errors.append('Unsupported decoded audio format')
            loop.quit()
            return
        values = array.array(kind[0])
        values.frombytes(bytes(buffer.data()))
        channels = fmt.channelCount()
        for i in range(0, len(values) - channels + 1, channels):
            value = sum(values[i:i + channels]) / channels
            if kind[0] == 'B':
                value -= 128
            samples.append(value / kind[1])
            if len(samples) >= sample_rate * seconds:
                loop.quit()
                break
    def error(*_):
        errors.append(decoder.errorString())
        loop.quit()
    def cancelled():
        if cancel is not None and cancel.is_set():
            loop.quit()
    decoder.bufferReady.connect(read)
    decoder.finished.connect(loop.quit)
    decoder.error.connect(error)
    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(cancelled)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(lambda: (errors.append('Audio decoding timed out'), loop.quit()))
    timer.start()
    deadline.start(120000)
    decoder.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
    decoder.start()
    loop.exec()
    decoder.stop()
    timer.stop()
    deadline.stop()
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if errors:
        raise ValueError(errors[0])
    return samples, sample_rate


def fingerprint(path, cancel=None):
    samples, rate = decode(path, cancel)
    frames = []
    step = max(1, rate // 2)
    for offset in range(0, len(samples) - step + 1, step):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        block = samples[offset:offset + min(step, 2048)]
        rms = math.sqrt(sum(x*x for x in block) / len(block))
        if rms < 0.0001:
            frames.append(None)
            continue
        features = []
        for frequency in (110, 220, 440, 660, 880, 1320, 1760, 2640):
            coefficient = 2 * math.cos(2 * math.pi * frequency / rate)
            s1 = s2 = 0.0
            for value in block:
                s0 = value + coefficient*s1 - s2
                s2, s1 = s1, s0
            features.append(math.sqrt(max(0, s1*s1 + s2*s2 - coefficient*s1*s2)))
        norm = math.sqrt(sum(x*x for x in features))
        frames.append([x / norm for x in features] if norm > 1e-10 else None)
    if sum(f is not None for f in frames) < 4:
        raise ValueError('Insufficient non-silent audio (at least two seconds required)')
    return frames


def similarity(left, right):
    scores = []
    for shift in range(-2, 3):
        pairs = [(a, right[i + shift]) for i, a in enumerate(left) if a is not None and 0 <= i + shift < len(right) and right[i + shift] is not None]
        if len(pairs) >= 4:
            score = sum(sum(x*y for x, y in zip(a, b)) for a, b in pairs) / len(pairs)
            coverage = len(pairs) / max(len(left), len(right))
            scores.append(max(0, min(1, score * coverage)))
    return round(100 * max(scores, default=0), 1)


def compare(rows, cancel=None, progress=None):
    if not 2 <= len(rows) <= 20:
        raise ValueError('Select between 2 and 20 tracks for audio comparison')
    signatures, errors = {}, []
    for i, row in enumerate(rows):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        try:
            signatures[row['id']] = fingerprint(row['path'], cancel)
        except Cancelled:
            raise
        except Exception as exc:
            errors.append({'path': row['path'], 'error': str(exc)})
        if progress:
            progress({'decoded': i + 1, 'total': len(rows)})
    results = []
    for i, left in enumerate(rows):
        for right in rows[i + 1:]:
            if left['id'] in signatures and right['id'] in signatures:
                results.append({'left': left['path'], 'right': right['path'], 'score': similarity(signatures[left['id']], signatures[right['id']])})
    return sorted(results, key=lambda r: -r['score']), errors
