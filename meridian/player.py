from __future__ import annotations

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from meridian.library import Track


class Player(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(bool)
    track_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.output = QAudioOutput(self)
        self.output.setVolume(0.85)
        self.backend = QMediaPlayer(self)
        self.backend.setAudioOutput(self.output)
        self.backend.positionChanged.connect(self._on_position)
        self.backend.durationChanged.connect(self._on_duration)
        self.backend.playbackStateChanged.connect(self._on_state)
        self.backend.mediaStatusChanged.connect(self._on_status)
        self.backend.errorOccurred.connect(self._on_error)
        self.current: Track | None = None

    def _on_position(self, value: int) -> None:
        self.position_changed.emit(int(value))

    def _on_duration(self, value: int) -> None:
        self.duration_changed.emit(int(value))

    def _on_state(self, state: QMediaPlayer.PlaybackState) -> None:
        self.state_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.track_finished.emit()

    def _on_error(self, *_args) -> None:
        self.error_occurred.emit(self.backend.errorString() or "Playback failed")

    def load(self, track: Track) -> None:
        self.current = track
        self.backend.setSource(QUrl.fromLocalFile(track.path))

    def play_track(self, track: Track) -> None:
        self.load(track)
        self.backend.play()

    @Slot()
    def toggle(self) -> None:
        if self.backend.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.backend.pause()
        else:
            self.backend.play()

    @Slot()
    def stop(self) -> None:
        self.backend.stop()

    def seek(self, ms: int) -> None:
        duration = int(self.backend.duration() or 0)
        position = max(0, int(ms))
        if duration > 0:
            position = min(position, duration)
        self.backend.setPosition(position)

    def set_volume(self, value: float) -> None:
        self.output.setVolume(max(0.0, min(1.0, value)))

    def is_playing(self) -> bool:
        return self.backend.playbackState() == QMediaPlayer.PlaybackState.PlayingState
