"""Allowlisted, parameterized smart playlist rules stored without schema changes."""
import json
import uuid
from music_catalog_manager.database.store import WRITABLE_FIELDS

FIELDS = (*WRITABLE_FIELDS, 'format', 'duration', 'available', 'dirty', 'artwork')
OPERATORS = ('contains', 'equals', 'empty', 'greater', 'less')


def compile_rules(definition):
    rules = definition.get('rules', [])
    mode = definition.get('mode', 'all')
    if mode not in ('all', 'any') or not 1 <= len(rules) <= 20:
        raise ValueError('A smart playlist needs 1–20 valid rules')
    expressions: list[str] = []
    params: list[str | float] = []
    for rule in rules:
        field, operator = rule.get('field'), rule.get('operator')
        value = rule.get('value', '')
        if field not in FIELDS or operator not in OPERATORS or not isinstance(value, str) or len(value) > 1000:
            raise ValueError('Invalid smart playlist rule')
        key = f't.{field}' if field in ('format', 'duration', 'available', 'dirty') else f"coalesce(json_extract(t.tags,'$.{field}'),'')"
        if field == 'artwork':
            key = "coalesce(a.path,'')"
        if operator == 'empty':
            expressions.append(f"coalesce(CAST({key} AS TEXT),'')=''")
        elif operator in ('greater', 'less'):
            import math
            number = float(value)
            if not math.isfinite(number):
                raise ValueError('Invalid numeric rule')
            expressions.append(f"CAST({key} AS REAL){'>' if operator == 'greater' else '<'}?")
            params.append(number)
        elif operator == 'contains':
            expressions.append(f'instr(CASEFOLD(CAST({key} AS TEXT)),?)>0')
            params.append(value.casefold())
        else:
            expressions.append(f'CASEFOLD(CAST({key} AS TEXT))=?')
            params.append(value.casefold())
    return '(' + (' AND ' if mode == 'all' else ' OR ').join(expressions) + ')', params


def lists(store):
    return store.setting('smart_playlists', [])


def save(store, name, mode, rules, playlist_id=None):
    definition = dict(id=playlist_id or 'smart:' + uuid.uuid4().hex, name=name.strip(), mode=mode, rules=rules)
    if not definition['name'] or len(definition['name']) > 200:
        raise ValueError('Playlist name is required (maximum 200 characters)')
    compile_rules(definition)
    with store.connection() as db:
        row = db.execute("SELECT value FROM settings WHERE key='smart_playlists'").fetchone()
        items = json.loads(row[0]) if row else []
        items = [item for item in items if item['id'] != definition['id']]
        items.append(definition)
        db.execute("INSERT OR REPLACE INTO settings VALUES('smart_playlists',?)", (json.dumps(items),))
    return definition['id']


def remove(store, playlist_id):
    store.set_setting('smart_playlists', [item for item in lists(store) if item['id'] != playlist_id])


def get(store, playlist_id):
    return next(item for item in lists(store) if item['id'] == playlist_id)
