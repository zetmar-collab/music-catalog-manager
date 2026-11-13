from PySide6.QtWidgets import QMessageBox

from music_catalog_manager.services import library_cleanup
from music_catalog_manager.ui.models import tr


class CleanupViews:
    def remove_folder_dialog(self, root_id):
        return self.cleanup_dialog(root_id)

    def clear_library_dialog(self):
        return self.cleanup_dialog()

    def cleanup_dialog(self, root_id=None):
        if self.worker:
            return False
        counts = library_cleanup.summary(self.store, root_id)
        title = 'Clear entire library' if root_id is None else 'Remove folder from catalog'
        lines = [tr('Remove all catalog data?') if root_id is None else counts['path']]
        for key, label in [('folders', 'Folders'), ('tracks', 'Tracks'), ('pending', 'Pending tag changes'),
                           ('playlists', 'Playlists'), ('playlist_entries', 'Playlist entries'),
                           ('history', 'History'), ('audio_backup_records', 'Audio backup records')]:
            if key != 'playlists' or root_id is None:
                lines.append(tr(label) + ': ' + str(counts[key]))
        lines += ['', tr('Audio files, folder.jpg and original backup files stay on disk.'),
                  tr('An automatic catalog backup is required before removal.'),
                  tr('Restore the safety backup to undo this operation.')]
        if root_id is None:
            lines.append(tr('Language, theme and other application preferences are preserved.'))
        else:
            lines.append(tr('Other registered folders and playlist definitions are preserved.'))
        if not self.preview(title, '\n'.join(lines)):
            return False
        self.query_generation += 1
        for worker in self.query_workers:
            worker.cancel.set()
        self.table.clearSelection()
        def done(result):
            self.clear_filters()
            QMessageBox.information(self, tr(title), tr('Catalog data removed. Safety backup:') + '\n' + result['backup'])
        self.start(lambda cancel, progress: library_cleanup.remove(self.store, root_id, cancel, progress), done, lock_playback=True)
        return True
