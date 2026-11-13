"""Session records include identity hints so reused SQLite IDs cannot play new files."""
import json
from typing import Any


def save(store, queue, current, position, context=None):
    records = [{k: r.get(k) for k in ('id', 'path', 'file_key', 'sha256')} for r in queue]
    store.set_setting('playback_session', dict(queue=records, current=current,
                      position=max(0, int(position)), context=context))


def load(store, cancel=None):
    data = store.setting('playback_session', {})
    if not isinstance(data, dict):
        return [], -1, 0, None
    with store.connection() as db:
        rows = {r['id']: dict(r) for r in db.execute('SELECT t.*,a.path AS artwork FROM tracks t LEFT JOIN artwork a ON a.track_id=t.id')}
    queue: list[dict[str, Any]] = []
    current = -1
    for index, hint in enumerate(data.get('queue', [])):
        if cancel is not None and cancel.is_set():
            return [], -1, 0, None
        row = rows.get(hint.get('id'))
        if row is None:
            continue
        same_identity = (hint.get('file_key') and hint['file_key'] == row['file_key']) or (hint.get('sha256') and hint['sha256'] == row['sha256'])
        if not same_identity and (hint.get('path') != row['path'] or hint.get('file_key') != row['file_key']):
            continue
        if index == data.get('current'):
            current = len(queue)
        row = dict(row)
        row['tags'] = json.loads(row['tags'])
        queue.append(row)
    return queue, (current if current >= 0 else (0 if queue else -1)), (data.get('position', 0) if current >= 0 else 0), data.get('context')
