"""Background reconciliation supplements filesystem notifications and detects missed writes."""
import os
from pathlib import Path
from music_catalog_manager.database.store import normalized
from music_catalog_manager.paths import windows_path
from music_catalog_manager.services.backup import check_cancel
from music_catalog_manager.services.metadata import EXTENSIONS


def snapshot(roots, previous=None, cancel=None):
    state, errors = {}, []
    for root in roots:
        base = normalized(root['path'])
        def unreadable(exc):
            errors.append(str(exc))
            # Keep the old subtree when access is denied: don't invent removals.
            if previous and exc.filename and not isinstance(exc, (FileNotFoundError, NotADirectoryError)):
                prefix = normalized(exc.filename)
                state.update({p: value for p, value in previous.items() if Path(windows_path(p)).is_relative_to(Path(windows_path(prefix)))})
        for folder, dirs, files in os.walk(windows_path(base), followlinks=False, onerror=unreadable):
            check_cancel(cancel)
            dirs[:] = [d for d in dirs if not Path(folder, d).is_symlink() and not Path(folder, d).is_junction()]
            state[normalized(folder)] = ('directory', root['id'])
            for name in files:
                path = Path(folder, name)
                if path.suffix.lower() not in EXTENSIONS or path.is_symlink():
                    continue
                try:
                    st = path.stat()
                    state[normalized(path)] = (st.st_mtime_ns, st.st_size, root['id'])
                except OSError as exc:
                    unreadable(exc)
    changed: dict[int, set[str]] = {}
    if previous is not None:
        for path in state.keys() | previous.keys():
            if state.get(path) == previous.get(path):
                continue
            info = state.get(path) or previous[path]
            rid = info[-1]
            folder = path if info[0] == 'directory' else str(Path(windows_path(path)).parent)
            changed.setdefault(rid, set()).add(normalized(folder))
    # Scan a changed ancestor only once when a subtree has appeared or disappeared.
    scopes = {rid: [p for p in paths if not any(p != other and Path(windows_path(p)).is_relative_to(Path(windows_path(other))) for other in paths)]
              for rid, paths in changed.items()}
    return state, scopes, errors
