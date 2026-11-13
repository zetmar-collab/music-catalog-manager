from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout)

from music_catalog_manager.services import playlists
from music_catalog_manager.services.scanner import scan
from music_catalog_manager.ui.models import tr

PLAYLIST_FILTER = 'Playlists (*.m3u *.m3u8 *.pls *.wpl *.xspf)'


class PlaylistImportViews:
    def import_playlist_folder(self):
        if self.worker:
            return
        root = QFileDialog.getExistingDirectory(self, tr('Import playlists from folder'))
        if not root:
            return
        root = Path(root)
        self.start(lambda cancel, progress: playlists.discover(root, cancel, progress),
                   lambda result: self.choose_playlist_files(root, *result))

    def choose_playlist_files(self, root, paths, errors):
        if not paths:
            QMessageBox.information(self, tr('Import playlists from folder'),
                tr('No playlists found in this folder or its subfolders.') + ('\n' + '\n'.join(errors) if errors else ''))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Import playlists from folder'))
        dialog.resize(800, 550)
        layout = QVBoxLayout(dialog)
        label = QLabel(tr('Select playlists from the main folder and all subfolders. Reimport updates previously imported lists.'))
        label.setWordWrap(True)
        layout.addWidget(label)
        view = QListWidget()
        for path in paths:
            item = QListWidgetItem(str(path.relative_to(root)))
            item.setCheckState(Qt.Checked)
            view.addItem(item)
        layout.addWidget(view)
        catalog = QCheckBox(tr('Catalog audio in this folder and subfolders before importing'))
        catalog.setChecked(True)
        layout.addWidget(catalog)
        note = QLabel(tr('Audio outside this folder must already be in the catalog. Cancellation keeps completed imports.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        if errors:
            warning = QLabel(tr('Some folders could not be read.'))
            warning.setToolTip('\n'.join(errors))
            layout.addWidget(warning)
        buttons = QDialogButtonBox()
        accept = buttons.addButton(tr('Import'), QDialogButtonBox.AcceptRole)
        buttons.addButton(tr('Cancel'), QDialogButtonBox.RejectRole)
        view.itemChanged.connect(lambda *_: accept.setEnabled(any(view.item(i).checkState() == Qt.Checked for i in range(view.count()))))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = [path for i, path in enumerate(paths) if view.item(i).checkState() == Qt.Checked]
        if not selected:
            return
        do_scan = catalog.isChecked()
        hashes = self.store.setting('hashes', False)
        self.import_playlist_paths(selected, root, do_scan)

    def import_playlist_paths(self, selected, root=None, do_scan=False):
        from music_catalog_manager.services import playlist_revisions
        hashes = self.store.setting('hashes', False)
        def work(cancel, progress):
            if do_scan:
                rid = self.store.add_root(root)
                scan(self.store, rid, cancel, progress, hashes)
            plans, errors = [], []
            for path in selected:
                playlists.check_cancel(cancel)
                try:
                    plans.append(playlist_revisions.plan(self.store, path, root, cancel))
                except Exception as exc:
                    playlists.check_cancel(cancel)
                    errors.append(str(path) + ': ' + str(exc))
            return plans, errors
        def done(result):
            plans, errors = result
            def apply(index, dialog):
                dialog.accept()
                preserve_old = preserve.isChecked()
                def commit(cancel, progress):
                    results = []
                    for item in plans:
                        playlists.check_cancel(cancel)
                        results.append(playlist_revisions.apply(self.store, item, preserve_old, cancel))
                        progress(dict(imported=len(results), total=len(plans)))
                    return results
                self.start(commit, lambda rows: self.preview('Playlist import results', '\n'.join(r['name'] + ': ' + str(r['matched']) for r in rows)))
            dialog, table = self.table_dialog('Preview playlist changes', ['Playlist', 'Added', 'Removed', 'Unmatched paths:', 'Details'],
                [(p['name'], p['added'], p['removed'], len(p['missing']), '\n'.join(p['missing'])) for p in plans],
                [('Apply', lambda index, dialog: dialog.accept())] if plans else [])
            preserve = QCheckBox(tr('Keep old entries missing from the new playlist'))
            dialog.layout().insertWidget(0, preserve)
            if errors:
                label = QLabel('\n'.join(errors))
                label.setWordWrap(True)
                dialog.layout().insertWidget(0, label)
            if dialog.exec() == QDialog.Accepted and plans:
                apply(0, dialog)
        self.start(work, done)
