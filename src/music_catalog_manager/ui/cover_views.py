from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from music_catalog_manager.services import covers
from music_catalog_manager.services.artwork import MAX_BYTES, validate_image
from music_catalog_manager.ui.models import tr

PROJECT_CONTACT = 'https://github.com/zetmar-collab/music-catalog-manager'


class CoverViews:
    def choose_local_cover(self, tracks=None):
        if self.worker:
            return
        tracks = tracks or self.selected()
        if not tracks:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('Choose local image'), '', 'Images (*.jpg *.jpeg *.png)')
        if not path:
            return
        path = Path(path)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError(tr('Image exceeds 20 MB'))
        data = validate_image(path.read_bytes())
        self.apply_artwork(tracks, data)

    def search_cover_dialog(self, tracks=None):
        if self.worker:
            return
        tracks = tracks or self.selected()
        if not tracks:
            return
        tags = tracks[0]['tags']
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Find cover online'))
        layout = QVBoxLayout(dialog)
        info = QLabel(tr('Search by album and album artist. Results are suggestions; preview before saving.'))
        info.setWordWrap(True)
        layout.addWidget(info)
        form = QFormLayout()
        artist = QLineEdit(tags.get('albumartist') or tags.get('artist', ''))
        album = QLineEdit(tags.get('album', ''))
        form.addRow(tr('Album artist'), artist)
        form.addRow(tr('Album'), album)
        layout.addLayout(form)
        layout.addWidget(QLabel('MusicBrainz · Cover Art Archive'))
        buttons = QDialogButtonBox()
        search = buttons.addButton(tr('Search online'), QDialogButtonBox.AcceptRole)
        buttons.addButton(tr('Cancel'), QDialogButtonBox.RejectRole)
        def changed():
            search.setEnabled(bool(artist.text().strip() and album.text().strip()))
        artist.textChanged.connect(changed)
        album.textChanged.connect(changed)
        changed()
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        artist_value, album_value = artist.text().strip(), album.text().strip()
        contact = self.store.setting('contact', '') or PROJECT_CONTACT
        self.internet(lambda client, progress: covers.search(client, artist_value, album_value, progress),
                      lambda result: self.cover_results(tracks, result), contact=contact, with_progress=True)

    def cover_results(self, tracks, result):
        candidates = result['covers']
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Choose cover'))
        dialog.resize(960, 590)
        layout = QVBoxLayout(dialog)
        message = QLabel(tr('Select a cover and preview its destination before saving.') if candidates else
            tr('Could not retrieve covers. Check the connection or choose an image from disk.') if result['errors'] else
            tr('No covers found. Try another spelling or choose an image from disk.'))
        message.setWordWrap(True)
        layout.addWidget(message)
        view = QListWidget()
        view.setViewMode(QListWidget.IconMode)
        view.setResizeMode(QListWidget.Adjust)
        view.setIconSize(QSize(170, 170))
        view.setGridSize(QSize(220, 260))
        view.setWordWrap(True)
        for candidate in candidates:
            pix = QPixmap()
            pix.loadFromData(candidate['data'])
            item = QListWidgetItem(QIcon(pix), '\n'.join(filter(None, (candidate['album'], candidate['artist'], candidate['date'] + ' ' + candidate['country'], candidate['source']))))
            item.setToolTip(candidate['url'])
            view.addItem(item)
        layout.addWidget(view)
        if result['errors']:
            error = QLabel(tr('Some sources could not be reached.'))
            error.setToolTip('\n'.join(result['errors']))
            layout.addWidget(error)
        buttons = QDialogButtonBox()
        use = buttons.addButton(tr('Preview'), QDialogButtonBox.AcceptRole)
        use.setEnabled(False)
        local = buttons.addButton(tr('Choose local image'), QDialogButtonBox.ActionRole)
        retry = buttons.addButton(tr('Search again'), QDialogButtonBox.ActionRole)
        buttons.addButton(tr('Cancel'), QDialogButtonBox.RejectRole)
        choice = {'action': None}
        local.clicked.connect(lambda: (choice.update(action='local'), dialog.accept()))
        retry.clicked.connect(lambda: (choice.update(action='retry'), dialog.accept()))
        view.currentRowChanged.connect(lambda row: use.setEnabled(row >= 0))
        view.itemDoubleClicked.connect(lambda *_: dialog.accept())
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if candidates:
            view.setCurrentRow(0)
        if dialog.exec() != QDialog.Accepted:
            return
        if choice['action'] == 'local':
            self.choose_local_cover(tracks)
        elif choice['action'] == 'retry':
            self.search_cover_dialog(tracks)
        elif view.currentRow() >= 0:
            candidate = candidates[view.currentRow()]
            self.apply_artwork(tracks, candidate['data'], candidate['release_id'])
