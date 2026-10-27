from music_catalog_manager.database.store import Store


def test_schema_settings(tmp_path):
    store = Store(tmp_path)
    store.set_setting('language', 'pl')
    assert Store(tmp_path).setting('language') == 'pl'
    assert store.add_root(tmp_path) == store.add_root(tmp_path)
    with store.connection() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2


def test_undo(tmp_path):
    store = Store(tmp_path)
    with store.connection() as db:
        tid = db.execute("INSERT INTO tracks(path) VALUES('test')").lastrowid
    store.edit([tid], {'title': 'Żółć'})
    assert store.track(tid)['tags']['title'] == 'Żółć'
    assert store.undo()
    assert 'title' not in store.track(tid)['tags']
