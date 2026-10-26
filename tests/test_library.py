import json
from PySide6.QtCore import Qt
from music_catalog_manager.ui.window import TrackModel, Filter


def test_unicode_filter_sort_and_duplicates():
    model = TrackModel()
    rows = []
    for i, artist in enumerate(('Żółć', 'Łódź', 'ŻÓŁĆ')):
        rows.append(dict(id=i, tags={'artist': artist, 'title': str(i)}, path=f'{i}.mp3',
            format='MP3', root_id=1, duration=3-i, sha256='same' if i != 1 else 'other', available=1, dirty=0))
    model.replace(rows)
    proxy = Filter()
    proxy.setSourceModel(model)
    proxy.query = 'żółć'
    proxy.invalidate()
    assert proxy.rowCount() == 2
    proxy.filters = {'format': 'MP3'}
    proxy.sort(5, Qt.AscendingOrder)
    assert proxy.index(0, 0).data() == '2'
    proxy.query = ''
    proxy.filters = {'artist': 'łÓDŹ'}
    proxy.invalidate()
    assert proxy.rowCount() == 1
    proxy.filters = {}
    proxy.duplicates = True
    proxy.hashes = {'same'}
    proxy.invalidate()
    assert proxy.rowCount() == 2
