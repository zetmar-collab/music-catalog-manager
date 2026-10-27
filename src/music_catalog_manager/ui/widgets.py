from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class ArtworkLabel(QLabel):
    """Keep the original image, without forcing its pixel size on the layout."""
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.original = QPixmap()
        self.setMinimumSize(0, 180)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def sizeHint(self):
        return QSize(220, 220)

    def setPixmap(self, pixmap):
        self.original = pixmap
        self.rescale()

    def rescale(self):
        super().setPixmap(self.original.scaled(max(1, self.width()), max(1, self.height()), Qt.KeepAspectRatio, Qt.SmoothTransformation) if not self.original.isNull() else QPixmap())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.rescale()
