from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QObject, QUrl, QVariantAnimation, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from meridian.library import Track

# Always-on overlap between outgoing and incoming tracks (skips, queue, jumps).
CROSSFADE_MS = 3000


@dataclass
class _Deck:
    player: QMediaPlayer
    output: QAudioOutput


class Player(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(bool)
    track_finished = Signal()
    track_nearly_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._master = 0.85
        self._active = 0
        self._decks = (self._make_deck(), self._make_deck())
        self._wire_deck(0)
        self._wire_deck(1)
        self.current: Track | None = None
        self._crossfading = False
        self._advance_emitted = False
        self._outgoing: _Deck | None = None
        self._xfade = QVariantAnimation(self)
        self._xfade.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._xfade.valueChanged.connect(self._on_xfade_progress)
        self._xfade.finished.connect(self._on_xfade_finished)

    def _make_deck(self) -> _Deck:
        output = QAudioOutput(self)
        output.setVolume(self._master)
        player = QMediaPlayer(self)
        player.setAudioOutput(output)
        return _Deck(player=player, output=output)

    def _wire_deck(self, index: int) -> None:
        deck = self._decks[index]
        deck.player.positionChanged.connect(lambda v, i=index: self._on_position(i, v))
        deck.player.durationChanged.connect(lambda v, i=index: self._on_duration(i, v))
        deck.player.playbackStateChanged.connect(lambda s, i=index: self._on_state(i, s))
        deck.player.mediaStatusChanged.connect(lambda s, i=index: self._on_status(i, s))
        deck.player.errorOccurred.connect(lambda *_a, i=index: self._on_error(i))

    @property
    def backend(self) -> QMediaPlayer:
        return self._decks[self._active].player

    @property
    def output(self) -> QAudioOutput:
        return self._decks[self._active].output

    def _on_position(self, index: int, value: int) -> None:
        if index != self._active:
            return
        self.position_changed.emit(int(value))
        if self._crossfading or self._advance_emitted:
            return
        duration = int(self.backend.duration() or 0)
        if duration < 2500:
            return
        fade = self._fade_ms(duration)
        remaining = duration - int(value)
        if 0 <= remaining <= fade:
            self._advance_emitted = True
            self.track_nearly_finished.emit()

    def _on_duration(self, index: int, value: int) -> None:
        if index == self._active:
            self.duration_changed.emit(int(value))

    def _on_state(self, index: int, state: QMediaPlayer.PlaybackState) -> None:
        if index == self._active:
            self.state_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_status(self, index: int, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._crossfading:
            return
        if index != self._active:
            return
        if self._advance_emitted:
            return
        self.track_finished.emit()

    def _on_error(self, index: int) -> None:
        if index != self._active and not self._crossfading:
            return
        err = self._decks[index].player.errorString() or "Playback failed"
        self.error_occurred.emit(err)

    @staticmethod
    def _fade_ms(duration_ms: int) -> int:
        if duration_ms <= 0:
            return CROSSFADE_MS
        return max(400, min(CROSSFADE_MS, duration_ms // 3))

    def play_track(self, track: Track) -> None:
        """Play track with always-on crossfade (queue, skips, matrix pulls, double-clicks)."""
        if self._crossfading:
            self._finish_crossfade(immediate=True)

        same = self.current is not None and self.current.id == track.id
        can_fade = (
            not same
            and self.current is not None
            and self.backend.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self.current = track
        self._advance_emitted = False
        if can_fade:
            self._start_crossfade(track)
        else:
            self._hard_cut(track)

    def _hard_cut(self, track: Track) -> None:
        other = self._decks[1 - self._active]
        other.player.stop()
        other.output.setVolume(0.0)
        active = self._decks[self._active]
        active.output.setVolume(self._master)
        active.player.setSource(QUrl.fromLocalFile(track.path))
        active.player.play()

    def _start_crossfade(self, track: Track) -> None:
        incoming_index = 1 - self._active
        outgoing = self._decks[self._active]
        incoming = self._decks[incoming_index]
        self._outgoing = outgoing
        self._active = incoming_index
        self._crossfading = True

        duration = int(outgoing.player.duration() or 0)
        fade = self._fade_ms(duration) if duration > 0 else CROSSFADE_MS

        incoming.output.setVolume(0.0)
        incoming.player.setSource(QUrl.fromLocalFile(track.path))
        incoming.player.play()

        self._xfade.stop()
        self._xfade.setDuration(fade)
        self._xfade.setStartValue(0.0)
        self._xfade.setEndValue(1.0)
        self._xfade.start()

    def _on_xfade_progress(self, value: object) -> None:
        if not self._crossfading or self._outgoing is None:
            return
        t = float(value)
        self._outgoing.output.setVolume(self._master * (1.0 - t))
        self._decks[self._active].output.setVolume(self._master * t)

    def _on_xfade_finished(self) -> None:
        self._finish_crossfade(immediate=False)

    def _finish_crossfade(self, *, immediate: bool) -> None:
        if immediate:
            self._xfade.stop()
        outgoing = self._outgoing
        self._outgoing = None
        self._crossfading = False
        if outgoing is not None:
            outgoing.player.stop()
            outgoing.output.setVolume(0.0)
        self._decks[self._active].output.setVolume(self._master)
        self.position_changed.emit(int(self.backend.position() or 0))
        self.duration_changed.emit(int(self.backend.duration() or 0))
        self.state_changed.emit(self.is_playing())

    @Slot()
    def toggle(self) -> None:
        if self._crossfading:
            self._finish_crossfade(immediate=True)
        if self.backend.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.backend.pause()
        else:
            self.backend.play()

    @Slot()
    def stop(self) -> None:
        if self._crossfading:
            self._finish_crossfade(immediate=True)
        for deck in self._decks:
            deck.player.stop()
            deck.output.setVolume(0.0)
        self._decks[self._active].output.setVolume(self._master)

    def seek(self, ms: int) -> None:
        if self._crossfading:
            self._finish_crossfade(immediate=True)
        duration = int(self.backend.duration() or 0)
        position = max(0, int(ms))
        if duration > 0:
            position = min(position, duration)
        self.backend.setPosition(position)
        self._advance_emitted = False

    def set_volume(self, value: float) -> None:
        self._master = max(0.0, min(1.0, value))
        if self._crossfading and self._outgoing is not None:
            t = float(self._xfade.currentValue() or 0.0)
            self._outgoing.output.setVolume(self._master * (1.0 - t))
            self._decks[self._active].output.setVolume(self._master * t)
        else:
            self.output.setVolume(self._master)

    def is_playing(self) -> bool:
        return self.backend.playbackState() == QMediaPlayer.PlaybackState.PlayingState
