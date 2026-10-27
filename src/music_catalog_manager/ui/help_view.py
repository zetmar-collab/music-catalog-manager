from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout

from music_catalog_manager.ui.models import tr


def help_path(language):
    if language not in ('pl', 'en'):
        raise ValueError('Unsupported help language')
    return Path(__file__).parents[1] / 'resources' / f'help-{language}.html'


class HelpViews:
    def install_help_menu(self):
        menu = self.menuBar().addMenu(tr('Help'))
        action = menu.addAction(tr('User guide'))
        action.setShortcut('F1')
        action.triggered.connect(lambda: self.show_help())
        menu.addSeparator()
        menu.addAction('Polski').triggered.connect(lambda: self.show_help('pl'))
        menu.addAction('English').triggered.connect(lambda: self.show_help('en'))

    def show_help(self, language=None):
        language = language or ('pl' if self.translator.messages else 'en')
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Help'))
        dialog.resize(960, 720)
        layout = QVBoxLayout(dialog)
        line = QHBoxLayout()
        line.addWidget(QLabel(tr('Language')))
        languages = QComboBox()
        languages.addItem('Polski', 'pl')
        languages.addItem('English', 'en')
        languages.setCurrentIndex(0 if language == 'pl' else 1)
        line.addWidget(languages)
        line.addStretch()
        layout.addLayout(line)
        browser = QTextBrowser()
        browser.setStyleSheet('QTextBrowser{background:#ffffff;color:#172b42;padding:12px}')
        browser.setOpenExternalLinks(True)
        def load():
            browser.setSource(QUrl.fromLocalFile(str(help_path(languages.currentData()))))
        languages.currentIndexChanged.connect(load)
        load()
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
