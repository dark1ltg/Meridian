from __future__ import annotations

from PySide6.QtCore import QStringListModel, QTimer, Qt, Signal
from PySide6.QtWidgets import QCompleter, QLineEdit

from meridian.library import Library, Track


class TrackSearch(QLineEdit):
    track_chosen = Signal(int)

    def __init__(self, library: Library, parent=None) -> None:
        super().__init__(parent)
        self.library = library
        self.setObjectName("trackSearch")
        self.setPlaceholderText("Search title, artist, album")
        self.setClearButtonEnabled(True)
        self._hits: list[Track] = []
        # Completer labels are unique even when artist/title collide.
        self._label_to_id: dict[str, int] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._refresh)
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self._completer.setMaxVisibleItems(12)
        self.setCompleter(self._completer)
        popup = self._completer.popup()
        popup.setObjectName("searchPopup")
        popup.setStyleSheet(
            "background: #121a2e; color: #d7deee; border: 1px solid #2a3a58; "
            "selection-background-color: #243049; outline: none;"
        )
        self.textChanged.connect(self._schedule)
        self._completer.activated.connect(self._activated)
        self.returnPressed.connect(self._accept_first)

    def _schedule(self, _text: str) -> None:
        self._timer.start()

    @staticmethod
    def _unique_label(track: Track, used: set[str]) -> str:
        base = track.label
        if base not in used:
            used.add(base)
            return base
        # Disambiguate duplicates with album or path stem.
        alt = f"{base}  ·  {track.album}" if track.album else base
        if alt not in used:
            used.add(alt)
            return alt
        n = 2
        while True:
            label = f"{base}  ({n})"
            if label not in used:
                used.add(label)
                return label
            n += 1

    def _refresh(self) -> None:
        self._hits = self.library.search(self.text())
        used: set[str] = set()
        labels: list[str] = []
        self._label_to_id = {}
        for track in self._hits:
            label = self._unique_label(track, used)
            labels.append(label)
            self._label_to_id[label] = track.id
        self._model.setStringList(labels)
        if self._hits and self.hasFocus() and self.text().strip():
            self._completer.complete()

    def _activated(self, label: str) -> None:
        tid = self._label_to_id.get(label)
        if tid is None:
            for track in self._hits:
                if track.label == label:
                    tid = track.id
                    break
        if tid is not None:
            self.track_chosen.emit(tid)
            self.clear()

    def _accept_first(self) -> None:
        if not self._hits:
            self._refresh()
        if self._hits:
            self.track_chosen.emit(self._hits[0].id)
            self.clear()
