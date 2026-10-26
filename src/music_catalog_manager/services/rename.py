import json
import os
import re
import string
from pathlib import Path

from music_catalog_manager.database.store import normalized

RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{n}' for p in ('COM', 'LPT') for n in range(1, 10)}


def safe_name(value, extension):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip().rstrip('. ')
    if not value:
        raise ValueError('Empty filename')
    if value.split('.')[0].upper() in RESERVED:
        value = '_' + value
    # UTF-16 code units, leave room for extension and filesystem bookkeeping.
    while len((value + extension).encode('utf-16-le')) // 2 > 240:
        value = value[:-1]
    return value + extension


def preview(tracks, template):
    if len(template) > 256:
        raise ValueError('Template too long')
    result, targets = [], set()
    for track in tracks:
        source = Path(track['path'])
        values = dict(track['tags'])
        try:
            values['track'] = int(values.get('tracknumber', '').split('/')[0] or 0)
        except ValueError:
            values['track'] = 0
        for _, key, spec, conversion in string.Formatter().parse(template):
            if key and (key not in values or '.' in key or '[' in key or conversion):
                raise ValueError('Unknown template field')
            if spec and (key != 'track' or spec not in ('02', '03', '04', '02d', '03d', '04d')):
                raise ValueError('Unsupported template formatting')
        target = source.with_name(safe_name(template.format_map(values), source.suffix))
        norm = normalized(target)
        if norm in targets or (target.exists() and normalized(source) != norm):
            raise FileExistsError(str(target))
        targets.add(norm)
        result.append((track['id'], source, target))
    return result


def execute(store, plan):
    # Preflight every destination before the first mutation.
    targets = set()
    for tid, source, target in plan:
        if source.parent != target.parent or source.suffix != target.suffix:
            raise ValueError('Folder and extension must remain unchanged')
        norm = normalized(target)
        if norm in targets or (target.exists() and normalized(source) != norm):
            raise FileExistsError(str(target))
        targets.add(norm)
        if not source.is_file():
            raise FileNotFoundError(str(source))
    moved = []
    try:
        with store.connection() as db:
            for tid, source, target in plan:
                if source == target:
                    continue
                # Windows rename never overwrites an existing destination.
                if target.exists():
                    raise FileExistsError(str(target))
                os.rename(source, target)
                moved.append((source, target))
                db.execute('UPDATE tracks SET path=? WHERE id=?', (normalized(target), tid))
                db.execute('INSERT INTO operation_history(kind,track_id,before_data,after_data) VALUES(?,?,?,?)',
                           ('rename', tid, json.dumps(str(source)), json.dumps(str(target))))
    except Exception:
        for source, target in reversed(moved):
            if not source.exists():
                os.rename(target, source)
        raise
