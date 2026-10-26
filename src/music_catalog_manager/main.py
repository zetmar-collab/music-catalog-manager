import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'MusicCatalogManager')
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--verify-audio', type=Path)
    args = parser.parse_args()
    from PySide6.QtCore import QTimer, QLockFile
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QMessageBox
    from music_catalog_manager.database.store import Store
    from music_catalog_manager.ui.window import MainWindow
    app = QApplication(sys.argv[:1])
    app.setApplicationName('Music Catalog Manager')
    app.setFont(QFont('Segoe UI', 10))
    args.profile.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(args.profile / 'application.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, 'Music Catalog Manager', 'Ten profil jest już otwarty. / This profile is already open.')
        return 1
    store = Store(args.profile)
    window = MainWindow(store)
    window.show()
    if args.verify_audio:
        def acceptance():
            import json
            import traceback
            from music_catalog_manager.diagnostics import verify_audio
            try:
                result = verify_audio(args.verify_audio)
                result['passed'] = True
                code = 0
            except Exception:
                result = {'passed': False, 'error': traceback.format_exc()}
                code = 1
            (args.profile / 'acceptance-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            app.exit(code)
        QTimer.singleShot(100, acceptance)
    if args.smoke_test:
        def smoke():
            import json
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if window.proxy.rowCount():
                    window.table.selectRow(0)
                window.grab().save(str(args.screenshot))
            (args.profile / 'smoke-result.json').write_text(json.dumps({'window_visible': window.isVisible(),
                'add_folder_label': window.action_buttons[0].text(), 'schema': 1, 'icon_loaded': not window.windowIcon().isNull()}), encoding='utf-8')
            app.quit()
        QTimer.singleShot(1500, smoke)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
