"""Explicit packaged acceptance check. Writes only to an isolated temp directory."""
import io
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from music_catalog_manager.database.store import Store
from music_catalog_manager.services import backup, metadata
from music_catalog_manager.services.scanner import file_hash, scan


def verify_audio(source):
    source = Path(source).resolve()
    files = [p for p in source.iterdir() if p.suffix.lower() in metadata.EXTENSIONS]
    if not files:
        raise ValueError('No audio fixtures found')
    originals = {p: file_hash(p) for p in files}
    with tempfile.TemporaryDirectory(prefix='mcm-acceptance-') as folder:
        folder = Path(folder)
        music = folder / 'audio'
        music.mkdir()
        for p in files:
            shutil.copy2(p, music / p.name)
        store = Store(folder / 'profile')
        rid = store.add_root(music)
        stats = scan(store, rid, hashes=True)
        assert stats['new'] == len(files) and stats['errors'] == 0, stats
        assert scan(store, rid)['new'] == 0
        image = io.BytesIO()
        Image.new('RGB', (20, 20), '#538fe6').save(image, 'PNG')
        written = []
        for track in store.tracks():
            if metadata.writable(track['path']):
                metadata.write_safe(track['path'], {'title': 'Żółć — packaged test'}, image.getvalue())
                result = metadata.read(track['path'])
                assert result['tags']['title'] == 'Żółć — packaged test'
                assert result['image']
                written.append(track['format'])
        store.edit([t['id'] for t in store.tracks()], {'title': 'Fixture'})
        target = folder / 'backup.zip'
        backup.create(store, target)
        other = Store(folder / 'restored')
        backup.restore(other, target)
        assert len(other.tracks()) == len(files)
    assert all(file_hash(path) == before for path, before in originals.items())
    return {'scanned_formats': sorted(p.suffix for p in files), 'written_formats': sorted(written),
            'backup_restore': True, 'originals_unchanged': True}
