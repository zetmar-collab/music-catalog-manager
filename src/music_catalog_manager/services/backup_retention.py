"""Only explicitly selected ordinary profile backups can be removed."""
from pathlib import Path
from zipfile import BadZipFile
from music_catalog_manager.services import backup


def candidates(store, keep=5):
    if not isinstance(keep, int) or keep < 1:
        raise ValueError('Keep at least one backup')
    entries = []
    for path in store.profile.glob('*.zip'):
        if path.name.startswith('before-') or path.is_symlink():
            continue
        try:
            backup.describe(path)
            entries.append(path)
        except (OSError, ValueError, KeyError, BadZipFile):
            continue
    return sorted(entries, key=lambda p: p.stat().st_mtime_ns, reverse=True)[keep:]


def remove(store, paths, confirmed=False):
    if not confirmed:
        raise ValueError('Confirm the exact backup list before removal')
    approved = []
    for value in paths:
        path = Path(value)
        if path.is_symlink() or path.resolve().parent != store.profile.resolve() or path.suffix != '.zip' or path.name.startswith('before-'):
            raise ValueError('Protected backup path')
        backup.inspect(path)
        approved.append(path)
    for path in approved:
        path.unlink()
    return len(approved)
