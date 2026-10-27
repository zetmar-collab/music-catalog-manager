"""Native screenshots of 0.4.0 dialogs, using an isolated synthetic profile."""
import io
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from music_catalog_manager.database.store import Store, normalized
from music_catalog_manager.services import playlists
from music_catalog_manager.ui.window import MainWindow


def main():
    import json
    output = Path('build/ui-review-0.4.0')
    output.mkdir(parents=True, exist_ok=True)
    store = Store(output / 'profile')
    store.set_setting('language', 'pl')
    store.set_setting('theme', 'dark')
    store.set_setting('window_layout', {})
    with store.connection() as db:
        if not db.execute('SELECT count(*) FROM tracks').fetchone()[0]:
            for index in range(6):
                db.execute('INSERT INTO tracks(path,tags,size,duration,format,bitrate) VALUES(?,?,?,?,?,?)',
                    (normalized(output / f'{index}.mp3'), json.dumps(dict(title=f'Utwór demonstracyjny {index+1}',
                        artist='Wykonawca demonstracyjny', album='Album demonstracyjny'), ensure_ascii=False), 5000000, 210, 'MP3', 320000))
    rows = store.tracks()
    pid = playlists.lists(store)[0]['id'] if playlists.lists(store) else playlists.save(store, 'Wieczorny wybór', [rows[i]['id'] for i in (2, 0, 2, 1)])
    app = QApplication([])
    app.setFont(QFont('Segoe UI', 10))
    window = MainWindow(store)
    window.resize(1400, 900)
    window.show()
    loop = QEventLoop()
    def loaded():
        if window.loading_library:
            QTimer.singleShot(30, loaded)
        else:
            loop.quit()
    window.group.setCurrentIndex(4)
    window.groups.setCurrentIndex(window.groups.findData(pid))
    QTimer.singleShot(30, loaded)
    loop.exec()
    window.table.selectRow(0)
    app.processEvents()
    window.grab().save(str(output / 'playlist-grouping.png'))
    def capture(name, callback):
        def close():
            dialog = app.activeModalWidget()
            if dialog:
                dialog.grab().save(str(output / (name + '.png')))
                dialog.reject()
        QTimer.singleShot(120, close)
        callback()
    capture('help-pl', lambda: window.show_help('pl'))
    capture('help-en', lambda: window.show_help('en'))
    capture('cover-search', window.search_cover_dialog)
    candidates = []
    for index, color in enumerate(('#3269ae', '#92683b')):
        image = Image.new('RGB', (300, 300), color)
        ImageDraw.Draw(image).text((95, 140), 'DEMO COVER', fill='white')
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        candidates.append(dict(data=buffer.getvalue(), release_id='demo', album='Album demonstracyjny',
            artist='Wykonawca demonstracyjny', date='2026', country='PL', source='Cover Art Archive — DEMO', url='https://musicbrainz.org'))
    capture('cover-results', lambda: window.cover_results(window.selected(), dict(covers=candidates, errors=[])))
    files = [output / 'mix.m3u', output / 'Podfolder' / 'wieczór.pls']
    capture('playlist-import', lambda: window.choose_playlist_files(output, files, []))
    window.close()
    print(output.resolve())


if __name__ == '__main__':
    main()
