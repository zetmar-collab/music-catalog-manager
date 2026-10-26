import json
from pathlib import Path
from PySide6.QtCore import QTranslator


class Translator(QTranslator):
    def __init__(self, language):
        super().__init__()
        self.messages = json.loads((Path(__file__).parents[1] / 'translations' / 'pl.json').read_text(encoding='utf-8')) if language == 'pl' else {}

    def translate(self, context, sourceText, disambiguation=None, n=-1):
        if context != 'MainWindow':
            return None
        return self.messages.get(sourceText, sourceText)


def qt_translator(language):
    translator = QTranslator()
    if language == 'pl':
        translator.load(str(Path(__file__).parents[1] / 'translations' / 'qtbase_pl.qm'))
    return translator
