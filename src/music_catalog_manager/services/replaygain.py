"""Read-only ReplayGain adjustment; never analyze or rewrite audio samples."""
import math
import re


def multiplier(tags, mode='off'):
    if mode not in ('track', 'album'):
        return 1.0
    prefix = 'replaygain_' + mode
    raw = tags.get(prefix + '_gain', '')
    if not raw and mode == 'album':
        prefix, raw = 'replaygain_track', tags.get('replaygain_track_gain', '')
    try:
        gain = float(re.sub(r'\s*dB\s*$', '', str(raw), flags=re.I))
        if not math.isfinite(gain) or not -60 <= gain <= 60:
            return 1.0
        factor = 10 ** (gain / 20)
        peak = float(tags.get(prefix + '_peak') or 0)
        if math.isfinite(peak) and peak > 0:
            factor = min(factor, 1 / peak)
        return factor
    except (ValueError, TypeError, OverflowError):
        return 1.0
