import csv
import json
import locale
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QCoreApplication, QModelIndex, QSortFilterProxyModel, Qt, QUrl, QTimer, QByteArray
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPalette, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSplitter, QTableView, QVBoxLayout, QWidget, QScrollArea)

from music_catalog_manager.database.store import FIELDS
from music_catalog_manager.services import backup, metadata, rename
from music_catalog_manager.services.artwork import cache_image, folder_image, validate_image
from music_catalog_manager.services.musicbrainz import MusicBrainz
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.ui.i18n import Translator, qt_translator
from music_catalog_manager.ui.worker import Worker
from music_catalog_manager.ui.playback import PlaybackBar
from music_catalog_manager.ui.widgets import ArtworkLabel
from music_catalog_manager.ui.cover_views import CoverViews
from music_catalog_manager.ui.playlist_import import PlaylistImportViews
from music_catalog_manager.ui.help_view import HelpViews


def tr(text):
    return QCoreApplication.translate('MainWindow', text)


from music_catalog_manager.ui.models import LABELS, COLUMNS, TrackModel, Filter, LibraryProxy
from music_catalog_manager.ui.library_views import LibraryViews
from music_catalog_manager.services.library import Library
from music_catalog_manager.services import audio_backups


class MainWindow(CoverViews, PlaylistImportViews, HelpViews, LibraryViews, QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.worker = None
        self.pending_result = None
        self.library = Library(store)
        self.page_offset = 0
        self.page_size = 250
        self.query_sort = 'title'
        self.query_descending = False
        self.query_generation = 0
        self.query_workers = set()
        self.loading_library = False
        self.closing = False
        self.facets_dirty = True
        self.active_playlist = None
        self.advanced_override = None
        language = store.setting('language', 'pl' if (locale.getlocale()[0] or '').startswith('Polish') or (locale.getlocale()[0] or '').startswith('pl') else 'en')
        self.translator = Translator(language)
        self.qt_translator = qt_translator(language)
        QApplication.instance().installTranslator(self.qt_translator)
        QApplication.instance().installTranslator(self.translator)
        self.setWindowTitle('Music Catalog Manager')
        self.setWindowIcon(QIcon(str(Path(__file__).parents[1] / 'resources' / 'icon.ico')))
        self.resize(1400, 900)
        self.build()
        self.apply_theme(store.setting('theme', 'system'))
        self.restore_layout()
        self.refresh()

    def button(self, text, handler, layout):
        button = QPushButton(tr(text))
        button.setAccessibleName(tr(text))
        button.clicked.connect(handler)
        if isinstance(layout, QGridLayout):
            layout.addWidget(button, layout.count() // 2, layout.count() % 2)
        else:
            layout.addWidget(button)
        return button

    def build(self):
        self.building = True
        if hasattr(self, 'playback'):
            self.playback.release()
        central = QWidget()
        shell = QWidget()
        self.setCentralWidget(shell)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        work_area = QScrollArea()
        work_area.setWidgetResizable(True)
        work_area.setFrameShape(QScrollArea.NoFrame)
        work_area.setWidget(central)
        shell_layout.addWidget(work_area, 1)
        outer = QVBoxLayout(central)
        title = QLabel('♫  Music Catalog Manager')
        self.title_label = title
        title.setStyleSheet('font-size:24px;font-weight:600;padding:12px')
        outer.addWidget(title)
        toolbar = QHBoxLayout()
        outer.addLayout(toolbar)
        self.action_buttons = []
        for label, handler in [('Add folder', self.add_folder), ('Rescan', self.rescan), ('Edit tags', self.edit_tags),
                ('Play', lambda: self.playback.toggle())]:
            self.action_buttons.append(self.button(label, handler, toolbar))
        splitter = QSplitter()
        self.splitter = splitter
        outer.addWidget(splitter, 1)
        self.sidebar = QListWidget()
        self.sidebar.addItems([tr(x) for x in ('Library', 'Folders', 'Duplicates', 'Backups', 'Settings', 'Albums', 'Playlists', 'Collection quality')])
        self.sidebar.setMaximumWidth(205)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.navigate)
        splitter.addWidget(self.sidebar)
        middle = QWidget()
        content = QVBoxLayout(middle)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Search library…'))
        self.search.setAccessibleName(tr('Search library…'))
        content.addWidget(self.search)
        self.filters_panel = QWidget()
        filters = QGridLayout(self.filters_panel)
        filters.setContentsMargins(0, 0, 0, 0)
        content.addWidget(self.filters_panel)
        self.combos = {}
        for filter_index, (key, label) in enumerate([('artist', 'Artist'), ('album', 'Album'), ('genre', 'Genre'), ('date', 'Date'), ('format', 'Format'), ('root_id', 'Folder')]):
            combo = QComboBox()
            combo.setMinimumWidth(90)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
            combo.setAccessibleName(tr(label))
            combo.setToolTip(tr(label))
            combo.currentIndexChanged.connect(self.update_filter)
            filters.addWidget(combo, filter_index // 3, filter_index % 3)
            self.combos[key] = combo
        self.install_library_controls(content)
        self.grouping_panel = QWidget()
        grouping = QHBoxLayout(self.grouping_panel)
        grouping.setContentsMargins(0, 0, 0, 0)
        content.addWidget(self.grouping_panel)
        grouping.addWidget(QLabel(tr('Group by')))
        self.group = QComboBox()
        self.group.addItems([tr(x) for x in ('None', 'Artist', 'Album', 'Folder', 'Playlist')])
        self.group.currentIndexChanged.connect(self.group_changed)
        grouping.addWidget(self.group)
        self.groups = QComboBox()
        self.groups.setMinimumWidth(160)
        self.groups.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.groups.setMinimumContentsLength(10)
        self.groups.currentIndexChanged.connect(self.group_selected)
        grouping.addWidget(self.groups)
        grouping.addStretch()
        self.table = QTableView()
        self.model = TrackModel(self)
        self.proxy = LibraryProxy(self)
        self.proxy.sortRequested.connect(self.sort_library)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
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
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.update_filter)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        content.addWidget(self.table, 1)
        self.install_page_controls(content)
        self.bottom_panel = QWidget()
        bottom = QGridLayout(self.bottom_panel)
        bottom.setContentsMargins(0, 0, 0, 0)
        content.addWidget(self.bottom_panel)
        self.button('Open location', self.open_location, bottom)
        self.undo_button = self.button('Undo database edit', self.undo, bottom)
        self.write_button = self.button('Write pending tags', self.write_pending, bottom)
        self.install_tools()
        splitter.addWidget(middle)
        right = QWidget()
        right.setMinimumWidth(200)
        right.setMaximumWidth(310)
        self.detail_panel = right
        detail = QVBoxLayout(right)
        self.cover = ArtworkLabel('♫')
        self.cover.setFixedHeight(220)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setStyleSheet('font-size:60px;border-radius:12px;background:rgba(104,122,144,35)')
        detail.addWidget(self.cover)
        self.detail_heading = QLabel()
        self.detail_heading.setTextFormat(Qt.PlainText)
        self.detail_heading.setWordWrap(True)
        self.detail_heading.setStyleSheet('font-size:18px;font-weight:600')
        detail.addWidget(self.detail_heading)
        self.detail_album = QLabel()
        self.detail_album.setTextFormat(Qt.PlainText)
        self.detail_album.setWordWrap(True)
        detail.addWidget(self.detail_album)
        self.detail_facts = QLabel()
        self.detail_facts.setTextFormat(Qt.PlainText)
        self.detail_facts.setWordWrap(True)
        detail.addWidget(self.detail_facts)
        self.cover_online_button = self.button('Find cover online', lambda: self.guarded(self.search_cover_dialog), detail)
        self.cover_local_button = self.button('Choose local image', lambda: self.guarded(self.choose_local_cover), detail)
        self.cover_online_button.setEnabled(False)
        self.cover_local_button.setEnabled(False)
        self.technical_toggle = QCheckBox(tr('Technical details'))
        detail.addWidget(self.technical_toggle)
        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        detail.addWidget(self.detail_text)
        self.technical_toggle.toggled.connect(self.detail_text.setVisible)
        self.detail_text.hide()
        detail.addStretch(1)
        splitter.addWidget(right)
        splitter.setSizes([160, 930, 270])
        self.playback = PlaybackBar(self.store, self.selected, self.visible_tracks, self)
        shell_layout.addWidget(self.playback)
        status = QHBoxLayout()
        shell_layout.addLayout(status)
        self.status = QLabel(tr('Ready'))
        status.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        status.addWidget(self.progress)
        self.cancel_button = self.button('Cancel', self.cancel, status)
        self.cancel_button.setEnabled(False)
        self.building = False
        self.adapt_layout()

    def adapt_layout(self):
        compact = self.height() < 720
        self.title_label.setVisible(not compact)
        self.detail_panel.setVisible(self.width() >= 1100)
        self.bottom_panel.setVisible(not compact)
        visible = self.advanced_override if self.advanced_override is not None else not compact
        self.filters_panel.setVisible(visible)
        self.grouping_panel.setVisible(visible)
        self.filters_toggle.blockSignals(True)
        self.filters_toggle.setChecked(visible)
        self.filters_toggle.blockSignals(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'detail_panel') and not getattr(self, 'building', False):
            self.adapt_layout()

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
        return list(self.library.all(**self.library_options()))

    def play_index(self, index):
        if index.isValid():
            self.playback.play_track(self.model.rows[self.proxy.mapToSource(index).row()])

    def refresh(self):
        self.facets_dirty = True
        self.load_library()

    def update_filter(self, *_):
        self.page_offset = 0
        self.load_library()

    def group_changed(self, *_):
        old = getattr(self, 'group_filter_key', None)
        if old in self.combos:
            self.combos[old].blockSignals(True)
            self.combos[old].setCurrentIndex(0)
            self.combos[old].blockSignals(False)
        if old == 'playlist':
            self.active_playlist = None
        self.populate_groups()
        self.groups.blockSignals(True)
        self.groups.setCurrentIndex(0)
        self.groups.blockSignals(False)
        self.group_selected()

    def group_selected(self, *_):
        key = {1: 'artist', 2: 'album', 3: 'root_id'}.get(self.group.currentIndex())
        self.group_filter_key = 'playlist' if self.group.currentIndex() == 4 else key
        if self.group.currentIndex() == 4:
            self.active_playlist = self.groups.currentData() or None
            self.query_sort = 'playlist_position' if self.active_playlist is not None else 'title'
            self.query_descending = False
            self.table.horizontalHeader().blockSignals(True)
            self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
            self.table.horizontalHeader().blockSignals(False)
            self.update_filter()
            return
        if key:
            self.combos[key].setCurrentIndex(max(0, self.combos[key].findData(self.groups.currentData())))
            self.table.sortByColumn({'artist': 1, 'album': 2, 'root_id': 7}[key], Qt.AscendingOrder)
        else:
            self.update_filter()

    def details(self, *_):
        selected = self.selected()
        if hasattr(self, 'cover_online_button'):
            self.cover_online_button.setEnabled(bool(selected) and not self.worker)
            self.cover_local_button.setEnabled(bool(selected) and not self.worker)
        self.cover.setPixmap(QPixmap())
        self.cover.setText('♫')
        if not selected:
            self.detail_heading.setText(tr('Select a track to see details.'))
            self.detail_album.clear()
            self.detail_facts.clear()
            self.detail_text.setPlainText(tr('Select a track to see details.'))
            return
        row = selected[0]
        self.detail_heading.setText(row['tags'].get('title') or Path(row['path']).stem)
        self.detail_album.setText('\n'.join(filter(None, (row['tags'].get('artist'), row['tags'].get('album')))))
        facts = [row['tags'].get('genre', ''), row['tags'].get('date', ''), row['format'], f"{int(row['duration'] or 0)//60}:{int(row['duration'] or 0)%60:02}", f"{(row['bitrate'] or 0)//1000} kbps"]
        self.detail_facts.setText(' · '.join(filter(None, facts)))
        text = '\n'.join(tr(LABELS[k]) + ': ' + row['tags'].get(k, '') for k in FIELDS)
        text += f"\n\n{row['format']} · {row['size'] or 0:,} B · {row['bitrate'] or 0} bps\n{row['path']}"
        if row['sha256'] in self.proxy.hashes:
            text += '\n' + tr('Confirmed duplicate (SHA-256)')
        if not metadata.writable(row['path']):
            text += '\n' + tr('Read-only format')
        self.detail_text.setPlainText(text)
        if row['artwork']:
            pix = QPixmap(str(self.store.cache / row['artwork']))
            if not pix.isNull():
                self.cover.setPixmap(pix)

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
        self.tools_menu.setEnabled(False)
        self.cover_online_button.setEnabled(False)
        self.cover_local_button.setEnabled(False)
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
        self.tools_menu.setEnabled(True)
        self.refresh()
        result, callback = self.pending_result, self.done_callback
        self.pending_result = None
        if result is not None and not self.closing:
            self.guarded(lambda: callback(result[0]))
        if self.closing:
            self.close()

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
        preview_button = buttons.addButton(tr('Save in catalog'), QDialogButtonBox.AcceptRole)
        disk.toggled.connect(lambda enabled: preview_button.setText(tr('Save to files') if enabled else tr('Save in catalog')))
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
        import uuid
        operation_id = uuid.uuid4().hex
        def work(cancel, progress):
            errors = []
            for track_index, track in enumerate(tracks):
                if cancel.is_set():
                    break
                try:
                    if disk:
                        backup_path = metadata.write_safe(track['path'], changes, image, self.store.profile / 'audio-backups' if copies else None)
                        audio_backups.register(self.store, track['id'], track['path'], backup_path)
                    if changes:
                        self.store.edit([track['id']], changes, operation_id)
                    if image:
                        cache_image(self.store, track['id'], image, 'manual')
                    if disk:
                        st = Path(track['path']).stat()
                        with self.store.connection() as db:
                            # Pending database fields remain pending unless the complete tag set was written.
                            pending = self.store.track(track['id'])['tags']
                            actual = metadata.read(track['path'])['tags']
                            dirty = int(any(actual.get(k, '') != pending.get(k, '') for k in FIELDS))
                            db.execute('UPDATE tracks SET mtime=?,size=?,sha256=NULL,dirty=?,file_key=? WHERE id=?', (st.st_mtime_ns, st.st_size, dirty, f'{st.st_dev}:{st.st_ino}', track['id']))
                    self.store.log('write' if disk else 'database', track['id'], after=changes)
                    progress({'processed': track_index + 1, 'total': len(tracks)})
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
                    self.start(lambda cancel, progress: rename.execute(self.store, plan, cancel, progress), lock_playback=True)
            self.guarded(action)

    def internet(self, action, done, contact=None, with_progress=False):
        contact = self.store.setting('contact', '') if contact is None else contact
        if not contact:
            QMessageBox.information(self, tr('Settings'), tr('Configure a contact email or URL in Settings before using internet services.'))
            return
        def work(cancel, progress):
            client = MusicBrainz(self.store.profile, contact, cancel)
            try:
                return action(client, progress) if with_progress else action(client)
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
        choices = [tr('Find cover online'), tr('Choose local image'), tr('Cover Art Archive (MBID)')]
        value, ok = QInputDialog.getItem(self, tr('Artwork'), tr('Source'), choices, 0, False)
        if not ok:
            return
        if value == choices[0]:
            self.search_cover_dialog(tracks)
        elif value == choices[1]:
            self.choose_local_cover(tracks)
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
            targets = {}
            for track in tracks:
                targets.setdefault(Path(track['path']).parent, []).append(track)
            approved = []
            for folder, members in targets.items():
                target = folder / 'folder.jpg'
                if choice == choices[2] and target.exists() and not self.confirm(tr('Replace existing file?') + '\n' + str(target)):
                    continue
                approved.append((folder, members))
            def work(cancel, progress):
                for index, (folder, members) in enumerate(approved):
                    if cancel.is_set():
                        break
                    if choice == choices[2]:
                        folder_image(members[0]['path'], data, (folder / 'folder.jpg').exists())
                    for track in members:
                        cache_image(self.store, track['id'], data, 'Cover Art Archive' if release else 'local', release)
                    progress({'folders': index + 1, 'total': len(approved)})
            self.start(work)

    def create_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Create backup'), str(self.store.profile / 'MusicCatalog.zip'), 'ZIP (*.zip)')
        if path:
            self.start(lambda cancel, progress: backup.create(self.store, path, cancel, progress), lambda _: QMessageBox.information(self, tr('Create backup'), tr('Backup created. Audio files are not included.')))

    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Restore backup'), '', 'ZIP (*.zip)')
        if path:
            def action():
                manifest = backup.inspect(path)
                summary = tr('Replace current library? A safety backup will be created. Audio files are not restored.') + '\n\n' + json.dumps(manifest, indent=2)
                if self.preview('Restore backup', summary):
                    self.start(lambda cancel, progress: backup.restore(self.store, path, cancel, progress), lambda _: self.refresh(), lock_playback=True)
            self.guarded(action)

    def navigate(self, index):
        if self.worker:
            return
        if index in (0, 2):
            self.proxy.duplicates = index == 2
            self.active_playlist = None
            if self.group.currentIndex() == 4:
                self.group.setCurrentIndex(0)
            self.update_filter()
            return
        handlers = {1: self.folders_dialog, 3: self.backups_dialog, 4: self.settings,
                    5: self.albums_dialog, 6: self.playlists_dialog, 7: self.quality_dialog}
        if index in handlers:
            self.guarded(handlers[index])
        self.sidebar.blockSignals(True)
        self.sidebar.setCurrentRow(2 if self.proxy.duplicates else 0)
        self.sidebar.blockSignals(False)

    def folders(self):
        self.folders_dialog()

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
            self.save_layout()
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
            self.restore_layout()
            self.refresh()

    def undo(self):
        if self.worker:
            return
        count = self.store.undo_count()
        if count and self.confirm(tr('Undo database changes for tracks:') + ' ' + str(count)):
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
                        backup_path = metadata.write_safe(track['path'], track['tags'], backup_dir=self.store.profile / 'audio-backups')
                        audio_backups.register(self.store, track['id'], track['path'], backup_path)
                        st = Path(track['path']).stat()
                        with self.store.connection() as db:
                            db.execute('UPDATE tracks SET mtime=?,size=?,sha256=NULL,dirty=0,file_key=? WHERE id=?', (st.st_mtime_ns, st.st_size, f'{st.st_dev}:{st.st_ino}', track['id']))
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
        if self.worker:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr('Export'), 'library.json', 'JSON (*.json);;CSV (*.csv)')
        if not path or (Path(path).exists() and not self.confirm(tr('Replace existing file?'))):
            return
        from music_catalog_manager.services.export import export_library
        options = self.library_options()
        self.start(lambda cancel, progress: export_library(self.store, options, path, cancel, progress))

    def history(self):
        with self.store.connection() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM operation_history ORDER BY id DESC LIMIT 200')]
        dialog, _ = self.table_dialog('History', ['Created', 'Action', 'Tracks', 'Details'], [(r['created'], r['kind'], r['track_id'], r['after_data']) for r in rows])
        dialog.exec()

    def shutdown(self):
        self.closing = True
        self.query_generation += 1
        if self.worker:
            self.worker.cancel.set()
            self.worker.wait()
        for worker in list(self.query_workers):
            worker.wait()
        self.playback.release()

    def closeEvent(self, event):
        self.save_layout()
        self.playback.release()
        if self.worker:
            self.closing = True
            self.cancel()
            event.ignore()
            self.status.setText(tr('Cancelling…'))
        else:
            self.closing = True
            self.query_generation += 1
            for worker in list(self.query_workers):
                worker.wait()
            event.accept()
