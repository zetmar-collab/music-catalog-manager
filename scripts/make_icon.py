import io
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

root = Path(__file__).resolve().parents[1] / 'src/music_catalog_manager/resources'
image = QImage(256, 256, QImage.Format_ARGB32)
image.fill(Qt.transparent)
painter = QPainter(image)
QSvgRenderer(str(root / 'icon.svg')).render(painter)
painter.end()
image.save(str(root / 'icon.png'))
Image.open(root / 'icon.png').save(root / 'icon.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
