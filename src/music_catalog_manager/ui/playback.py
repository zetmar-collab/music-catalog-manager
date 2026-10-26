from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QUrl, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget


def tr(text):
    return QCoreApplication.translate('MainWindow', text)


def timestamp(milliseconds):
    seconds = max(0, int(milliseconds)) // 1000
    return f'{seconds // 60}:{seconds % 60:02}'


class PlaybackBar(QWidget):
    """Plays local paths from catalog records; never writes to audio files."""

    def __init__(self, store, selected, visible, parent=None):
        super().__init__(parent)
        self.store, self.selected, self.visible = store, selected, visible
        self.player = self.output = None
        self.queue = []
        self.current = -1
        self.busy = False
        self.last_error = ''
        self.retiring = 0
        self.release_callbacks = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        self.now_playing = QLabel(tr('No track playing'))
        self.now_playing.setTextFormat(Qt.PlainText)
        self.now_playing.setWordWrap(True)
        layout.addWidget(self.now_playing)
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
        # Multiple selected tracks form a queue; one track starts the visible list.
        self.queue = selected if len(selected) > 1 else self.visible()
        self.current = next((i for i, item in enumerate(self.queue) if item['id'] == track['id']), -1)
        if self.current < 0:
            self.queue, self.current = [track], 0
        self.play_current()

    def play_current(self):
        if self.busy or not 0 <= self.current < len(self.queue):
            return
        record = self.queue[self.current]
        # Resolve fresh paths after rescans and database edits.
        try:
            record = self.store.track(record['id'])
        except KeyError:
            self.show_error('This track is no longer in the library.')
            return
        path = Path(record['path'])
        if not path.is_file():
            self.release()
            self.show_error('The audio file is unavailable.', str(path))
            return
        if not self.ensure_player():
            return
        self.last_error = ''
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
        if self.player and not self.player.source().isEmpty():
            if self.player.playbackState() == self.player.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()
        elif chosen:
            self.play_track(chosen[0])
        self.update_controls()

    def stop(self):
        if self.player:
            self.player.stop()
        self.position_changed(0)
        self.update_controls()

    def release(self):
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
        if not self.busy and self.current > 0:
            self.current -= 1
            self.play_current()

    def next(self):
        if not self.busy and self.current + 1 < len(self.queue):
            self.current += 1
            self.play_current()

    def media_status(self, status):
        if status == self.player.MediaStatus.EndOfMedia:
            self.next()
        self.update_controls()

    def media_error(self, error, detail):
        if self.player and error != self.player.Error.NoError:
            self.show_error('Cannot play this file. Check its availability and format.', detail)

    def show_error(self, message, detail=''):
        self.last_error = tr(message)
        self.now_playing.setText(self.last_error)
        self.now_playing.setToolTip(detail)
        self.update_controls()

    def set_volume(self, value):
        if self.output:
            self.output.setVolume(value / 100)
        self.store.set_setting('volume', value)

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
        playing = loaded and self.player.playbackState() == self.player.PlaybackState.PlayingState
        self.play_button.setText(tr('Pause') if playing else tr('Play'))
        self.play_button.setAccessibleName(self.play_button.text())
        self.play_button.setEnabled(not self.busy)
        self.stop_button.setEnabled(loaded and not self.busy)
        self.previous_button.setEnabled(not self.busy and self.current > 0)
        self.next_button.setEnabled(not self.busy and self.current + 1 < len(self.queue))
        self.seek.setEnabled(loaded and self.player.isSeekable() and not self.busy)
