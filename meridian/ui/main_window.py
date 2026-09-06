from __future__ import annotations

from pathlib import Path
from time import time

from PySide6.QtCore import QSettings, Qt, QTimer, Slot
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from meridian import __version__
from meridian.features import CONFIDENCE_HIGH, CONFIDENCE_LOW
from meridian.context import (
    LENS_RADIUS_DEFAULT,
    MODE_HINTS,
    MODE_LABELS,
    Mode,
    make_context,
    mode_bias,
)
from meridian.library import Library
from meridian.player import Player
from meridian.queue_engine import Quadrant, QueuePlan, build_plan
from meridian.scanner import AnalyzeWorker, ScanWorker, start_worker
from meridian.ui.search import TrackSearch
from meridian.ui.fit_list import FitList
from meridian.ui.fonts import condensed
from meridian.ui.palette import PLAYLIST_HEX
from meridian.ui.matrix import EisenhowerMatrix
from meridian.ui.mood_map import MoodMap
from meridian.ui.transport import TransportBar


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Meridian {__version__}")
        self.resize(1440, 900)
        self.settings = QSettings()
        self.library = Library()
        self.player = Player(self)
        self.mode = Mode(self.settings.value("mode", Mode.WANDER.value))
        self.explicit: list[int] = []
        self.plan: QueuePlan | None = None
        self.session_queue: list[int] = []
        self.ephemeral: set[int] = set()
        self.played_history: list[int] = []
        self.queue_index = 0
        self.skips_window: list[float] = []
        self._scan_thread = None
        self._scan_worker = None
        self._analyze_thread = None
        self._analyze_worker = None
        self._analyze_gen = 0
        self._closing = False
        self._pending_finish_nudge: int | None = None
        self._duration = 0
        self._rebuild_lock = False
        self._lens_timer = QTimer(self)
        self._lens_timer.setSingleShot(True)
        self._lens_timer.setInterval(180)
        self._lens_timer.timeout.connect(self.refresh_plan)

        self._build()
        self._bind()
        self._restore_lens()
        if not self.library.folders():
            music = Path.home() / "Music"
            if music.is_dir():
                self.library.add_folder(str(music))
        self.refresh_plan()
        QTimer.singleShot(400, self.start_scan)

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 24, 14, 8)
        layout.setSpacing(20)

        header = QHBoxLayout()
        header.setContentsMargins(0, 4, 0, 8)
        brand = QLabel("MERIDIAN")
        brand.setObjectName("brand")
        self.band_chip = QLabel("Night")
        self.band_chip.setObjectName("chip")
        self.mode_box = QComboBox()
        for mode in Mode:
            self.mode_box.addItem(MODE_LABELS[mode], mode.value)
        idx = self.mode_box.findData(self.mode.value)
        if idx >= 0:
            self.mode_box.setCurrentIndex(idx)
        self.hint = QLabel(MODE_HINTS[self.mode])
        self.hint.setObjectName("hint")
        self.search = TrackSearch(self.library)
        self.search.setMinimumWidth(260)
        add_btn = QPushButton("Add library folder")
        add_btn.setObjectName("ghostBtn")
        scan_btn = QPushButton("Rescan")
        scan_btn.setObjectName("ghostBtn")
        add_btn.clicked.connect(self.add_folder)
        scan_btn.clicked.connect(self.start_rescan)
        header.addWidget(brand)
        header.addSpacing(12)
        header.addWidget(self.band_chip)
        header.addWidget(self.mode_box)
        header.addWidget(self.hint, 1)
        header.addWidget(self.search)
        header.addWidget(add_btn)
        header.addWidget(scan_btn)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        map_label = QLabel(
            "MOOD MAP  ·  drag a star to pin  ·  scroll = lens  ·  pinch / Ctrl+scroll = dive  ·  drag empty = pan  ·  double-click empty = night sky"
        )
        map_label.setObjectName("section")
        self.map = MoodMap()
        left_l.addWidget(map_label)
        left_l.addWidget(self.map, 1)

        right = QSplitter(Qt.Orientation.Vertical)
        right.setHandleWidth(18)
        right.setChildrenCollapsible(False)
        self.matrix = EisenhowerMatrix()
        queue_wrap = QFrame()
        queue_wrap.setObjectName("queuePanel")
        q_l = QVBoxLayout(queue_wrap)
        q_l.setContentsMargins(10, 10, 10, 10)
        q_l.setSpacing(8)
        q_head = QLabel("CONTEXT QUEUE  ·  replenishes from lens, clock, and matrix when empty")
        q_head.setObjectName("section")
        self.queue_list = FitList()
        self.queue_list.setObjectName("queueList")
        self.queue_list.setFont(condensed(12))
        q_l.addWidget(q_head)
        q_l.addWidget(self.queue_list, 1)
        right.addWidget(self.matrix)
        right.addWidget(queue_wrap)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 2)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.transport = TransportBar()
        layout.addLayout(header)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.transport)

        status = QStatusBar()
        self.setStatusBar(status)
        self.status_label = QLabel("Local, offline, map-first.")
        status.addWidget(self.status_label)

        play_act = QAction("Play/Pause", self)
        play_act.setShortcut(QKeySequence(Qt.Key.Key_Space))
        play_act.triggered.connect(self.toggle_play)
        self.addAction(play_act)
        next_act = QAction("Next", self)
        next_act.setShortcut(QKeySequence("Ctrl+Right"))
        next_act.triggered.connect(self.play_next)
        self.addAction(next_act)
        prev_act = QAction("Previous", self)
        prev_act.setShortcut(QKeySequence("Ctrl+Left"))
        prev_act.triggered.connect(self.play_prev)
        self.addAction(prev_act)
        find_act = QAction("Search", self)
        find_act.setShortcut(QKeySequence.StandardKey.Find)
        find_act.triggered.connect(self.search.setFocus)
        self.addAction(find_act)

    def _bind(self) -> None:
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.map.lens_changed.connect(self._lens_changed)
        self.map.track_pinned.connect(self._pin_track)
        self.map.track_activated.connect(self.play_id)
        self.map.track_hovered.connect(self.status_label.setText)
        self.matrix.track_activated.connect(self._pull_and_play)
        self.queue_list.itemDoubleClicked.connect(self._queue_activated)
        self.search.track_chosen.connect(self._search_picked)
        self.transport.play_toggled.connect(self.toggle_play)
        self.transport.previous.connect(self.play_prev)
        self.transport.next.connect(self.play_next)
        self.transport.seeked.connect(self.player.seek)
        self.transport.volume_changed.connect(self.player.set_volume)
        self.transport.love_toggled.connect(self._love)
        self.player.position_changed.connect(self._pos)
        self.player.duration_changed.connect(self._dur)
        self.player.state_changed.connect(self.transport.set_playing)
        self.player.track_nearly_finished.connect(self._nearly_finished)
        self.player.track_finished.connect(self._track_finished_hard)
        self.player.natural_listen_completed.connect(self._natural_listen_completed)
        self.player.error_occurred.connect(lambda m: self.status_label.setText(m))

    def _restore_lens(self) -> None:
        x = float(self.settings.value("lens_x", 0.52))
        y = float(self.settings.value("lens_y", 0.48))
        r = float(self.settings.value("lens_r", LENS_RADIUS_DEFAULT))
        self._apply_mode_lens_scale()
        self.map.set_lens(x, y, r)

    def skip_pressure(self) -> float:
        cutoff = time() - 900
        self.skips_window = [t for t in self.skips_window if t > cutoff]
        return min(1.0, len(self.skips_window) / 6)

    def current_context(self):
        x, y, r = self.map.lens_mood()
        _, _, scale = mode_bias(self.mode)
        return make_context(self.mode, x, y, r * scale, self.skip_pressure())

    def _apply_mode_lens_scale(self) -> None:
        _, _, scale = mode_bias(self.mode)
        self.map.set_radius_scale(scale)

    def refresh_plan(self, keep_current: bool = True, rebuild_queue: bool = True) -> None:
        if self._rebuild_lock:
            return
        ctx = self.current_context()
        self.band_chip.setText(ctx.band_label)
        tracks = self.library.all_tracks()
        current_id = self.player.current.id if self.player.current else None
        self.plan = build_plan(tracks, ctx, self.explicit)
        self.map.set_tracks(self.plan.ranked, current_id)
        self.matrix.set_plan(self.plan.by_quadrant)
        if rebuild_queue:
            self.ephemeral.clear()
            self.session_queue = list(self.plan.order)
            if keep_current and current_id and current_id in self.session_queue:
                self.queue_index = self.session_queue.index(current_id)
            else:
                self.queue_index = 0
        self._fill_queue()
        n = len(tracks)
        self.status_label.setText(f"{n} local tracks · lens at mood {ctx.lens_x:.2f},{ctx.lens_y:.2f}")

    def _fill_queue(self) -> None:
        self.queue_list.clear()
        if not self.session_queue:
            return
        by_id = {r.track.id: r for r in self.plan.ranked} if self.plan else {}
        for i, tid in enumerate(self.session_queue):
            track = self.library.get(tid)
            if not track:
                continue
            mark = "· " if tid in self.ephemeral else ""
            item = QListWidgetItem(f"{i + 1:02d}  {mark}{track.short_title}")
            item.setData(Qt.ItemDataRole.UserRole, tid)
            ranked = by_id.get(tid)
            tip = self._queue_reason(track, ranked, tid in self.ephemeral)
            if ranked:
                item.setForeground(QColor(PLAYLIST_HEX[ranked.quadrant]))
            item.setToolTip(tip)
            if i == self.queue_index:
                item.setSelected(True)
            self.queue_list.addItem(item)

    def _queue_reason(self, track, ranked, is_ephemeral: bool) -> str:
        lines = [track.label]
        if is_ephemeral:
            lines.append("⮕ You picked this from the matrix — plays once then removed")
        if ranked:
            q = ranked.quadrant
            fit_pct = f"{ranked.fit:.0%}"
            imp_pct = f"{ranked.importance:.0%}"
            if q == Quadrant.NOW:
                lines.append(f"NOW — closest to the lens ({fit_pct} fit), high importance ({imp_pct})")
            elif q == Quadrant.DEEP:
                lines.append(f"DEEP — important ({imp_pct}) but just outside the lens core")
            elif q == Quadrant.FILL:
                lines.append(f"FILL — near the lens ({fit_pct} fit) but lower importance ({imp_pct})")
            else:
                lines.append(f"SHELF — outside the lens area ({fit_pct} fit, {imp_pct} importance)")
            reasons = []
            if track.loved:
                reasons.append("♥ loved — boosted importance")
            if track.pinned:
                reasons.append("pinned mood position on the map")
            if track.play_count >= 4:
                reasons.append(f"played {track.play_count}× — familiar pick")
            elif track.play_count == 0:
                reasons.append("never played — fresh discovery")
            if track.skip_count > track.play_count and track.skip_count >= 3:
                reasons.append(f"skipped often ({track.skip_count}×) — deprioritized")
            ctx = self.current_context()
            reasons.append(f"clock band: {ctx.band_label}")
            reasons.append(f"mode: {self.mode.value.title()}")
            reasons.append(f"mood: valence {track.valence:.2f}, energy {track.energy:.2f}")
            conf = float(getattr(track, "mood_confidence", 0.5) or 0.5)
            if track.pinned:
                reasons.append("confidence 1.00 (pinned)")
            else:
                reasons.append(f"confidence {conf:.2f}")
                note = (getattr(track, "confidence_note", "") or "").strip()
                if note:
                    reasons.append(note)
                if conf < CONFIDENCE_LOW:
                    reasons.append("weak placement evidence (dimmed)")
                elif conf < CONFIDENCE_HIGH:
                    reasons.append("partial placement evidence")
            if reasons:
                lines.append("Why: " + " · ".join(reasons))
        else:
            lines.append("Added to the queue directly")
        return "\n".join(lines)

    def _mode_changed(self) -> None:
        self.mode = Mode(self.mode_box.currentData())
        self.settings.setValue("mode", self.mode.value)
        self.hint.setText(MODE_HINTS[self.mode])
        self._apply_mode_lens_scale()
        self.refresh_plan()

    def _lens_changed(self, x: float, y: float, r: float) -> None:
        self.settings.setValue("lens_x", x)
        self.settings.setValue("lens_y", y)
        self.settings.setValue("lens_r", r)
        self._lens_timer.start()

    def _search_picked(self, track_id: int) -> None:
        track = self.library.get(track_id)
        if not track:
            return
        _, _, radius = self.map.lens_mood()
        self.map.set_lens(track.valence, track.energy, radius)
        self.settings.setValue("lens_x", track.valence)
        self.settings.setValue("lens_y", track.energy)
        self.settings.setValue("lens_r", radius)
        self.status_label.setText(f"Lens on {track.label}")
        self._pull_and_play(track_id)

    def _pin_track(self, track_id: int, valence: float, energy: float) -> None:
        self.library.set_mood(track_id, valence, energy, pinned=True)
        self.refresh_plan()

    def add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add music folder", str(Path.home() / "Music"))
        if path:
            self.library.add_folder(path)
            self.start_scan()

    def start_rescan(self) -> None:
        """Force re-read tags and re-analyze every track under library folders."""
        if self._scan_thread and self._scan_thread.isRunning():
            return
        n = len(self.library.all_tracks())
        reply = QMessageBox.warning(
            self,
            "Rescan whole library?",
            (
                "Rescan re-reads tags and re-analyzes mood for every track in your "
                f"library folders ({n} track{'s' if n != 1 else ''}).\n\n"
                "This can take a while on large libraries. Pinned stars keep their "
                "positions; everything else may move on the map.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._stop_analyze(wait_ms=8000)
        pending = self.library.mark_all_pending_analysis()
        self.status_label.setText(f"Rescanning library ({pending} tracks to re-analyze)…")
        self._start_scan_worker(force=True, on_finished=self._rescan_done)

    def _rescan_done(self, count: int) -> None:
        self._cleanup_scan_thread()
        if self._closing:
            return
        self.status_label.setText(f"Rescanned {count} files. Re-analyzing waveforms…")
        self.refresh_plan()
        self.start_analyze()

    def start_scan(self) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            return
        self.status_label.setText("Scanning local files…")
        self._start_scan_worker(force=False, on_finished=self._scan_done)

    def _start_scan_worker(self, *, force: bool, on_finished) -> None:
        self._cleanup_scan_thread()
        self._scan_worker = ScanWorker(self.library, force=force)
        self._scan_thread = start_worker(self._scan_worker)
        self._scan_worker.progress.connect(lambda n: self.status_label.setText(f"Found {n}"))
        self._scan_worker.failed.connect(lambda m: QMessageBox.warning(self, "Scan failed", m))
        self._scan_worker.finished.connect(on_finished)

    def _cleanup_scan_thread(self) -> None:
        if self._scan_thread:
            self._scan_thread.quit()
            self._scan_thread.wait(3000)
            self._scan_thread.deleteLater()
            self._scan_thread = None
        if self._scan_worker:
            self._scan_worker.deleteLater()
            self._scan_worker = None

    def _stop_analyze(self, wait_ms: int = 5000) -> None:
        # Bump generation first so a late finished signal cannot restart analyze.
        self._analyze_gen += 1
        worker = self._analyze_worker
        thread = self._analyze_thread
        self._analyze_worker = None
        self._analyze_thread = None
        if worker is not None:
            worker.abort()
            try:
                worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(wait_ms)
        if thread is not None:
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()

    def _scan_done(self, added: int) -> None:
        self._cleanup_scan_thread()
        if self._closing:
            return
        self.status_label.setText(f"Indexed {added} new files. Mapping mood…")
        self.refresh_plan()
        self.start_analyze()

    def start_analyze(self) -> None:
        if self._closing:
            return
        if self._analyze_thread and self._analyze_thread.isRunning():
            return
        if not self.library.unanalyzed_ids():
            self.status_label.setText("Mood map updated from local audio.")
            return
        self._analyze_gen += 1
        gen = self._analyze_gen
        self._analyze_worker = AnalyzeWorker(self.library)
        self._analyze_thread = start_worker(self._analyze_worker)
        self._analyze_worker.progress.connect(
            lambda name, i, n: self.status_label.setText(f"Listening to waveform {i}/{n}: {name}")
        )
        self._analyze_worker.finished.connect(lambda g=gen: self._analyze_done(g))

    def _analyze_done(self, gen: int) -> None:
        # Ignore stale workers that finished after abort/rescan/quit.
        if gen != self._analyze_gen or self._closing:
            return
        thread = self._analyze_thread
        worker = self._analyze_worker
        self._analyze_thread = None
        self._analyze_worker = None
        if thread:
            thread.quit()
            thread.wait(3000)
            thread.deleteLater()
        if worker:
            worker.deleteLater()
        if self._closing:
            return
        self.refresh_plan()
        # If scan added more tracks while we were analyzing, finish them.
        if self.library.unanalyzed_ids():
            self.status_label.setText("More tracks to map…")
            self.start_analyze()
            return
        self.status_label.setText("Mood map updated from local audio.")

    def _queue_activated(self, item: QListWidgetItem) -> None:
        tid = item.data(Qt.ItemDataRole.UserRole)
        if not tid:
            return
        track_id = int(tid)
        if track_id in self.session_queue:
            self.queue_index = self.session_queue.index(track_id)
        self.play_id(track_id)

    def _pull_and_play(self, track_id: int) -> None:
        """Insert a matrix pick into the context queue, play it once, then continue."""
        if track_id in self.session_queue:
            old = self.session_queue.index(track_id)
            self.session_queue.pop(old)
            if old < self.queue_index:
                self.queue_index -= 1
            elif old == self.queue_index and self.queue_index > 0:
                self.queue_index -= 1
        if self.player.current and self.session_queue:
            insert_at = min(self.queue_index + 1, len(self.session_queue))
        else:
            insert_at = max(0, min(self.queue_index, len(self.session_queue)))
        self.session_queue.insert(insert_at, track_id)
        self.ephemeral.add(track_id)
        self.queue_index = insert_at
        if track_id not in self.explicit:
            self.explicit.insert(0, track_id)
            self.explicit = self.explicit[:12]
        self.play_id(track_id)

    def toggle_play(self) -> None:
        """Pause/resume current track, or start the context queue if nothing is loaded."""
        if self.player.is_playing():
            self.player.toggle()
            return
        if self.player.current is not None:
            # Paused (or stopped mid-track) — resume.
            self.player.toggle()
            return
        if not self.session_queue:
            self._replenish_queue()
        if not self.session_queue:
            self.status_label.setText("Context queue is empty — move the lens or replenish.")
            return
        self.queue_index = max(0, min(self.queue_index, len(self.session_queue) - 1))
        self.play_id(self.session_queue[self.queue_index])

    @Slot(int)
    def play_id(self, track_id: int, *, _depth: int = 0) -> None:
        if _depth > 48:
            self.status_label.setText("No playable tracks left in the queue.")
            return
        track = self.library.get(track_id)
        if track is None or not Path(track.path).exists():
            msg = "Track removed from library." if track is None else "File missing on disk."
            self.status_label.setText(msg)
            next_id = self._skip_unplayable(track_id)
            if next_id is not None:
                self.play_id(next_id, _depth=_depth + 1)
            return
        self._rebuild_lock = True
        self.library.record_play(track_id, time())
        self.played_history.append(track_id)
        self.played_history = self.played_history[-48:]
        self.player.play_track(track)
        self.transport.set_track(track.short_title, f"{track.artist}  ·  {track.album or 'Single'}", track.loved)
        self._rebuild_lock = False
        if self.plan:
            self.map.set_tracks(self.plan.ranked, track_id)
        self._fill_queue()

    def _skip_unplayable(self, track_id: int) -> int | None:
        """Drop a missing/deleted id from the queue and return the next candidate."""
        self.played_history.append(track_id)
        self.played_history = self.played_history[-48:]
        self.ephemeral.discard(track_id)
        if track_id in self.session_queue:
            idx = self.session_queue.index(track_id)
            self.session_queue.pop(idx)
            self.queue_index = idx
        else:
            self.queue_index += 1
        if self.queue_index >= len(self.session_queue) or not self.session_queue:
            self._replenish_queue()
            self.queue_index = 0
        if not self.session_queue:
            return None
        self.queue_index = min(self.queue_index, len(self.session_queue) - 1)
        self._fill_queue()
        return self.session_queue[self.queue_index]

    def play_next(self) -> None:
        # During natural crossfade, current is already the incoming track at ~0ms.
        # Credit the skip to the outgoing track (pending finish), not the new one.
        if self.player.is_crossfading() and self._pending_finish_nudge is not None:
            outgoing = self._pending_finish_nudge
            self._pending_finish_nudge = None
            self.library.record_skip(outgoing)
            self.skips_window.append(time())
            self._listen_nudge(outgoing, skipped=True)
            self._advance_queue(skipped=True)
            return
        self._pending_finish_nudge = None
        skipped = bool(self.player.current and self.player.backend.position() < 8000)
        if self.player.current:
            if skipped:
                self.library.record_skip(self.player.current.id)
                self.skips_window.append(time())
            self._listen_nudge(self.player.current.id, skipped=skipped)
        self._advance_queue(skipped=skipped)

    def play_prev(self) -> None:
        self._pending_finish_nudge = None
        if not self.session_queue:
            self._replenish_queue()
        if not self.session_queue:
            return
        self.queue_index = max(0, self.queue_index - 1)
        self.play_id(self.session_queue[self.queue_index])

    def _nearly_finished(self) -> None:
        # Arm crossfade / advance now; credit the listen when the fade completes.
        if self.player.current:
            self._pending_finish_nudge = self.player.current.id
        self._advance_queue(skipped=False)

    def _natural_listen_completed(self) -> None:
        tid = self._pending_finish_nudge
        self._pending_finish_nudge = None
        if tid is not None:
            self._listen_nudge(tid, skipped=False)

    def _track_finished_hard(self) -> None:
        # Short tracks (no nearly-finished arm): nudge + advance together.
        self._pending_finish_nudge = None
        if self.player.current:
            self._listen_nudge(self.player.current.id, skipped=False)
        self._advance_queue(skipped=False)

    def _listen_nudge(self, track_id: int, *, skipped: bool) -> None:
        """Local-only: gently move unpinned stars from skip/finish under the lens."""
        lx, ly, _ = self.map.lens_mood()
        moved = self.library.nudge_mood_from_listen(
            track_id, lens_x=lx, lens_y=ly, skipped=skipped
        )
        if moved:
            self.refresh_plan(keep_current=True, rebuild_queue=False)

    def _advance_queue(self, skipped: bool = False) -> None:
        current_id = self.player.current.id if self.player.current else None
        if current_id is not None and current_id in self.ephemeral:
            self.ephemeral.discard(current_id)
            if current_id in self.session_queue:
                idx = self.session_queue.index(current_id)
                self.session_queue.pop(idx)
                self.queue_index = idx
            else:
                self.queue_index += 1
        else:
            self.queue_index += 1
        if self.queue_index >= len(self.session_queue) or not self.session_queue:
            self._replenish_queue()
            self.queue_index = 0
        if not self.session_queue:
            return
        self.queue_index = min(self.queue_index, len(self.session_queue) - 1)
        self.play_id(self.session_queue[self.queue_index])

    def _replenish_queue(self) -> None:
        """Build a fresh context queue from lens, time of day, and matrix lists."""
        ctx = self.current_context()
        self.band_chip.setText(ctx.band_label)
        # Skip ghost rows whose files are gone so the queue cannot refill with them.
        tracks = [t for t in self.library.all_tracks() if Path(t.path).exists()]
        exclude = set(self.played_history[-24:])
        self.plan = build_plan(tracks, ctx, self.explicit, exclude_ids=exclude)
        current_id = self.player.current.id if self.player.current else None
        self.map.set_tracks(self.plan.ranked, current_id)
        self.matrix.set_plan(self.plan.by_quadrant)
        self.ephemeral.clear()
        self.session_queue = list(self.plan.order)
        self._fill_queue()
        self.status_label.setText(
            f"Context queue replenished · {ctx.band_label} · {len(self.session_queue)} tracks from the matrix"
        )

    def _love(self) -> None:
        if not self.player.current:
            return
        loved = self.library.toggle_loved(self.player.current.id)
        track = self.library.get(self.player.current.id)
        if track:
            self.transport.set_track(track.short_title, f"{track.artist}  ·  {track.album or 'Single'}", loved)
        self.refresh_plan(rebuild_queue=False)

    def _pos(self, pos: int) -> None:
        self.transport.set_progress(pos, self._duration)

    def _dur(self, dur: int) -> None:
        self._duration = dur
        self.transport.set_progress(self.player.backend.position(), dur)

    def closeEvent(self, event) -> None:
        self._closing = True
        self._pending_finish_nudge = None
        self._stop_analyze(wait_ms=12000)
        if self._scan_worker:
            self._scan_worker.abort()
        self._cleanup_scan_thread()
        self.library.close()
        super().closeEvent(event)
