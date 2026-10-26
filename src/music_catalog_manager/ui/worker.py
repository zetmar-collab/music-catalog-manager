from threading import Event
from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(object)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function
        self.cancel = Event()

    def run(self):
        try:
            self.result.emit(self.function(self.cancel, self.progress.emit))
        except Exception as exc:
            from music_catalog_manager.services.musicbrainz import Cancelled
            if not isinstance(exc, Cancelled):
                self.failed.emit(str(exc))
