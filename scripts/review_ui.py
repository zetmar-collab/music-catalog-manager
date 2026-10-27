"""Capture isolated UI fixtures at the caller's QT_SCALE_FACTOR."""
import json
import os
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from music_catalog_manager.database.store import Store, normalized
from music_catalog_manager.services import playlists
from music_catalog_manager.ui.window import MainWindow


def main():
    app = QApplication([])
    app.setFont(QFont('Segoe UI', 10))
    scale = os.environ.get('QT_SCALE_FACTOR', '1')
    output = Path('build/ui-review') / scale
    output.mkdir(parents=True, exist_ok=True)
    store = Store(output / 'profile')
    store.set_setting('language', 'pl')
    store.set_setting('theme', 'dark')
    store.set_setting('window_layout', {})
    with store.connection() as db:
        if not db.execute('SELECT count(*) FROM tracks').fetchone()[0]:
            for i in range(24):
                tags = dict(title=f'Utwór demonstracyjny {i+1}', artist='Anna Nowak' if i < 12 else 'Północ',
                    album='Światło miasta' if i < 12 else 'Daleko stąd', albumartist='Anna Nowak' if i < 12 else 'Północ',
                    genre='Jazz' if i < 12 else 'Ambient', date='2026', tracknumber=f'{i%12+1}/12')
                db.execute('INSERT INTO tracks(path,size,tags,format,duration,bitrate,available) VALUES(?,?,?,?,?,?,?)',
                    (normalized(output / f'{i}.mp3'), 5_000_000, json.dumps(tags, ensure_ascii=False), 'MP3', 210, 320000, 1))
    if not playlists.lists(store):
        playlists.save(store, 'Wieczorny wybór', [r['id'] for r in store.tracks()[:5]])
    window = MainWindow(store)
    target = (960, 540) if float(scale) >= 2 else (1280, 800) if float(scale) > 1 else (1400, 900)
    window.resize(*target)
    window.show()
    result = dict(scale=scale, target=target)
    loop = QEventLoop()
    def capture():
        if window.loading_library:
            QTimer.singleShot(30, capture)
            return
        window.table.selectRow(0)
        window.grab().save(str(output / 'library.png'))
        result['actual'] = [window.width(), window.height()]
        result['rows'] = window.model.rowCount()
        result['playback_visible'] = window.playback.isVisible() and window.playback.geometry().bottom() <= window.height()
        # Windows can reduce client height to account for its title bar/taskbar.
        result['passed'] = window.width() <= target[0] and window.height() <= target[1] and window.height() >= 400 and result['rows'] == 24 and result['playback_visible']
        loop.quit()
    QTimer.singleShot(50, capture)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    for name, handler in [('albums', window.albums_dialog), ('playlists', window.playlists_dialog), ('folders', window.folders_dialog), ('backups', window.backups_dialog)]:
        def close_dialog(name=name):
            dialog = app.activeModalWidget()
            if dialog:
                dialog.grab().save(str(output / (name + '.png')))
                dialog.reject()
        QTimer.singleShot(100, close_dialog)
        handler()
    window.close()
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    return 0 if result.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
