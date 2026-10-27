"""Library navigation and feature dialogs, separate from file editing workflows."""
import json
import uuid
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QSize
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QLineEdit,
    QListWidgetItem, QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout)

from music_catalog_manager.services import audio_backups, backup, organize, playlists
from music_catalog_manager.ui.models import COLUMNS, tr
from music_catalog_manager.ui.worker import Worker


class LibraryViews:
    def install_library_controls(self, content):
        line = QHBoxLayout()
        self.quick_filter = QComboBox()
        for label, key in [('All tracks', ''), ('Missing tags', 'missing'), ('Without artwork', 'artwork'),
                           ('Database changes', 'pending'), ('Unavailable', 'unavailable')]:
            self.quick_filter.addItem(tr(label), key)
        self.quick_filter.setAccessibleName(tr('Quick filter'))
        self.quick_filter.currentIndexChanged.connect(self.update_filter)
        line.addWidget(self.quick_filter)
        self.active_filters = QLabel()
        self.active_filters.setTextFormat(Qt.PlainText)
        self.active_filters.setWordWrap(True)
        line.addWidget(self.active_filters, 1)
        self.filters_toggle = QPushButton(tr('Advanced filters'))
        self.filters_toggle.setCheckable(True)
        def toggle(visible):
            self.advanced_override = visible
            self.adapt_layout()
        self.filters_toggle.toggled.connect(toggle)
        line.addWidget(self.filters_toggle)
        clear = QPushButton(tr('Clear filters'))
        clear.clicked.connect(self.clear_filters)
        line.addWidget(clear)
        content.addLayout(line)

    def install_page_controls(self, content):
        line = QHBoxLayout()
        self.previous_page = QPushButton(tr('Previous page'))
        self.next_page = QPushButton(tr('Next page'))
        self.page_label = QLabel()
        self.previous_page.clicked.connect(lambda: self.change_page(-1))
        self.next_page.clicked.connect(lambda: self.change_page(1))
        line.addWidget(self.previous_page)
        line.addWidget(self.page_label, 1)
        line.addWidget(self.next_page)
        content.addLayout(line)

    def install_tools(self):
        self.menuBar().clear()
        self.tools_menu = self.menuBar().addMenu(tr('Tools'))
        self.selection_actions = []
        commands = [('Find metadata', self.find_metadata, True), ('Album metadata', self.album_metadata, True),
                    ('Artwork', self.artwork_dialog, True), ('Rename', self.rename_tracks, True),
                    ('Find cover online', self.search_cover_dialog, True), ('Choose local image', self.choose_local_cover, True),
                    ('Import playlists from folder', self.import_playlist_folder, False),
                    ('Tags from filename', self.tags_from_filename, True),
                    ('Save selection as playlist', self.save_playlist, True),
                    ('Compare recordings', self.compare_recordings, False),
                    ('Create backup', self.create_backup, False), ('Restore original audio', self.restore_audio_dialog, False),
                    ('Collection quality', self.quality_dialog, False), ('Track details', self.track_details_dialog, True),
                    ('Open location', self.open_location, True), ('Undo database edit', self.undo, False),
                    ('Write pending tags', self.write_pending, True),
                    ('Export', self.export, False), ('History', self.history, False)]
        for label, callback, needs_selection in commands:
            action = self.tools_menu.addAction(tr(label))
            action.triggered.connect(lambda checked=False, fn=callback: self.guarded(fn) if not self.worker else None)
            if needs_selection:
                self.selection_actions.append(action)
        columns = self.menuBar().addMenu(tr('Columns'))
        for index, (_, label) in enumerate(COLUMNS):
            action = columns.addAction(tr(label))
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(index))
            action.toggled.connect(lambda visible, i=index: self.table.setColumnHidden(i, not visible))
        self.column_actions = columns.actions()
        self.install_help_menu()
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(lambda point: self.tools_menu.exec(self.table.viewport().mapToGlobal(point)))
        self.table.selectionModel().selectionChanged.connect(self.selection_actions_changed)
        self.selection_actions_changed()

    def selection_actions_changed(self, *_):
        selected = bool(self.table.selectionModel().selectedRows())
        for action in self.selection_actions:
            action.setEnabled(selected)

    def library_options(self):
        filters = {key: combo.currentData() or '' for key, combo in self.combos.items()}
        if getattr(self, 'album_artist_filter', None):
            filters['album_identity'] = self.album_artist_filter
        return dict(query=self.search.text(), filters=filters,
                    quick=self.quick_filter.currentData() or '', duplicates=self.proxy.duplicates,
                    playlist=self.active_playlist, sort=self.query_sort, descending=self.query_descending)

    def sort_library(self, column, order):
        if column < 0:
            return
        self.query_sort = COLUMNS[column][0]
        self.query_descending = order == Qt.DescendingOrder
        if not getattr(self, 'building', False) and hasattr(self, 'quick_filter') and hasattr(self, 'playback'):
            self.page_offset = 0
            self.load_library()

    def load_library(self):
        if self.closing or not hasattr(self, 'quick_filter'):
            return
        self.query_generation += 1
        generation = self.query_generation
        self.loading_library = True
        self.table.setEnabled(False)
        # Coalesce rapid filter changes into one pending request.
        if self.query_workers:
            self.query_pending = True
            for worker in self.query_workers:
                worker.cancel.set()
            return
        self.query_pending = False
        options, offset = self.library_options(), self.page_offset
        facets_needed = self.facets_dirty
        selected_ids = {t['id'] for t in self.selected()}
        self.previous_page.setEnabled(False)
        self.next_page.setEnabled(False)
        self.page_label.setText(tr('Loading…'))
        def work(cancel, progress):
            rows, count = self.library.page(**options, offset=offset, limit=self.page_size, cancel=cancel)
            facets = self.library.facets(cancel) if facets_needed else None
            with self.store.connection() as db:
                db.set_progress_handler(lambda: int(cancel.is_set()), 1000)
                total = db.execute('SELECT count(*) FROM tracks').fetchone()[0]
                hashes = {r[0] for r in db.execute('SELECT sha256 FROM tracks WHERE sha256 IS NOT NULL GROUP BY sha256 HAVING count(*)>1')}
            return rows, count, total, facets, hashes
        worker = Worker(work, self)
        self.query_workers.add(worker)
        def receive(result):
            if generation != self.query_generation or self.closing:
                return
            rows, count, total, facets, hashes = result
            if offset >= count and offset > 0:
                self.page_offset = max(0, ((count - 1) // self.page_size) * self.page_size)
                self.load_library()
                return
            self.model.replace(rows)
            self.proxy.hashes = hashes
            if facets is not None:
                roots = {str(r['id']): r['path'] for r in self.store.roots()}
                for key, combo in self.combos.items():
                    previous = combo.currentData()
                    combo.blockSignals(True)
                    combo.clear()
                    combo.addItem(tr('All') + ': ' + tr(dict(artist='Artist', album='Album', genre='Genre', date='Date', format='Format', root_id='Folder')[key]), '')
                    for value in facets[key]:
                        combo.addItem(roots.get(value, value) if key == 'root_id' else value, value)
                    combo.setCurrentIndex(max(0, combo.findData(previous)))
                    combo.blockSignals(False)
                self.facets_dirty = False
                self.populate_groups()
            self.loading_library = False
            self.table.setEnabled(True)
            self.previous_page.setEnabled(offset > 0)
            self.next_page.setEnabled(offset + len(rows) < count)
            self.page_label.setText(f'{offset + 1 if count else 0}–{offset + len(rows)} / {count}')
            self.status.setText(tr('Tracks') + f': {count} / {total}')
            labels = [combo.currentText() for combo in self.combos.values() if combo.currentData()]
            if options['query']:
                labels.insert(0, options['query'])
            if options['quick']:
                labels.append(self.quick_filter.currentText())
            if self.active_playlist is not None:
                labels.append(tr('Playlist') + ': ' + self.groups.currentText())
            if self.proxy.duplicates:
                labels.append(tr('Duplicates'))
            self.active_filters.setText(' · '.join(labels))
            selection = self.table.selectionModel()
            from PySide6.QtCore import QItemSelectionModel
            for index, row in enumerate(rows):
                if row['id'] in selected_ids:
                    selection.select(self.proxy.index(index, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
            self.details()
            undo_count = self.store.undo_count()
            self.undo_button.setText(tr('Undo database edit') + f' ({undo_count})')
            self.undo_button.setEnabled(undo_count > 0 and not self.worker)
            if total == 0:
                self.detail_heading.setText(tr('Empty library. Add a music folder to begin.'))
            if self.proxy.duplicates and not count:
                self.active_filters.setText(tr('No confirmed duplicates. Enable SHA-256 and rescan if needed.'))
        worker.result.connect(receive)
        def failed(message):
            if generation == self.query_generation and not self.closing:
                self.loading_library = False
                self.table.setEnabled(True)
                self.page_label.setText(tr('Operation failed'))
                self.error(message)
        worker.failed.connect(failed)
        def finished():
            self.query_workers.discard(worker)
            worker.deleteLater()
            if getattr(self, 'query_pending', False) and not self.closing:
                self.load_library()
        worker.finished.connect(finished)
        worker.start()

    def populate_groups(self):
        previous = self.groups.currentData()
        self.groups.blockSignals(True)
        self.groups.clear()
        self.groups.addItem(tr('All'), '')
        key = {1: 'artist', 2: 'album', 3: 'root_id'}.get(self.group.currentIndex())
        if self.group.currentIndex() == 4:
            for item in playlists.lists(self.store):
                self.groups.addItem(f"{item['name']} ({item['tracks']})", item['id'])
        elif key:
            source = self.combos[key]
            for i in range(1, source.count()):
                self.groups.addItem(source.itemText(i), source.itemData(i))
        self.groups.setCurrentIndex(max(0, self.groups.findData(previous)))
        self.groups.blockSignals(False)
        if self.group.currentIndex() == 4 and self.active_playlist is not None and self.groups.findData(self.active_playlist) < 0:
            self.active_playlist = None
            self.update_filter()

    def clear_filters(self):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        for combo in [*self.combos.values(), self.quick_filter, self.group]:
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.active_playlist = None
        self.group_filter_key = None
        if self.query_sort == 'playlist_position':
            self.query_sort = 'title'
        self.album_artist_filter = None
        self.proxy.duplicates = False
        self.populate_groups()
        self.sidebar.blockSignals(True)
        self.sidebar.setCurrentRow(0)
        self.sidebar.blockSignals(False)
        self.update_filter()

    def change_page(self, direction):
        self.page_offset = max(0, self.page_offset + direction * self.page_size)
        self.load_library()

    def save_layout(self):
        self.store.set_setting('window_layout', dict(geometry=bytes(self.saveGeometry()).hex(),
            header=bytes(self.table.horizontalHeader().saveState()).hex(), splitter=self.splitter.sizes(),
            sort=self.query_sort, descending=self.query_descending))

    def restore_layout(self):
        saved = self.store.setting('window_layout', {})
        try:
            if saved.get('geometry'):
                self.restoreGeometry(QByteArray.fromHex(saved['geometry'].encode()))
            if saved.get('header'):
                self.table.horizontalHeader().restoreState(QByteArray.fromHex(saved['header'].encode()))
            if saved.get('splitter'):
                self.splitter.setSizes(saved['splitter'])
            if saved.get('sort') in dict(COLUMNS):
                self.query_sort = saved['sort']
                self.query_descending = saved.get('descending', False)
            for i, action in enumerate(self.column_actions):
                action.setChecked(not self.table.isColumnHidden(i))
        except (ValueError, TypeError):
            pass

    def table_dialog(self, title, headers, rows, buttons=()):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(title))
        dialog.resize(1000, 580)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels([tr(h) for h in headers])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value or ''))
                item.setToolTip(str(value or ''))
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        actions = QGridLayout() if len(buttons) > 4 else QHBoxLayout()
        for index, (label, callback) in enumerate(buttons):
            button = QPushButton(tr(label))
            button.clicked.connect(lambda checked=False, fn=callback: self.guarded(lambda: fn(table.currentRow(), dialog)))
            if isinstance(actions, QGridLayout):
                actions.addWidget(button, index // 3, index % 3)
            else:
                actions.addWidget(button)
        close = QPushButton(tr('Close'))
        close.clicked.connect(dialog.reject)
        if isinstance(actions, QGridLayout):
            actions.addWidget(close, len(buttons) // 3, len(buttons) % 3)
        else:
            actions.addWidget(close)
        layout.addLayout(actions)
        if rows:
            table.selectRow(0)
        return dialog, table

    def albums_dialog(self):
        albums = self.library.albums()
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Albums'))
        dialog.resize(940, 600)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText(tr('Search albums…'))
        layout.addWidget(search)
        view = QListWidget()
        view.setViewMode(QListWidget.IconMode)
        view.setResizeMode(QListWidget.Adjust)
        view.setIconSize(QSize(130, 130))
        view.setGridSize(QSize(185, 205))
        view.setWordWrap(True)
        for album in albums:
            item = QListWidgetItem(f"{album['album'] or tr('Unknown album')}\n{album['artist']}\n{album['tracks']} " + tr('tracks'))
            item.setData(Qt.UserRole, album)
            if album['artwork']:
                item.setIcon(QIcon(str(self.store.cache / album['artwork'])))
            else:
                item.setIcon(self.windowIcon())
            view.addItem(item)
        def open_album(item):
            album = item.data(Qt.UserRole)
            # Album artist is part of identity: albums with the same title stay separate.
            self.clear_filters()
            combo = self.combos['album']
            combo.setCurrentIndex(max(0, combo.findData(album['album'])))
            self.album_artist_filter = album['artist']
            self.table.sortByColumn(9, Qt.AscendingOrder)
            self.update_filter()
            dialog.accept()
        view.itemDoubleClicked.connect(open_album)
        search.textChanged.connect(lambda text: [view.item(i).setHidden(text.casefold() not in view.item(i).text().casefold()) for i in range(view.count())])
        layout.addWidget(view)
        close = QPushButton(tr('Close'))
        close.clicked.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def folders_dialog(self):
        rows = self.library.folders()
        def rescan(index, dialog):
            if index >= 0:
                dialog.accept()
                self.scan_roots([rows[index]])
        def relink(index, dialog):
            if index < 0:
                return
            root = rows[index]
            target = QFileDialog.getExistingDirectory(self, tr('New location'))
            if target and self.confirm(root['path'] + ' → ' + target):
                dialog.accept()
                self.start(lambda cancel, progress: self.store.relink(root['id'], target), lock_playback=True)
        dialog, _ = self.table_dialog('Folders', ['Folder', 'Tracks', 'Available', 'Last scan'],
            [(r['path'], r['tracks'], r['available'], r['scanned'] or '—') for r in rows],
            [('Rescan', rescan), ('New location', relink)])
        dialog.exec()

    def backups_dialog(self):
        rows = []
        for path in self.store.profile.glob('*.zip'):
            try:
                manifest = backup.inspect(path)
                rows.append((path, manifest))
            except Exception:
                continue
        def restore(index, dialog):
            if index >= 0 and self.confirm(tr('Replace current library? A safety backup will be created. Audio files are not restored.')):
                dialog.accept()
                self.start(lambda cancel, progress: backup.restore(self.store, rows[index][0], cancel, progress), lock_playback=True)
        def create(index, dialog):
            dialog.accept()
            self.create_backup()
        def browse(index, dialog):
            dialog.accept()
            self.restore_backup()
        dialog, _ = self.table_dialog('Backups', ['Location', 'Created', 'Contents'],
            [(str(path), m['created'], tr('Database and artwork; no audio')) for path, m in rows],
            [('Create backup', create), ('Restore backup', restore), ('Choose backup…', browse),
             ('Restore original audio', lambda i, d: self.restore_audio_dialog())])
        dialog.exec()

    def restore_audio_dialog(self):
        rows = audio_backups.entries(self.store)
        def restore(index, dialog):
            if index < 0:
                return
            row = rows[index]
            if self.preview('Restore original audio', tr('Replace audio and catalog tags from this backup. A safety copy will be created.') + '\n\n' + row['backup_path'] + '\n→ ' + str(row['current_path'])):
                dialog.accept()
                self.start(lambda cancel, progress: audio_backups.restore(self.store, row['id']), lock_playback=True)
        dialog, _ = self.table_dialog('Restore original audio', ['Created', 'Original location', 'Current location', 'Backup'],
            [(r['created'], r['original_path'], r['current_path'], r['backup_path']) for r in rows], [('Restore', restore)])
        dialog.exec()

    def save_playlist(self):
        rows = self.selected()
        if not rows:
            return
        name, ok = QInputDialog.getText(self, tr('Playlist'), tr('Name'))
        if ok:
            playlists.save(self.store, name, [r['id'] for r in rows])
            self.status.setText(tr('Playlist saved.'))
            self.refresh()

    def playlists_dialog(self):
        rows = playlists.lists(self.store)
        def play(index, dialog):
            if index >= 0:
                self.playback.set_queue(playlists.tracks(self.store, rows[index]['id']))
        def show(index, dialog):
            if index >= 0:
                self.clear_filters()
                self.group.setCurrentIndex(4)
                self.groups.setCurrentIndex(self.groups.findData(rows[index]['id']))
                dialog.accept()
        def export(index, dialog):
            if index >= 0:
                path, _ = QFileDialog.getSaveFileName(self, tr('Export'), rows[index]['name'] + '.m3u8', 'M3U (*.m3u8 *.m3u)')
                if path:
                    playlists.export_m3u(path, playlists.tracks(self.store, rows[index]['id']))
        def import_list(index, dialog):
            from music_catalog_manager.ui.playlist_import import PLAYLIST_FILTER
            path, _ = QFileDialog.getOpenFileName(self, tr('Import playlist'), '', PLAYLIST_FILTER)
            if not path:
                return
            dialog.accept()
            def done(result):
                ids, missing = result
                name, ok = QInputDialog.getText(self, tr('Playlist'), tr('Name'), text=Path(path).stem)
                if ok and self.preview('Import playlist', tr('Matched tracks:') + f' {len(ids)}\n' + tr('Unmatched paths:') + '\n' + '\n'.join(missing)):
                    if not name.strip():
                        raise ValueError(tr('Playlist name is required'))
                    from music_catalog_manager.database.store import normalized
                    def saved(results):
                        if results[0]['error']:
                            self.error(results[0]['error'])
                    self.start(lambda cancel, progress: playlists.import_files(self.store, [Path(path)], cancel=cancel,
                        progress=progress, names={normalized(path): name.strip()}), saved)
            self.start(lambda cancel, progress: playlists.import_file(self.store, path, cancel), done)
        def edit(index, dialog):
            if index < 0:
                return
            self.edit_playlist(rows[index])
            self.refresh()
            dialog.accept()
        def remove(index, dialog):
            if index >= 0 and self.confirm(tr('Delete playlist?') + '\n' + rows[index]['name']):
                playlists.remove(self.store, rows[index]['id'])
                self.refresh()
                dialog.accept()
        def import_folder(index, dialog):
            dialog.accept()
            self.import_playlist_folder()
        dialog, _ = self.table_dialog('Playlists', ['Name', 'Tracks'], [(r['name'], r['tracks']) for r in rows],
            [('Play', play), ('Show tracks', show), ('Edit', edit), ('Import playlist', import_list),
             ('Import playlists from folder', import_folder), ('Export', export), ('Delete', remove)])
        dialog.exec()

    def edit_playlist(self, playlist):
        dialog = QDialog(self)
        dialog.setWindowTitle(playlist['name'])
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(tr('Drag tracks to reorder. Select and remove unwanted entries.')))
        view = QListWidget()
        view.setDragDropMode(QAbstractItemView.InternalMove)
        for row in playlists.tracks(self.store, playlist['id']):
            item = QListWidgetItem((row['tags'].get('title') or Path(row['path']).name) + ' — ' + row['tags'].get('artist', ''))
            item.setData(Qt.UserRole, row['id'])
            view.addItem(item)
        layout.addWidget(view)
        remove = QPushButton(tr('Remove selected'))
        remove.clicked.connect(lambda: view.takeItem(view.currentRow()) if view.currentRow() >= 0 else None)
        layout.addWidget(remove)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            playlists.save(self.store, playlist['name'], [view.item(i).data(Qt.UserRole) for i in range(view.count())], playlist['id'])

    def tags_from_filename(self):
        tracks = self.selected()
        template, ok = QInputDialog.getText(self, tr('Tags from filename'), tr('Template'), text='{tracknumber} - {artist} - {title}')
        if not ok:
            return
        plans = [(t, organize.parse_filename(t['path'], template)) for t in tracks]
        summary = '\n\n'.join(t['path'] + '\n' + '\n'.join(tr(k) + ': ' + t['tags'].get(k, '') + ' → ' + v for k, v in changes.items()) for t, changes in plans)
        if self.preview('Preview changes', tr('Destination: database only') + '\n\n' + summary):
            operation_id = uuid.uuid4().hex
            for track, changes in plans:
                self.store.edit([track['id']], changes, operation_id)
            self.refresh()

    def track_details_dialog(self):
        tracks = self.selected()
        if not tracks:
            return
        row = tracks[0]
        from music_catalog_manager.ui.models import LABELS
        dialog, _ = self.table_dialog('Track details', ['Field', 'Value'],
            [(tr(LABELS.get(k, k)), v) for k, v in row['tags'].items()] +
            [(tr('Location'), row['path']), (tr('Format'), row['format']), (tr('Duration'), row['duration'])])
        dialog.exec()

    def quality_dialog(self):
        def done(issues):
            labels = {'missing_tags': 'Missing tags', 'missing_artwork': 'Without artwork', 'unavailable': 'Unavailable',
                      'artist_variants': 'Artist spelling variants', 'album_numbering': 'Album numbering', 'invalid_track_total': 'Invalid track total'}
            display = [(tr(labels[i['kind']]), i.get('path') or ' · '.join(i.get('album', [])) or ', '.join(i.get('values', [])),
                        ', '.join(tr(k) for k in i.get('fields', [])) if 'fields' in i else
                        (tr('Missing:') + str(i.get('missing', [])) + '; ' + tr('Repeated:') + str(i.get('repeated', []))) if i['kind'] == 'album_numbering' else '') for i in issues]
            def export(index, dialog):
                path, _ = QFileDialog.getSaveFileName(self, tr('Export'), 'quality.json', 'JSON (*.json)')
                if path:
                    Path(path).write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding='utf-8')
            dialog, _ = self.table_dialog('Collection quality', ['Issue', 'Location / Album', 'Details'], display, [('Export', export)])
            dialog.exec()
        self.start(lambda cancel, progress: organize.quality(self.library.all(cancel=cancel), cancel), done)

    def compare_recordings(self):
        choices = [tr('Metadata and duration — library candidates'), tr('Compare selected audio — first 60 seconds')]
        choice, ok = QInputDialog.getItem(self, tr('Compare recordings'), tr('Method'), choices, 0, False)
        if not ok:
            return
        if choice == choices[1]:
            tracks = self.selected()
            if not 2 <= len(tracks) <= 20:
                QMessageBox.information(self, tr('Compare recordings'), tr('Select between 2 and 20 tracks.'))
                return
            from music_catalog_manager.services.audio_compare import compare
            def audio_done(result):
                matches, errors = result
                dialog, _ = self.table_dialog('Audio similarity — suggestions, not proof of identity',
                    ['First file', 'Second file', 'Similarity / 100'],
                    [(r['left'], r['right'], r['score']) for r in matches] + [(r['path'], r['error'], '—') for r in errors])
                dialog.exec()
            self.start(lambda cancel, progress: compare(tracks, cancel, progress), audio_done)
            return
        def done(results):
            dialog, _ = self.table_dialog('Possible similar recordings — verify before changing files',
                ['Artist', 'Title', 'First file', 'Second file', 'Duration difference'],
                [(r['artist'], r['title'], r['left'], r['right'], r['duration_difference']) for r in results])
            dialog.exec()
        self.start(lambda cancel, progress: organize.similar(self.library.all(cancel=cancel), cancel), done)

    def album_metadata(self):
        tracks = self.selected()
        if not tracks:
            return
        albums = {organize.normalized_name(t['tags'].get('album', '')) for t in tracks}
        if len(albums) != 1:
            QMessageBox.information(self, tr('Album metadata'), tr('Select tracks from one album.'))
            return
        first = tracks[0]['tags']
        if not self.confirm(tr('Send album and artist to MusicBrainz?')):
            return
        def choose(releases):
            def select(index, dialog):
                if index < 0:
                    return
                release = releases[index]
                dialog.accept()
                self.internet(lambda client: client.release_tracks(release['id']), apply)
            dialog, _ = self.table_dialog('Choose album release', ['Album', 'Date', 'Country', 'Tracks', 'Release MBID'],
                [(r.get('title'), r.get('date'), r.get('country'), r.get('track-count'), r['id']) for r in releases], [('Preview', select)])
            dialog.exec()
        def apply(remote):
            plans, skipped = [], []
            for track in tracks:
                tags = track['tags']
                number = tags.get('tracknumber', '').split('/')[0]
                disc = tags.get('discnumber', '').split('/')[0] or '1'
                matches = [r for r in remote if r['tracknumber'].split('/')[0].lstrip('0') == number.lstrip('0') and r['discnumber'].split('/')[0] == disc] if number else []
                if not matches and tags.get('title'):
                    matches = [r for r in remote if organize.normalized_name(r['title']) == organize.normalized_name(tags['title'])]
                if len(matches) == 1:
                    plans.append((track, {k: v for k, v in matches[0].items() if v}))
                else:
                    skipped.append(track['path'])
            summary = tr('Destination: database only') + '\n\n' + '\n\n'.join(t['path'] + '\n' + '\n'.join(k + ': ' + t['tags'].get(k, '') + ' → ' + v for k, v in changes.items()) for t, changes in plans)
            summary += '\n\n' + tr('Unmatched paths:') + '\n' + '\n'.join(skipped)
            if plans and self.preview('Preview changes', summary):
                operation_id = uuid.uuid4().hex
                for track, changes in plans:
                    self.store.edit([track['id']], changes, operation_id)
                self.refresh()
            elif not plans:
                QMessageBox.information(self, tr('Album metadata'), tr('No unambiguous matches. Check track and disc numbers.'))
        self.internet(lambda client: client.releases(first.get('albumartist') or first.get('artist', ''), first.get('album', '')), choose)
