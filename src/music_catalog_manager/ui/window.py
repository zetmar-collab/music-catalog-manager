import csv
import json
import locale
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QCoreApplication, QModelIndex, QSortFilterProxyModel, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPalette, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSplitter, QTableView, QVBoxLayout, QWidget)

from music_catalog_manager.database.store import FIELDS
from music_catalog_manager.services import backup, metadata, rename
from music_catalog_manager.services.artwork import cache_image, folder_image, validate_image
from music_catalog_manager.services.musicbrainz import MusicBrainz
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.ui.i18n import Translator, qt_translator
from music_catalog_manager.ui.worker import Worker
from music_catalog_manager.ui.playback import PlaybackBar


def tr(text):
    return QCoreApplication.translate('MainWindow', text)


LABELS = dict(zip(FIELDS, ('Title', 'Artist', 'Album', 'Album artist', 'Genre', 'Date', 'Track number', 'Disc number', 'Composer', 'Comment')))
COLUMNS = [('title', 'Title'), ('artist', 'Artist'), ('album', 'Album'), ('date', 'Date'), ('genre', 'Genre'),
           ('duration', 'Duration'), ('format', 'Format'), ('path', 'Location'), ('status', 'Tag status')]


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


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.worker = None
        self.pending_result = None
        language = store.setting('language', 'pl' if (locale.getlocale()[0] or '').startswith('Polish') or (locale.getlocale()[0] or '').startswith('pl') else 'en')
        self.translator = Translator(language)
        self.qt_translator = qt_translator(language)
        QApplication.instance().installTranslator(self.qt_translator)
        QApplication.instance().installTranslator(self.translator)
        self.setWindowTitle('Music Catalog Manager')
        self.setWindowIcon(QIcon(str(Path(__file__).parents[1] / 'resources' / 'icon.ico')))
        self.resize(1400, 840)
        self.build()
        self.apply_theme(store.setting('theme', 'system'))
        self.refresh()

    def button(self, text, handler, layout):
        button = QPushButton(tr(text))
        button.setAccessibleName(tr(text))
        button.clicked.connect(handler)
        layout.addWidget(button)
        return button

    def build(self):
        if hasattr(self, 'playback'):
            self.playback.release()
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        title = QLabel('♫  Music Catalog Manager')
        title.setStyleSheet('font-size:24px;font-weight:600;padding:12px')
        outer.addWidget(title)
        toolbar = QHBoxLayout()
        outer.addLayout(toolbar)
        self.action_buttons = []
        for label, handler in [('Add folder', self.add_folder), ('Rescan', self.rescan), ('Edit tags', self.edit_tags),
                ('Find metadata', self.find_metadata), ('Artwork', self.artwork_dialog), ('Rename', self.rename_tracks), ('Create backup', self.create_backup)]:
            self.action_buttons.append(self.button(label, handler, toolbar))
        splitter = QSplitter()
        outer.addWidget(splitter, 1)
        self.sidebar = QListWidget()
        self.sidebar.addItems([tr(x) for x in ('Library', 'Folders', 'Duplicates', 'Backups', 'Settings')])
        self.sidebar.setMaximumWidth(175)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.navigate)
        splitter.addWidget(self.sidebar)
        middle = QWidget()
        content = QVBoxLayout(middle)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Search library…'))
        self.search.setAccessibleName(tr('Search library…'))
        content.addWidget(self.search)
        filters = QHBoxLayout()
        content.addLayout(filters)
        self.combos = {}
        for key, label in [('artist', 'Artist'), ('album', 'Album'), ('genre', 'Genre'), ('date', 'Date'), ('format', 'Format'), ('root_id', 'Folder')]:
            combo = QComboBox()
            combo.setMinimumWidth(90)
            combo.setMaximumWidth(170)
            combo.setAccessibleName(tr(label))
            combo.setToolTip(tr(label))
            combo.currentIndexChanged.connect(self.update_filter)
            filters.addWidget(combo)
            self.combos[key] = combo
        grouping = QHBoxLayout()
        content.addLayout(grouping)
        grouping.addWidget(QLabel(tr('Group by')))
        self.group = QComboBox()
        self.group.addItems([tr(x) for x in ('None', 'Artist', 'Album', 'Folder')])
        self.group.currentIndexChanged.connect(self.group_changed)
        grouping.addWidget(self.group)
        self.groups = QComboBox()
        self.groups.setMinimumWidth(240)
        self.groups.currentIndexChanged.connect(self.group_selected)
        grouping.addWidget(self.groups)
        grouping.addStretch()
        self.table = QTableView()
        self.model = TrackModel(self)
        self.proxy = Filter(self)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 210)
        self.table.setColumnWidth(1, 160)
        self.table.selectionModel().selectionChanged.connect(self.details)
        self.table.doubleClicked.connect(self.play_index)
        self.play_shortcut = QShortcut(QKeySequence('Space'), self.table)
        self.play_shortcut.setContext(Qt.WidgetShortcut)
        self.play_shortcut.activated.connect(lambda: self.playback.toggle())
        self.enter_shortcut = QShortcut(QKeySequence('Return'), self.table)
        self.enter_shortcut.setContext(Qt.WidgetShortcut)
        self.enter_shortcut.activated.connect(lambda: self.play_index(self.table.currentIndex()))
        self.search.textChanged.connect(self.update_filter)
        content.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        content.addLayout(bottom)
        self.button('Open location', self.open_location, bottom)
        self.button('Undo database edit', self.undo, bottom)
        self.button('Write pending tags', self.write_pending, bottom)
        self.button('Export', self.export, bottom)
        self.button('History', self.history, bottom)
        splitter.addWidget(middle)
        right = QWidget()
        right.setMinimumWidth(230)
        right.setMaximumWidth(350)
        detail = QVBoxLayout(right)
        self.cover = QLabel('♫')
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setMinimumHeight(220)
        self.cover.setStyleSheet('font-size:60px;border-radius:12px;background:rgba(104,122,144,35)')
        detail.addWidget(self.cover)
        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        detail.addWidget(self.detail_text)
        splitter.addWidget(right)
        splitter.setSizes([160, 930, 270])
        self.playback = PlaybackBar(self.store, self.selected, self.visible_tracks, self)
        outer.addWidget(self.playback)
        status = QHBoxLayout()
        outer.addLayout(status)
        self.status = QLabel(tr('Ready'))
        status.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        status.addWidget(self.progress)
        self.cancel_button = self.button('Cancel', self.cancel, status)
        self.cancel_button.setEnabled(False)

    def apply_theme(self, theme):
        app = QApplication.instance()
        app.styleHints().setColorScheme({'dark': Qt.ColorScheme.Dark, 'light': Qt.ColorScheme.Light, 'system': Qt.ColorScheme.Unknown}[theme])
        app.setStyle('Fusion')
        if theme == 'dark':
            palette = QPalette()
            for role, color in [(QPalette.Window, '#20252d'), (QPalette.WindowText, '#e8edf4'),
                    (QPalette.Base, '#191e25'), (QPalette.AlternateBase, '#242c35'), (QPalette.Text, '#e8edf4'),
                    (QPalette.Button, '#303a46'), (QPalette.ButtonText, '#e8edf4'), (QPalette.Highlight, '#3269ae'),
                    (QPalette.HighlightedText, '#ffffff'), (QPalette.ToolTipBase, '#20252d'), (QPalette.ToolTipText, '#e8edf4')]:
                palette.setColor(role, QColor(color))
            app.setPalette(palette)
        else:
            app.setPalette(app.style().standardPalette())
        app.setStyleSheet('QPushButton{padding:8px 10px} QLineEdit,QComboBox{padding:6px} QListWidget{padding:8px} QListWidget::item{padding:10px 3px} QTableView{gridline-color:rgba(128,128,128,35)} QHeaderView::section{padding:7px}')

    def selected(self):
        return [self.model.rows[self.proxy.mapToSource(i).row()] for i in sorted(self.table.selectionModel().selectedRows(), key=lambda index: index.row())]

    def visible_tracks(self):
        return [self.model.rows[self.proxy.mapToSource(self.proxy.index(i, 0)).row()] for i in range(self.proxy.rowCount())]

    def play_index(self, index):
        if index.isValid():
            self.playback.play_track(self.model.rows[self.proxy.mapToSource(index).row()])

    def refresh(self):
        rows = self.store.tracks()
        self.model.replace(rows)
        counts = {}
        for row in rows:
            if row['sha256']:
                counts[row['sha256']] = counts.get(row['sha256'], 0) + 1
        self.proxy.hashes = {h for h, count in counts.items() if count > 1}
        roots = {r['id']: r['path'] for r in self.store.roots()}
        for key, combo in self.combos.items():
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(tr('All') + ': ' + tr(dict((k, v) for k, v in [('artist', 'Artist'), ('album', 'Album'), ('genre', 'Genre'), ('date', 'Date'), ('format', 'Format'), ('root_id', 'Folder')])[key]), '')
            values = sorted({str(r['tags'].get(key, r.get(key, ''))) for r in rows if r['tags'].get(key, r.get(key, ''))}, key=str.casefold)
            for value in values:
                combo.addItem(roots.get(int(value), value) if key == 'root_id' else value, value)
            idx = combo.findData(previous)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)
        self.group_changed()
        self.update_filter()
        self.details()

    def update_filter(self, *_):
        self.proxy.query = self.search.text().casefold()
        self.proxy.filters = {key: combo.currentData() or '' for key, combo in self.combos.items()}
        self.proxy.invalidate()
        self.status.setText(tr('Tracks') + f': {self.proxy.rowCount()} / {self.model.rowCount()}')

    def group_changed(self, *_):
        self.groups.blockSignals(True)
        self.groups.clear()
        self.groups.addItem(tr('All'), '')
        key = {1: 'artist', 2: 'album', 3: 'root_id'}.get(self.group.currentIndex())
        if key:
            source = self.combos[key]
            for index in range(1, source.count()):
                self.groups.addItem(source.itemText(index), source.itemData(index))
        self.groups.blockSignals(False)
        self.group_selected()

    def group_selected(self, *_):
        key = {1: 'artist', 2: 'album', 3: 'root_id'}.get(self.group.currentIndex())
        if key:
            self.combos[key].setCurrentIndex(max(0, self.combos[key].findData(self.groups.currentData())))
            self.table.sortByColumn({'artist': 1, 'album': 2, 'root_id': 7}[key], Qt.AscendingOrder)

    def details(self, *_):
        selected = self.selected()
        self.cover.setPixmap(QPixmap())
        self.cover.setText('♫')
        if not selected:
            self.detail_text.setPlainText(tr('Select a track to see details.'))
            return
        row = selected[0]
        text = '\n'.join(tr(LABELS[k]) + ': ' + row['tags'].get(k, '') for k in FIELDS)
        text += f"\n\n{row['format']} · {row['size']:,} B · {row['bitrate'] or 0} bps\n{row['path']}"
        if row['sha256'] in self.proxy.hashes:
            text += '\n' + tr('Confirmed duplicate (SHA-256)')
        if not metadata.writable(row['path']):
            text += '\n' + tr('Read-only format')
        self.detail_text.setPlainText(text)
        if row['artwork']:
            pix = QPixmap(str(self.store.cache / row['artwork']))
            if not pix.isNull():
                self.cover.setPixmap(pix.scaled(260, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def error(self, detail):
        self.store.log('error', after=detail)
        box = QMessageBox(QMessageBox.Warning, tr('Operation failed'), tr('The operation could not be completed. See details.'), parent=self)
        box.setDetailedText(str(detail))
        box.exec()

    def guarded(self, function):
        try:
            return function()
        except Exception as exc:
            self.error(str(exc))

    def confirm(self, text):
        return QMessageBox.question(self, tr('Confirm'), text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def preview(self, title, text, image=None):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(title))
        dialog.resize(800, 520)
        layout = QVBoxLayout(dialog)
        if image:
            pix = QPixmap()
            pix.loadFromData(image)
            label = QLabel()
            label.setPixmap(pix.scaled(300, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(label)
        view = QPlainTextEdit(text)
        view.setReadOnly(True)
        layout.addWidget(view)
        buttons = QDialogButtonBox()
        buttons.addButton(tr('Confirm'), QDialogButtonBox.AcceptRole)
        buttons.addButton(tr('Cancel'), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.Accepted

    def start(self, function, done=None, lock_playback=False):
        if self.worker:
            return
        self.playback.set_busy(lock_playback)
        self.worker = Worker(function, self)
        self.pending_result = None
        self.done_callback = done or (lambda _: self.refresh())
        for button in self.action_buttons:
            button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_button.setEnabled(True)
        self.worker.progress.connect(self.scan_progress)
        self.worker.failed.connect(self.error)
        self.worker.result.connect(self.receive_result)
        self.worker.finished.connect(self.finished)
        if lock_playback:
            self.playback.when_released(self.worker.start)
        else:
            self.worker.start()

    def receive_result(self, result):
        self.pending_result = (result,)

    def finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        for button in self.action_buttons:
            button.setEnabled(True)
        self.progress.hide()
        self.cancel_button.setEnabled(False)
        self.playback.set_busy(False)
        self.refresh()
        result, callback = self.pending_result, self.done_callback
        self.pending_result = None
        if result is not None:
            self.guarded(lambda: callback(result[0]))

    def cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.status.setText(tr('Cancelling…'))

    def scan_progress(self, stats):
        self.status.setText(' · '.join(tr(key.capitalize()) + ': ' + str(value) for key, value in stats.items()))

    def scan_roots(self, roots):
        hashes = self.store.setting('hashes', False)
        def work(cancel, progress):
            results = []
            for root in roots:
                if cancel.is_set():
                    break
                results.append(scan(self.store, root['id'], cancel, progress, hashes))
            return results
        def done(results):
            self.refresh()
            totals = {key: sum(r[key] for r in results) for key in ('scanned', 'new', 'changed', 'skipped', 'errors')}
            QMessageBox.information(self, tr('Scan complete'), '\n'.join(tr(k.capitalize()) + ': ' + str(v) for k, v in totals.items()))
        self.start(work, done)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, tr('Add folder'))
        if path:
            rid = self.store.add_root(path)
            self.scan_roots([{'id': rid}])

    def rescan(self):
        roots = self.store.roots()
        choices = [tr('All')] + [r['path'] for r in roots]
        value, ok = QInputDialog.getItem(self, tr('Rescan'), tr('Folder'), choices, 0, False)
        if ok:
            self.scan_roots(roots if value == choices[0] else [r for r in roots if r['path'] == value])

    def edit_tags(self, *_):
        if self.worker:
            return
        tracks = self.selected()
        if not tracks:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Edit tags'))
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(tr('Only checked fields will change. Blank values remove the field.')))
        form = QFormLayout()
        layout.addLayout(form)
        inputs = {}
        for key in FIELDS:
            check, edit = QCheckBox(tr(LABELS[key])), QLineEdit(tracks[0]['tags'].get(key, '') if len(tracks) == 1 else '')
            edit.textEdited.connect(lambda _, c=check: c.setChecked(True))
            form.addRow(check, edit)
            inputs[key] = check, edit
        disk = QCheckBox(tr('Write tags to audio files'))
        disk.setEnabled(all(metadata.writable(t['path']) and t['available'] for t in tracks))
        layout.addWidget(disk)
        copies = QCheckBox(tr('Back up original audio before writing'))
        copies.setChecked(True)
        layout.addWidget(copies)
        layout.addWidget(QLabel(tr('Database undo does not restore audio files.')))
        buttons = QDialogButtonBox()
        buttons.addButton(tr('Preview'), QDialogButtonBox.AcceptRole)
        buttons.addButton(tr('Cancel'), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        changes = {k: edit.text() for k, (check, edit) in inputs.items() if check.isChecked()}
        if not changes:
            return
        summary = tr('Destination: audio files and database') if disk.isChecked() else tr('Destination: database only')
        summary += '\n\n' + '\n\n'.join(t['path'] + '\n' + '\n'.join(tr(LABELS[k]) + ': ' + t['tags'].get(k, '') + ' → ' + v for k, v in changes.items()) for t in tracks)
        if self.preview('Preview changes', summary):
            self.write_changes(tracks, changes, disk.isChecked(), copies.isChecked())

    def write_changes(self, tracks, changes, disk=False, copies=True, image=None):
        def work(cancel, progress):
            errors = []
            for track in tracks:
                if cancel.is_set():
                    break
                try:
                    if disk:
                        metadata.write_safe(track['path'], changes, image, self.store.profile / 'audio-backups' if copies else None)
                    if changes:
                        self.store.edit([track['id']], changes)
                    if image:
                        cache_image(self.store, track['id'], image, 'manual')
                    if disk:
                        st = Path(track['path']).stat()
                        with self.store.connection() as db:
                            # Pending database fields remain pending unless the complete tag set was written.
                            pending = self.store.track(track['id'])['tags']
                            actual = metadata.read(track['path'])['tags']
                            dirty = int(any(actual.get(k, '') != pending.get(k, '') for k in FIELDS))
                            db.execute('UPDATE tracks SET mtime=?,size=?,sha256=NULL,dirty=? WHERE id=?', (st.st_mtime_ns, st.st_size, dirty, track['id']))
                    self.store.log('write' if disk else 'database', track['id'], after=changes)
                except Exception as exc:
                    errors.append(Path(track['path']).name + ': ' + str(exc))
                    self.store.log('write_error', track['id'], after=str(exc))
            return errors
        def done(errors):
            if errors:
                self.error('\n'.join(errors))
        self.start(work, done, lock_playback=disk)

    def rename_tracks(self):
        if self.worker:
            return
        tracks = self.selected()
        if not tracks:
            return
        template, ok = QInputDialog.getText(self, tr('Rename'), tr('Template (or a literal name for one track)'), text='{artist} - {title}')
        if ok:
            def action():
                plan = rename.preview(tracks, template)
                if self.preview('Preview changes', '\n'.join(str(a) + ' → ' + b.name for _, a, b in plan)):
                    self.start(lambda cancel, progress: rename.execute(self.store, plan), lock_playback=True)
            self.guarded(action)

    def internet(self, action, done):
        contact = self.store.setting('contact', '')
        if not contact:
            QMessageBox.information(self, tr('Settings'), tr('Configure a contact email or URL in Settings before using internet services.'))
            return
        def work(cancel, progress):
            client = MusicBrainz(self.store.profile, contact, cancel)
            try:
                return action(client)
            finally:
                client.close()
        self.start(work, done)

    def find_metadata(self):
        tracks = self.selected()
        if not tracks:
            return
        track = tracks[0]
        if not self.confirm(tr('Send title, artist, album and existing identifiers of the selected track to MusicBrainz?')):
            return
        def done(results):
            if not results:
                QMessageBox.information(self, 'MusicBrainz', tr('No results.'))
                return
            dialog = QDialog(self)
            dialog.setWindowTitle(tr('Possible matches — verify before applying'))
            dialog.resize(1000, 450)
            layout = QVBoxLayout(dialog)
            options = QListWidget()
            for r in results:
                options.addItem(f"{r['score']}%? · {r['artist']} — {r['title']} · {r['album']} · {r['date']} · {r['musicbrainz_albumid']} · MusicBrainz")
            layout.addWidget(options)
            buttons = QDialogButtonBox()
            buttons.addButton(tr('Preview'), QDialogButtonBox.AcceptRole)
            buttons.addButton(tr('Cancel'), QDialogButtonBox.RejectRole)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() == QDialog.Accepted and options.currentRow() >= 0:
                changes = {k: v for k, v in results[options.currentRow()].items() if k not in ('score', 'source') and v}
                if self.preview('Preview changes', tr('Destination: database only') + '\n\n' + '\n'.join(k + ': ' + track['tags'].get(k, '') + ' → ' + str(v) for k, v in changes.items())):
                    self.store.edit([track['id']], changes)
                    self.refresh()
        self.internet(lambda client: client.search(track['tags']), done)

    def artwork_dialog(self):
        tracks = self.selected()
        if not tracks:
            return
        choices = [tr('Choose local image'), tr('Cover Art Archive')]
        value, ok = QInputDialog.getItem(self, tr('Artwork'), tr('Source'), choices, 0, False)
        if not ok:
            return
        if value == choices[0]:
            path, _ = QFileDialog.getOpenFileName(self, tr('Choose local image'), '', 'Images (*.jpg *.jpeg *.png)')
            if path:
                self.guarded(lambda: self.apply_artwork(tracks, validate_image(Path(path).read_bytes())))
        else:
            release, ok = QInputDialog.getText(self, tr('Cover Art Archive'), tr('Release MBID (verify album)'), text=tracks[0]['tags'].get('musicbrainz_albumid', ''))
            if ok and release:
                self.internet(lambda client: client.cover(release), lambda data: self.guarded(lambda: self.apply_artwork(tracks, data, release)))

    def apply_artwork(self, tracks, data, release=None):
        if not data:
            QMessageBox.information(self, tr('Artwork'), tr('No cover found. Choose a local image.'))
            return
        data = validate_image(data)
        choices = [tr('Cache only'), tr('Embed in audio (with original backups)'), tr('Save folder.jpg')]
        choice, ok = QInputDialog.getItem(self, tr('Artwork'), tr('Destination'), choices, 0, False)
        if not ok or not self.preview('Preview changes', choice + '\n' + '\n'.join(t['path'] for t in tracks), data):
            return
        if choice == choices[1]:
            if not all(metadata.writable(t['path']) for t in tracks):
                raise ValueError(tr('Read-only format'))
            self.write_changes(tracks, {}, True, True, data)
        else:
            for track in tracks:
                if choice == choices[2]:
                    target = Path(track['path']).parent / 'folder.jpg'
                    overwrite = target.exists()
                    if overwrite and not self.confirm(tr('Replace existing file?') + '\n' + str(target)):
                        continue
                    folder_image(track['path'], data, overwrite)
                cache_image(self.store, track['id'], data, 'Cover Art Archive' if release else 'local', release)
            self.refresh()

    def create_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Create backup'), 'MusicCatalog.zip', 'ZIP (*.zip)')
        if path:
            self.start(lambda cancel, progress: backup.create(self.store, path), lambda _: QMessageBox.information(self, tr('Create backup'), tr('Backup created. Audio files are not included.')))

    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Restore backup'), '', 'ZIP (*.zip)')
        if path:
            def action():
                manifest = backup.inspect(path)
                summary = tr('Replace current library? A safety backup will be created. Audio files are not restored.') + '\n\n' + json.dumps(manifest, indent=2)
                if self.preview('Restore backup', summary):
                    self.start(lambda cancel, progress: backup.restore(self.store, path), lambda _: self.refresh(), lock_playback=True)
            self.guarded(action)

    def navigate(self, index):
        if self.worker and index in (1, 3, 4):
            self.sidebar.setCurrentRow(0)
            return
        self.proxy.duplicates = index == 2
        self.proxy.invalidate()
        if index == 1:
            self.folders()
        elif index == 3:
            choices = [tr('Create backup'), tr('Restore backup')]
            value, ok = QInputDialog.getItem(self, tr('Backups'), tr('Action'), choices, 0, False)
            if ok:
                self.create_backup() if value == choices[0] else self.restore_backup()
        elif index == 4:
            self.settings()
        elif index == 2 and not self.proxy.hashes:
            QMessageBox.information(self, tr('Duplicates'), tr('Enable SHA-256 in Settings and rescan to confirm duplicates.'))

    def folders(self):
        roots = self.store.roots()
        if not roots:
            return
        choice, ok = QInputDialog.getItem(self, tr('Folders'), tr('Select a folder to relink'), [r['path'] for r in roots], 0, False)
        if ok:
            target = QFileDialog.getExistingDirectory(self, tr('New location'))
            if target and self.confirm(choice + ' → ' + target):
                root_id = next(r['id'] for r in roots if r['path'] == choice)
                self.start(lambda cancel, progress: self.store.relink(root_id, target), lock_playback=True)

    def settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Settings'))
        layout = QFormLayout(dialog)
        language = QComboBox()
        language.addItem('Polski', 'pl')
        language.addItem('English', 'en')
        language.setCurrentIndex(max(0, language.findData(self.store.setting('language', 'pl'))))
        layout.addRow(tr('Language'), language)
        theme = QComboBox()
        for label, code in [('System', 'system'), ('Light', 'light'), ('Dark', 'dark')]:
            theme.addItem(tr(label), code)
        theme.setCurrentIndex(max(0, theme.findData(self.store.setting('theme', 'system'))))
        layout.addRow(tr('Theme'), theme)
        contact = QLineEdit(self.store.setting('contact', ''))
        layout.addRow(tr('Developer contact (User-Agent)'), contact)
        hashes = QCheckBox(tr('Calculate SHA-256 (slower scans)'))
        hashes.setChecked(self.store.setting('hashes', False))
        layout.addRow(hashes)
        layout.addRow(QLabel(tr('Metadata: MusicBrainz. Covers: Cover Art Archive. Verify rights before redistribution.')))
        buttons = QDialogButtonBox()
        buttons.addButton(tr('Save'), QDialogButtonBox.AcceptRole)
        buttons.addButton(tr('Cancel'), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            for key, value in [('language', language.currentData()), ('theme', theme.currentData()), ('contact', contact.text().strip()), ('hashes', hashes.isChecked())]:
                self.store.set_setting(key, value)
            QApplication.instance().removeTranslator(self.translator)
            QApplication.instance().removeTranslator(self.qt_translator)
            self.qt_translator = qt_translator(language.currentData())
            QApplication.instance().installTranslator(self.qt_translator)
            self.translator = Translator(language.currentData())
            QApplication.instance().installTranslator(self.translator)
            self.build()
            self.apply_theme(theme.currentData())
            self.refresh()

    def undo(self):
        if self.worker:
            return
        self.store.undo()
        self.refresh()

    def write_pending(self):
        if self.worker:
            return
        tracks = self.selected()
        if not tracks or not all(metadata.writable(t['path']) and t['available'] for t in tracks):
            return
        summary = tr('Destination: audio files and database') + '\n' + tr('Back up original audio before writing')
        summary += '\n\n' + '\n\n'.join(t['path'] + '\n' + json.dumps(t['tags'], ensure_ascii=False, indent=2) for t in tracks)
        if self.preview('Preview changes', summary):
            def work(cancel, progress):
                errors = []
                for track in tracks:
                    if cancel.is_set():
                        break
                    try:
                        metadata.write_safe(track['path'], track['tags'], backup_dir=self.store.profile / 'audio-backups')
                        st = Path(track['path']).stat()
                        with self.store.connection() as db:
                            db.execute('UPDATE tracks SET mtime=?,size=?,sha256=NULL,dirty=0 WHERE id=?', (st.st_mtime_ns, st.st_size, track['id']))
                        self.store.log('write', track['id'], after=track['tags'])
                    except Exception as exc:
                        errors.append(str(exc))
                        self.store.log('write_error', track['id'], after=str(exc))
                return errors
            self.start(work, lambda errors: self.error('\n'.join(errors)) if errors else None, lock_playback=True)

    def open_location(self):
        tracks = self.selected()
        if tracks:
            if os.name == 'nt':
                subprocess.Popen(['explorer.exe', '/select,', tracks[0]['path']])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(tracks[0]['path']).parent)))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Export'), 'library.json', 'JSON (*.json);;CSV (*.csv)')
        if not path:
            return
        rows = [self.model.rows[self.proxy.mapToSource(self.proxy.index(i, 0)).row()] for i in range(self.proxy.rowCount())]
        def action():
            if Path(path).exists() and not self.confirm(tr('Replace existing file?')):
                return
            with open(path, 'w', encoding='utf-8', newline='') as file:
                if Path(path).suffix.lower() == '.csv':
                    writer = csv.DictWriter(file, fieldnames=['path', 'format', *FIELDS])
                    writer.writeheader()
                    for row in rows:
                        writer.writerow({'path': row['path'], 'format': row['format'], **{k: row['tags'].get(k, '') for k in FIELDS}})
                else:
                    json.dump(rows, file, ensure_ascii=False, indent=2)
        self.guarded(action)

    def history(self):
        with self.store.connection() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM operation_history ORDER BY id DESC LIMIT 200')]
        self.preview('History', json.dumps(rows, ensure_ascii=False, indent=2))

    def closeEvent(self, event):
        self.playback.release()
        if self.worker:
            self.cancel()
            event.ignore()
            self.status.setText(tr('Wait for the current operation to stop, then close the window.'))
        else:
            event.accept()
