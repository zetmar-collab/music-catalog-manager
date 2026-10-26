import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from music_catalog_manager.database.store import Store
from music_catalog_manager.ui.window import MainWindow


def test_window_languages_themes(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path)
    store.set_setting('language', 'pl')
    window = MainWindow(store)
    assert window.action_buttons[0].text() == 'Dodaj folder'
    buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
    assert buttons.button(QDialogButtonBox.Cancel).text() == 'Anuluj'
    for theme in ('dark', 'light', 'system'):
        window.apply_theme(theme)
    window.show()
    app.processEvents()
    assert window.isVisible()
    window.close()
    app.removeTranslator(window.translator)
    store.set_setting('language', 'en')
    window = MainWindow(store)
    assert window.action_buttons[0].text() == 'Add folder'
    window.close()
