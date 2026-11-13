from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer
from music_catalog_manager.services.folder_watch import snapshot
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.ui.worker import Worker


class FolderMonitor(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.state = None
        self.job = None
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda *_: self.schedule())
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1500)

    def schedule(self):
        if not self.timer.isActive() or self.timer.remainingTime() > 1500:
            self.timer.start(1500)

    def poll(self):
        window = self.window
        if window.closing:
            return
        if not window.store.setting('watch_folders', False):
            self.state = None
            if self.watcher.directories():
                self.watcher.removePaths(self.watcher.directories())
            self.timer.start(30000)
            return
        if window.worker or self.job:
            self.timer.start(2000)
            return
        roots = window.store.roots()
        existing = set(self.watcher.directories())
        wanted = {r['path'] for r in roots}
        self.watcher.removePaths(list(existing - wanted)) if existing - wanted else None
        self.watcher.addPaths(list(wanted - existing)) if wanted - existing else None
        previous = self.state
        def work(cancel, progress):
            state, changed, errors = snapshot(roots, previous, cancel)
            # First enable performs one reconciliation; subsequent scans are scoped.
            if previous is None:
                changed = {r['id']: [r['path']] for r in roots}
            for rid, folders in changed.items():
                scan(window.store, rid, cancel, progress, window.store.setting('hashes', False), folders)
            return state, bool(changed), errors
        self.job = Worker(work, self)
        self.job.result.connect(self.received)
        self.job.failed.connect(lambda error: window.store.log('watch_error', after=error))
        self.job.finished.connect(self.finished)
        self.job.start()

    def received(self, result):
        self.state, changed, errors = result
        if changed and not self.window.closing:
            self.window.refresh()
        for error in errors:
            self.window.store.log('watch_error', after=error)

    def finished(self):
        self.job.deleteLater()
        self.job = None
        if not self.window.closing:
            self.timer.start(30000)

    def stop(self):
        self.timer.stop()
        if self.job:
            self.job.cancel.set()
            self.job.wait()
