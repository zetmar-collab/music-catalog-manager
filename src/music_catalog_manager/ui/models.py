from PySide6.QtCore import QAbstractTableModel, QCoreApplication, QModelIndex, QSortFilterProxyModel, QIdentityProxyModel, Signal, Qt
from PySide6.QtGui import QColor
from music_catalog_manager.database.store import FIELDS

def tr(text):
    return QCoreApplication.translate('MainWindow', text)

LABELS = dict(zip(FIELDS, ('Title', 'Artist', 'Album', 'Album artist', 'Genre', 'Date', 'Track number', 'Disc number', 'Composer', 'Comment')))
COLUMNS = [('title', 'Title'), ('artist', 'Artist'), ('album', 'Album'), ('date', 'Date'), ('genre', 'Genre'),
           ('duration', 'Duration'), ('format', 'Format'), ('path', 'Location'), ('status', 'Tag status'), ('tracknumber', 'Track number'), ('discnumber', 'Disc number')]


class TrackModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def replace(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return tr(COLUMNS[section][1])
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = COLUMNS[index.column()][0]
        if role == Qt.UserRole:
            if key == 'status':
                return 0 if not row['available'] else 1 if row['dirty'] else 2 if not all(row['tags'].get(k) for k in ('title', 'artist', 'album')) else 3
            if key in ('tracknumber', 'discnumber'):
                try:
                    return int(row['tags'].get(key, '').split('/')[0] or 0)
                except ValueError:
                    return 0
            if key == 'duration':
                return row['duration'] or 0
            return str(row['tags'].get(key, row.get(key, ''))).casefold()
        if role == Qt.ForegroundRole and not row['available']:
            return QColor('#a86565')
        if role == Qt.DisplayRole:
            if key == 'duration':
                seconds = int(row['duration'] or 0)
                return f'{seconds // 60}:{seconds % 60:02}'
            if key == 'status':
                if not row['available']:
                    return tr('Unavailable')
                if row['dirty']:
                    return tr('Database changes')
                if not all(row['tags'].get(k) for k in ('title', 'artist', 'album')):
                    return tr('Missing tags')
                return tr('Complete')
            return row['tags'].get(key, row.get(key, ''))


class Filter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ''
        self.filters = {}
        self.duplicates = False
        self.hashes = set()
        self.setSortRole(Qt.UserRole)

    def filterAcceptsRow(self, row, parent):
        record = self.sourceModel().rows[row]
        if self.duplicates and (not record.get('sha256') or record['sha256'] not in self.hashes):
            return False
        text = ' '.join(str(v) for v in record['tags'].values()) + ' ' + record['path']
        if self.query not in text.casefold():
            return False
        for key, value in self.filters.items():
            actual = record['tags'].get(key, record.get(key, ''))
            if value and str(actual).casefold() != value.casefold():
                return False
        return True


class LibraryProxy(QIdentityProxyModel):
    sortRequested = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hashes = set()
        self.duplicates = False

    def sort(self, column, order=Qt.AscendingOrder):
        self.sortRequested.emit(column, order)

    def invalidate(self):
        pass
