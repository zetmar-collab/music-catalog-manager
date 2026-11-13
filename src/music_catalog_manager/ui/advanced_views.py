"""Editors for optional collection features."""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QComboBox,
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QFileDialog, QMessageBox, QCheckBox)
from music_catalog_manager.ui.models import tr
from music_catalog_manager.services import smart_playlists


class AdvancedViews:
    def create_portable_collection(self):
        from pathlib import Path
        from music_catalog_manager.services import portable_backup
        path, _ = QFileDialog.getSaveFileName(self, tr('Portable collection backup'), str(self.store.profile / 'Collection.zip'), 'ZIP (*.zip)')
        if path:
            self.start(lambda cancel, progress: portable_backup.create(self.store, path, cancel, progress),
                lambda result: QMessageBox.information(self, tr('Portable collection backup'), tr('Collection saved. Missing audio files:') + ' ' + str(len(result['missing']))))

    def restore_portable_collection(self):
        from pathlib import Path
        from PySide6.QtWidgets import QInputDialog
        from music_catalog_manager.services import portable_backup
        path, _ = QFileDialog.getOpenFileName(self, tr('Restore portable collection'), '', 'ZIP (*.zip)')
        if not path:
            return
        def preview(manifest):
            parent = QFileDialog.getExistingDirectory(self, tr('Choose destination parent folder'))
            if not parent:
                return
            name, ok = QInputDialog.getText(self, tr('New collection folder'), tr('Name'), text='Restored Music Collection')
            if not ok or not name.strip():
                return
            if Path(name).name != name or name in ('.', '..') or any(c in name for c in '<>:"/\\|?*'):
                raise ValueError(tr('Invalid folder name'))
            destination = Path(parent) / name
            if not self.preview('Restore portable collection', str(destination) + '\n' + tr('Tracks') + ': ' + str(len(manifest['tracks'])) + '\n' + tr('Required disk space:') + ' ' + str(manifest['uncompressed_bytes'])):
                return
            def restored(profile):
                QMessageBox.information(self, tr('Restore portable collection'), tr('Collection restored to:') + '\n' + str(profile.parent))
                if self.confirm(tr('Open restored collection in a new window?')):
                    import subprocess
                    import sys
                    command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'music_catalog_manager.main']
                    subprocess.Popen([*command, '--profile', str(profile)])
            self.start(lambda cancel, progress: portable_backup.restore(path, destination, cancel, progress), restored)
        self.start(lambda cancel, progress: portable_backup.inspect(path), preview)

    def backup_retention_dialog(self):
        from PySide6.QtWidgets import QInputDialog
        from music_catalog_manager.services import backup_retention
        keep, ok = QInputDialog.getInt(self, tr('Backup retention'), tr('Keep newest ordinary backups'), self.store.setting('backup_keep', 5), 1, 10000)
        if not ok:
            return
        self.store.set_setting('backup_keep', keep)
        def preview(paths):
            if not paths:
                QMessageBox.information(self, tr('Backup retention'), tr('No old backups to remove. Safety backups are protected.'))
                return
            if self.preview('Remove old backups', tr('Permanently remove these backup archives? Safety backups are protected.') + '\n\n' + '\n'.join(str(p) for p in paths)):
                self.start(lambda cancel, progress: backup_retention.remove(self.store, paths, confirmed=True))
        self.start(lambda cancel, progress: backup_retention.candidates(self.store, keep), preview)

    def skipped_tracks_dialog(self):
        rows = list(self.playback.skipped)
        def retry(index, dialog):
            self.playback.failed_entries.clear()
            if index >= 0:
                target = next((i for i, r in enumerate(self.playback.queue) if r['path'] == rows[index]['path']), None)
                if target is not None:
                    self.playback.current = target
                    self.playback.play_current()
                    dialog.accept()
        dialog, _ = self.table_dialog('Skipped tracks', ['Path', 'Reason'], [(r['path'], r['reason']) for r in rows], [('Retry', retry)])
        dialog.exec()

    def playlist_revisions_dialog(self):
        from music_catalog_manager.services import playlists, playlist_revisions
        from PySide6.QtWidgets import QInputDialog
        lists = playlists.lists(self.store)
        if not lists:
            return
        names = [r['name'] for r in lists]
        name, ok = QInputDialog.getItem(self, tr('Playlist revisions'), tr('Playlist'), names, editable=False)
        if not ok:
            return
        item = lists[names.index(name)]
        revisions = playlist_revisions.revisions(self.store, item['id'])
        def restore(index, dialog):
            if index >= 0 and self.preview('Restore playlist revision', tr('Current list will be retained as a new revision.') + '\n' + revisions[index]['created']):
                dialog.accept()
                self.start(lambda cancel, progress: playlist_revisions.restore(self.store, item['id'], revisions[index]))
        dialog, _ = self.table_dialog('Playlist revisions', ['Created', 'Name', 'Tracks'],
            [(r['created'], r['name'], len(r['ids'])) for r in revisions], [('Restore', restore)])
        dialog.exec()

    def smart_playlists_dialog(self):
        rows = smart_playlists.lists(self.store)
        def edit(index, dialog):
            if index >= 0:
                dialog.accept()
                self.edit_smart_playlist(rows[index])
        def create(index, dialog):
            dialog.accept()
            self.edit_smart_playlist()
        def play(index, dialog):
            if index >= 0:
                dialog.accept()
                self.request_playback_queue(options=dict(playlist=rows[index]['id']))
        def show(index, dialog):
            if index >= 0:
                self.clear_filters()
                self.group.setCurrentIndex(4)
                self.groups.setCurrentIndex(self.groups.findData(rows[index]['id']))
                dialog.accept()
        def remove(index, dialog):
            if index >= 0 and self.confirm(tr('Delete playlist?')):
                smart_playlists.remove(self.store, rows[index]['id'])
                dialog.accept()
                self.refresh()
        dialog, _ = self.table_dialog('Smart playlists', ['Name', 'Match', 'Rules'],
            [(r['name'], tr('All rules') if r['mode'] == 'all' else tr('Any rule'), len(r['rules'])) for r in rows],
            [('New', create), ('Edit', edit), ('Play', play), ('Show', show), ('Delete', remove)])
        dialog.exec()

    def edit_smart_playlist(self, definition=None):
        definition = definition or dict(name='', mode='all', rules=[])
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Smart playlist'))
        dialog.resize(760, 480)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        name = QLineEdit(definition['name'])
        mode = QComboBox()
        for label, key in [('All rules', 'all'), ('Any rule', 'any')]:
            mode.addItem(tr(label), key)
        mode.setCurrentIndex(max(0, mode.findData(definition['mode'])))
        form.addRow(tr('Name'), name)
        form.addRow(tr('Match'), mode)
        layout.addLayout(form)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels([tr('Field'), tr('Condition'), tr('Value')])
        layout.addWidget(table)
        def add(rule=None):
            if table.rowCount() >= 20:
                return
            rule = rule if isinstance(rule, dict) else dict(field='genre', operator='contains', value='')
            row = table.rowCount()
            table.insertRow(row)
            for column, choices, selected in [(0, smart_playlists.FIELDS, rule['field']), (1, smart_playlists.OPERATORS, rule['operator'])]:
                combo = QComboBox()
                for choice in choices:
                    combo.addItem(tr(choice), choice)
                combo.setCurrentIndex(max(0, combo.findData(selected)))
                table.setCellWidget(row, column, combo)
            table.setCellWidget(row, 2, QLineEdit(rule.get('value', '')))
        for rule in definition['rules'] or [dict(field='genre', operator='contains', value='')]:
            add(rule)
        controls = QHBoxLayout()
        self.button('Add rule', add, controls)
        self.button('Remove selected', lambda: table.removeRow(table.currentRow()), controls)
        layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.rejected.connect(dialog.reject)
        def save():
            rules = [dict(field=table.cellWidget(row, 0).currentData(), operator=table.cellWidget(row, 1).currentData(), value=table.cellWidget(row, 2).text()) for row in range(table.rowCount())]
            try:
                smart_playlists.save(self.store, name.text(), mode.currentData(), rules, definition.get('id'))
            except (ValueError, TypeError) as exc:
                self.error(str(exc))
                return
            dialog.accept()
            self.refresh()
        buttons.accepted.connect(save)
        layout.addWidget(buttons)
        dialog.exec()
