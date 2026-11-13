"""Render the existing SVG at each MSIX logo's native size."""
import argparse
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    renderer = QSvgRenderer(str(ROOT / 'src/music_catalog_manager/resources/icon.svg'))
    sizes = {'StoreLogo': (50, 50), 'Square44x44Logo': (44, 44),
             'Square150x150Logo': (150, 150), 'Square310x310Logo': (310, 310),
             'Wide310x150Logo': (310, 150)}
    for name, (width, height) in sizes.items():
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        side = min(width, height)
        painter = QPainter(image)
        renderer.render(painter, QRectF((width - side) / 2, (height - side) / 2, side, side))
        painter.end()
        if not image.save(str(args.destination / (name + '.png'))):
            raise OSError('Could not save ' + name)


if __name__ == '__main__':
    main()
