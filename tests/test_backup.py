import io
import json
import zipfile
from pathlib import Path
import pytest
from PIL import Image
from music_catalog_manager.database.store import Store
from music_catalog_manager.services import backup
from music_catalog_manager.services.artwork import cache_image
from music_catalog_manager.services.scanner import scan


def test_real_restore_separate_profile(store, tmp_path, audio_factory):
    folder = tmp_path / 'music'
    audio_factory(folder / 'test.wav')
    scan(store, store.add_root(folder))
    tid = store.tracks()[0]['id']
    store.edit([tid], {'title': 'Łódź'})
    store.set_setting('language', 'pl')
    store.set_setting('theme', 'dark')
    image = io.BytesIO()
    Image.new('RGB', (16, 16)).save(image, 'PNG')
    cache_image(store, tid, image.getvalue())
    target = tmp_path / 'backup.zip'
    backup.create(store, target)
    manifest = backup.inspect(target)
    assert not manifest['audio_included']
    other = Store(tmp_path / 'other')
    other.set_setting('theme', 'light')
    safety = backup.restore(other, target)
    assert safety.exists()
    assert other.tracks()[0]['tags']['title'] == 'Łódź'
    assert other.setting('language') == 'pl'
    assert other.setting('theme') == 'dark'
    assert (other.cache / other.tracks()[0]['artwork']).exists()
    with other.connection() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert len(db.execute("SELECT * FROM sqlite_master WHERE type='index'").fetchall()) >= 4
    with pytest.raises(FileExistsError):
        backup.create(store, target)
    moved = tmp_path / 'nowa lokalizacja'
    folder.rename(moved)
    other.relink(other.roots()[0]['id'], moved)
    assert Path(other.tracks()[0]['path']).exists()


def test_corruption_and_zip_slip_preserve_current(store, tmp_path):
    store.set_setting('keep', True)
    target = tmp_path / 'bad.zip'
    for filename in ('../escape', 'C:/escape', 'artwork/../../escape', 'evil.txt'):
        with zipfile.ZipFile(target, 'w') as archive:
            archive.writestr(filename, 'bad')
            archive.writestr('manifest.json', '{}')
        with pytest.raises(ValueError):
            backup.restore(store, target)
        assert store.setting('keep') is True
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('library.sqlite', 'damaged')
        archive.writestr('manifest.json', json.dumps({'schema': 1, 'files': {'library.sqlite': 'wrong'}}))
    with pytest.raises(ValueError, match='Checksum'):
        backup.restore(store, target)
