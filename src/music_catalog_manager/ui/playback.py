from pathlib import Path
import random
from copy import deepcopy
from itertools import chain

from PySide6.QtCore import QCoreApplication, Qt, QUrl, QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QAbstractItemView)


def tr(text):
    return QCoreApplication.translate('MainWindow', text)


def timestamp(milliseconds):
    seconds = max(0, int(milliseconds)) // 1000
    return f'{seconds // 60}:{seconds % 60:02}'


class PlaybackBar(QWidget):
    """Plays local paths from catalog records; never writes to audio files."""

    def __init__(self, store, selected, visible, parent=None, context=None):
        super().__init__(parent)
        self.store, self.selected, self.visible = store, selected, visible
        self.context = context
        self.queue_context = None
        self.request_queue = None
        self.failed_entries = set()
        self.skipped = []
        self.pending_position = 0
        self.gain = 1.0
        self.player = self.output = None
        self.queue = []
        self.current = -1
        self.busy = False
        self.last_error = ''
        self.retiring = 0
        self.release_callbacks = []
        self.playback_generation = 0
        self.end_player = None
        self.end_generation = None
        self.end_timer = QTimer(self)
        self.end_timer.setSingleShot(True)
        self.end_timer.timeout.connect(self.finish_track)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        self.now_playing = QLabel(tr('No track playing'))
        self.now_playing.setTextFormat(Qt.PlainText)
        self.now_playing.setWordWrap(True)
        heading = QHBoxLayout()
        heading.addWidget(self.now_playing, 1)
        self.shuffle = QCheckBox(tr('Shuffle'))
        self.shuffle.setChecked(bool(store.setting('shuffle', False)))
        self.shuffle.toggled.connect(self.shuffle_changed)
        heading.addWidget(self.shuffle)
        self.repeat = QComboBox()
        for label, key in [('No repeat', 'off'), ('Repeat track', 'one'), ('Repeat queue', 'all')]:
            self.repeat.addItem(tr(label), key)
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(store.setting('repeat', 'off'))))
        self.repeat.currentIndexChanged.connect(self.repeat_changed)
        heading.addWidget(self.repeat)
        self.queue_button = self.button('Queue', self.queue_dialog, heading)
        layout.addLayout(heading)
        controls = QHBoxLayout()
        layout.addLayout(controls)
        self.previous_button = self.button('Previous', self.previous, controls)
        self.play_button = self.button('Play', self.toggle, controls)
        self.stop_button = self.button('Stop', self.stop, controls)
        self.next_button = self.button('Next', self.next, controls)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setAccessibleName(tr('Playback position'))
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.seek_to)
        controls.addWidget(self.seek, 1)
        self.clock = QLabel('0:00 / 0:00')
        controls.addWidget(self.clock)
        controls.addWidget(QLabel(tr('Volume')))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setAccessibleName(tr('Volume'))
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(100)
        self.volume.setValue(max(0, min(100, int(store.setting('volume', 60)))))
        self.volume.valueChanged.connect(self.set_volume)
        self.volume_timer = QTimer(self)
        self.volume_timer.setSingleShot(True)
        self.volume_timer.setInterval(250)
        self.volume_timer.timeout.connect(lambda: store.set_setting('volume', self.volume.value()))
        controls.addWidget(self.volume)
        self.update_controls()

    def button(self, text, handler, layout):
        button = QPushButton(tr(text))
        button.setAccessibleName(tr(text))
        button.clicked.connect(handler)
        layout.addWidget(button)
        return button

    def ensure_player(self):
        if self.player is None:
            try:
                from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
                player = QMediaPlayer(self)
                if not player.isAvailable():
                    player.deleteLater()
                    raise RuntimeError('Qt Multimedia backend unavailable')
                output = QAudioOutput(player)
                output.setVolume(self.volume.value() / 100)
                player.setAudioOutput(output)
                player.playbackStateChanged.connect(self.update_controls)
                player.positionChanged.connect(self.position_changed)
                player.durationChanged.connect(self.duration_changed)
                player.seekableChanged.connect(self.update_controls)
                player.mediaStatusChanged.connect(self.media_status)
                player.errorOccurred.connect(self.media_error)
                self.player, self.output = player, output
            except (ImportError, RuntimeError) as exc:
                self.show_error('Audio playback is unavailable.', str(exc))
                return False
        return True

    def play_track(self, track):
        if self.busy:
            return
        selected = self.selected()
        if self.request_queue:
            self.request_queue(selected if len(selected) > 1 else None, track['id'])
            return
        # Multiple selected tracks form a queue; one track starts the visible list.
        self.queue = selected if len(selected) > 1 else self.visible()
        self.queue_context = deepcopy(self.context()) if self.context else None
        self.current = next((i for i, item in enumerate(self.queue) if item['id'] == track['id']), -1)
        if self.current < 0:
            self.queue, self.current = [track], 0
        if self.shuffle.isChecked():
            chosen = self.queue.pop(self.current)
            random.shuffle(self.queue)
            self.queue.insert(0, chosen)
            self.current = 0
        self.play_current()

    def set_queue(self, tracks, start_id=None):
        if self.busy or not tracks:
            return
        self.queue = list(tracks)
        self.failed_entries.clear()
        self.pending_position = 0
        self.queue_context = deepcopy(self.context()) if self.context else None
        self.current = next((i for i, item in enumerate(self.queue) if item['id'] == start_id), 0)
        if self.shuffle.isChecked():
            if start_id is not None:
                chosen = self.queue.pop(self.current)
                random.shuffle(self.queue)
                self.queue.insert(0, chosen)
            else:
                random.shuffle(self.queue)
            self.current = 0
        self.play_current()

    def enqueue(self, tracks, next_up=False):
        if self.busy or not tracks:
            return
        at = self.current + 1 if next_up and self.current >= 0 else len(self.queue)
        self.queue[at:at] = list(tracks)
        if self.current < 0:
            self.current = 0
        self.failed_entries.clear()
        self.update_controls()

    def save_session(self):
        from music_catalog_manager.services import session
        session.save(self.store, self.queue, self.current,
                     self.player.position() if self.player else self.pending_position, self.queue_context)

    def restore_session(self, result):
        self.queue, self.current, self.pending_position, self.queue_context = result
        self.failed_entries.clear()
        if self.queue:
            self.now_playing.setText(tr('Session restored. Press Play to continue.'))
            if self.store.setting('autoplay_session', False):
                self.play_current()
        self.update_controls()

    def skip_failed(self, reason):
        if not self.store.setting('skip_unavailable', False):
            return False
        index = self.current
        self.failed_entries.add(index)
        self.skipped.append(dict(path=self.queue[index]['path'], reason=reason))
        self.skipped = self.skipped[-200:]
        self.store.log('playback_skip', self.queue[index]['id'], after=reason)
        following = chain(range(index + 1, len(self.queue)), range(index) if self.repeat.currentData() == 'all' else ())
        target = next((i for i in following if i not in self.failed_entries), None)
        self.show_error('Skipped unavailable track.', reason)
        if target is None:
            if self.player:
                self.player.stop()
        else:
            generation = self.playback_generation
            def advance():
                if generation == self.playback_generation and not self.busy:
                    self.current = target
                    self.play_current()
            QTimer.singleShot(0, advance)
        return True

    def shuffle_changed(self, enabled):
        self.store.set_setting('shuffle', enabled)
        if enabled and self.queue and self.current >= 0:
            tail = self.queue[self.current + 1:]
            random.shuffle(tail)
            self.queue[self.current + 1:] = tail

    def repeat_changed(self, *_):
        self.store.set_setting('repeat', self.repeat.currentData())
        self.update_controls()

    def queue_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Queue'))
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(tr('Drag tracks to reorder. Select and remove unwanted entries.')))
        view = QListWidget()
        view.setDragDropMode(QAbstractItemView.InternalMove)
        original = list(self.queue)
        current = self.current
        for index, track in enumerate(original):
            item = QListWidgetItem(('▶ ' if index == current else '') + (track['tags'].get('title') or Path(track['path']).name) + ' — ' + track['tags'].get('artist', ''))
            item.setData(Qt.UserRole, index)
            view.addItem(item)
        layout.addWidget(view)
        self.button('Remove selected', lambda: view.takeItem(view.currentRow()) if view.currentRow() >= 0 else None, layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted and not self.busy:
            # Playback can advance while this dialog is open: resolve its current item now.
            current_track = self.queue[self.current] if 0 <= self.current < len(self.queue) else None
            indices = [view.item(i).data(Qt.UserRole) for i in range(view.count())]
            self.queue = [original[i] for i in indices]
            self.failed_entries.clear()
            self.current = next((i for i, track in enumerate(self.queue) if track is current_track), -1)
            if self.current < 0:
                remaining = self.queue
                self.release()
                self.queue = remaining
                self.current = 0 if remaining else -1
            self.update_controls()

    def play_current(self):
        self.cancel_advance()
        if self.busy or not 0 <= self.current < len(self.queue):
            return
        record = self.queue[self.current]
        # Resolve fresh paths after rescans and database edits.
        try:
            record = self.store.track(record['id'])
        except KeyError:
            if self.skip_failed('Track removed from catalog'):
                return
            self.show_error('This track is no longer in the library.')
            return
        path = Path(record['path'])
        if not path.is_file():
            if self.skip_failed(str(path)):
                return
            self.release()
            self.show_error('The audio file is unavailable.', str(path))
            return
        if not self.ensure_player():
            return
        self.last_error = ''
        from music_catalog_manager.services.replaygain import multiplier
        self.gain = multiplier(record['tags'], self.store.setting('replaygain', 'off'))
        self.set_volume(self.volume.value())
        title = record['tags'].get('title') or path.name
        artist = record['tags'].get('artist')
        self.now_playing.setText((artist + ' — ' if artist else '') + title)
        self.now_playing.setToolTip(str(path))
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()
        self.update_controls()

    def toggle(self):
        if self.busy:
            return
        chosen = self.selected()
        if self.context and self.context() != self.queue_context:
            if self.request_queue:
                self.request_queue(chosen if len(chosen) > 1 else None, chosen[0]['id'] if chosen else None)
                return
            tracks = self.visible()
            ids = {track['id'] for track in tracks}
            chosen = [track for track in chosen if track['id'] in ids]
            if tracks:
                self.set_queue(chosen if len(chosen) > 1 else tracks, chosen[0]['id'] if chosen else None)
            else:
                self.release()
            return
        if self.player and not self.player.source().isEmpty():
            if self.player.playbackState() == self.player.PlaybackState.PlayingState:
                self.cancel_advance()
                self.player.pause()
            else:
                self.player.play()
        elif self.queue and self.current >= 0:
            self.play_current()
        elif chosen:
            self.play_track(chosen[0])
        self.update_controls()

    def stop(self):
        self.cancel_advance()
        if self.player:
            self.player.stop()
        self.position_changed(0)
        self.update_controls()

    def release(self):
        self.cancel_advance()
        if self.volume_timer.isActive():
            self.volume_timer.stop()
            self.store.set_setting('volume', self.volume.value())
        if self.player:
            # Retire on the Qt event loop; deleting a multimedia backend inside
            # its own signal dispatch can crash. File mutations wait for it.
            player = self.player
            self.player = self.output = None
            player.blockSignals(True)
            player.stop()
            self.retiring += 1
            player.destroyed.connect(self.player_retired)
            player.deleteLater()
        self.queue, self.current = [], -1
        self.seek.setRange(0, 0)
        self.clock.setText('0:00 / 0:00')
        self.now_playing.setText(tr('No track playing'))
        self.update_controls()

    def player_retired(self, *_):
        self.retiring -= 1
        if not self.retiring:
            callbacks, self.release_callbacks = self.release_callbacks, []
            for callback in callbacks:
                QTimer.singleShot(0, callback)

    def when_released(self, callback):
        if self.retiring:
            self.release_callbacks.append(callback)
        else:
            QTimer.singleShot(0, callback)

    def set_busy(self, busy):
        self.busy = busy
        if busy:
            self.release()
        self.update_controls()

    def previous(self):
        self.cancel_advance()
        if not self.busy and self.current > 0:
            self.current -= 1
            self.play_current()

    def next(self):
        self.cancel_advance()
        if not self.busy and self.current + 1 < len(self.queue):
            self.current += 1
            self.play_current()
        elif not self.busy and self.queue and self.repeat.currentData() == 'all':
            self.current = 0
            self.play_current()

    def media_status(self, status):
        if self.player and self.pending_position and status in (self.player.MediaStatus.LoadedMedia, self.player.MediaStatus.BufferedMedia):
            position, self.pending_position = self.pending_position, 0
            self.player.setPosition(position)
        if self.player and status == self.player.MediaStatus.EndOfMedia and not self.end_timer.isActive():
            # Finish the backend's EndOfMedia dispatch before changing its source.
            self.end_player = self.player
            self.end_generation = self.playback_generation
            self.end_timer.start(0)
        self.update_controls()

    def cancel_advance(self):
        self.end_timer.stop()
        self.playback_generation += 1
        self.end_player = None

    def finish_track(self):
        if (self.busy or self.player is None or self.player is not self.end_player
                or self.end_generation != self.playback_generation
                or self.player.mediaStatus() != self.player.MediaStatus.EndOfMedia):
            return
        self.cancel_advance()
        if self.repeat.currentData() == 'one':
            self.player.setPosition(0)
            self.player.play()
        else:
            self.next()

    def media_error(self, error, detail):
        if self.player and error != self.player.Error.NoError:
            self.cancel_advance()
            if self.queue and self.skip_failed(detail):
                return
            self.show_error('Cannot play this file. Check its availability and format.', detail)

    def show_error(self, message, detail=''):
        self.last_error = tr(message)
        self.now_playing.setText(self.last_error)
        self.now_playing.setToolTip(detail)
        self.update_controls()

    def set_volume(self, value):
        if self.output:
            self.output.setVolume(min(1.0, max(0.0, value / 100 * self.gain)))
        self.volume_timer.start()

    def seek_to(self, position):
        if self.player and self.player.isSeekable():
            self.player.setPosition(position)

    def position_changed(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(min(position, self.seek.maximum()))
        duration = self.player.duration() if self.player else 0
        self.clock.setText(timestamp(position) + ' / ' + timestamp(duration))

    def duration_changed(self, duration):
        self.seek.setRange(0, min(duration, 2_147_483_647))
        self.position_changed(self.player.position())

    def update_controls(self, *_):
        loaded = self.player is not None and not self.player.source().isEmpty()
        same_context = self.context is None or self.context() == self.queue_context
        playing = loaded and same_context and self.player.playbackState() == self.player.PlaybackState.PlayingState
        self.play_button.setText(tr('Pause') if playing else tr('Play'))
        self.play_button.setAccessibleName(self.play_button.text())
        self.play_button.setEnabled(not self.busy)
        self.stop_button.setEnabled(loaded and not self.busy)
        self.previous_button.setEnabled(not self.busy and self.current > 0)
        self.next_button.setEnabled(not self.busy and bool(self.queue) and (self.current + 1 < len(self.queue) or self.repeat.currentData() == 'all'))
        self.queue_button.setEnabled(not self.busy)
        self.seek.setEnabled(loaded and self.player.isSeekable() and not self.busy)
