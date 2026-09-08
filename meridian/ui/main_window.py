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
from meridian.host_deps import (
    libx264_missing_message,
    libx264_missing_status,
    should_warn_missing_libx264,
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
        # Timed-out workers kept alive (signals disconnected) until QThread ends.
        self._lingering_workers: list[tuple] = []
        self._close_library_when_idle = False
        self._closing = False
        self._pending_play_credit: int | None = None
        # Outgoing track of the active crossfade (for Next/Prev / settle credit).
        self._crossfade_outgoing_id: int | None = None
        # When True, natural fade settle finish-nudges `_crossfade_outgoing_id`.
        # User jumps credit immediately instead (skip vs finish from position).
        self._outgoing_settle_finish: bool = False
        self._expect_natural_advance: bool = False
        self._host_codec_sticky = False
        self._duration = 0
        self._rebuild_lock = False
        # Listen-nudge / lens refresh requested while play_id holds the rebuild lock.
        self._pending_plan_refresh = False
        self._handling_playback_error = False
        # Hard-cut play_id credits immediately; cleared/undone if media errors.
        self._last_hard_play_credit: int | None = None
        self._lens_timer = QTimer(self)
        self._lens_timer.setSingleShot(True)
        self._lens_timer.setInterval(180)
        self._lens_timer.timeout.connect(lambda: self.refresh_plan(rebuild_queue=False))

        self._build()
        self._bind()
        self._restore_lens()
        if not self.library.folders():
            music = Path.home() / "Music"
            if music.is_dir():
                self.library.add_folder(str(music))
        self.refresh_plan()
        QTimer.singleShot(400, self.start_scan)
        QTimer.singleShot(900, self._maybe_warn_libx264)

    def _set_status(self, message: str) -> None:
        """Set the status bar, keeping a sticky libx264 tip when the host lacks it."""
        text = message or ""
        if self._host_codec_sticky and should_warn_missing_libx264():
            tip = libx264_missing_status()
            if tip and tip not in text:
                text = f"{text} · {tip}" if text else tip
        else:
            self._host_codec_sticky = False
        self.status_label.setText(text)

    def _maybe_warn_libx264(self) -> None:
        """AppImage keeps libx264 on the host — tell the user if playback may be broken."""
        if not should_warn_missing_libx264():
            self._host_codec_sticky = False
            return
        self._host_codec_sticky = True
        self._set_status(libx264_missing_status())
        if self.settings.value("host/skip_libx264_warning", False, type=bool):
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("System library needed for playback")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(libx264_missing_message())
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        dont = box.addButton("Don’t show again", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is dont:
            self.settings.setValue("host/skip_libx264_warning", True)
        # Re-assert after the dialog so scan/analyze progress cannot bury the tip forever.
        self._set_status(libx264_missing_status())

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
        self.map.track_activated.connect(self._map_activated)
        self.map.track_hovered.connect(self._set_status)
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
        self.player.crossfade_settled.connect(self._crossfade_settled)
        self.player.error_occurred.connect(self._playback_error)

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

    def _playable_tracks(self):
        """Library rows whose files still exist and are not playback-denylisted."""
        return [
            t
            for t in self.library.all_tracks()
            if Path(t.path).exists() and not self.library.is_playback_denied(t.id)
        ]

    def _flush_pending_plan_refresh(self) -> None:
        if not self._pending_plan_refresh:
            return
        self._pending_plan_refresh = False
        self.refresh_plan(rebuild_queue=False)

    def refresh_plan(self, keep_current: bool = True, rebuild_queue: bool = True) -> None:
        if self._rebuild_lock:
            # Never drop a non-rebuild refresh (listen nudge / lens) permanently.
            if not rebuild_queue:
                self._pending_plan_refresh = True
            return
        ctx = self.current_context()
        self.band_chip.setText(ctx.band_label)
        tracks = self._playable_tracks()
        current_id = self.player.current.id if self.player.current else None
        self.plan = build_plan(tracks, ctx, self.explicit)
        self.map.set_tracks(self.plan.ranked, current_id)
        self.matrix.set_plan(self.plan.by_quadrant)
        if rebuild_queue:
            # Keep one-shot matrix pulls that still appear in the new order.
            kept_ephemeral = {tid for tid in self.ephemeral if tid in self.plan.order}
            self.session_queue = list(self.plan.order)
            self.ephemeral = kept_ephemeral
            if keep_current and current_id and current_id in self.session_queue:
                self.queue_index = self.session_queue.index(current_id)
            elif keep_current and current_id:
                # Still playing something absent from the new queue: Next should
                # land on slot 0, not skip it via queue_index += 1 from 0.
                self.queue_index = -1
            else:
                self.queue_index = 0
        self._fill_queue()
        n = len(tracks)
        self._set_status(f"{n} local tracks · lens at mood {ctx.lens_x:.2f},{ctx.lens_y:.2f}")

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
        self._set_status(f"Lens on {track.label}")
        # set_lens does not emit lens_changed — refresh matrix/plan for the new lens.
        self.refresh_plan(rebuild_queue=False)
        self._pull_and_play(track_id)

    def _pin_track(self, track_id: int, valence: float, energy: float) -> None:
        self.library.set_mood(track_id, valence, energy, pinned=True)
        self.refresh_plan(rebuild_queue=False)

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
        self._stop_analyze(wait_ms=20000)
        pending = self.library.mark_all_pending_analysis()
        self._set_status(f"Rescanning library ({pending} tracks to re-analyze)…")
        self._start_scan_worker(force=True, on_finished=self._rescan_done)

    def _rescan_done(self, count: int) -> None:
        self._cleanup_scan_thread()
        if self._closing:
            return
        if count < 0:
            self._set_status("Rescan failed.")
            return
        self._set_status(f"Rescanned {count} files. Re-analyzing waveforms…")
        self.refresh_plan(rebuild_queue=False)
        self.start_analyze()

    def start_scan(self) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            return
        self._set_status("Scanning local files…")
        self._start_scan_worker(force=False, on_finished=self._scan_done)

    def _start_scan_worker(self, *, force: bool, on_finished) -> None:
        self._cleanup_scan_thread()
        self._scan_worker = ScanWorker(self.library, force=force)
        self._scan_thread = start_worker(self._scan_worker)
        self._scan_worker.progress.connect(lambda n: self._set_status(f"Found {n}"))
        self._scan_worker.failed.connect(lambda m: QMessageBox.warning(self, "Scan failed", m))
        self._scan_worker.finished.connect(on_finished)

    def _disconnect_worker(self, worker) -> None:
        if worker is None:
            return
        for name in ("progress", "finished", "failed"):
            sig = getattr(worker, name, None)
            if sig is None:
                continue
            try:
                sig.disconnect()
            except (RuntimeError, TypeError):
                pass

    def _linger_worker(self, thread, worker) -> None:
        """Keep a timed-out thread alive with UI signals detached until it exits."""
        if thread is None:
            return
        pair = (thread, worker)
        self._lingering_workers.append(pair)

        def _reap() -> None:
            if pair in self._lingering_workers:
                self._lingering_workers.remove(pair)
            thread.deleteLater()
            if worker is not None:
                worker.deleteLater()
            if self._close_library_when_idle and not self._lingering_workers:
                try:
                    self.library.close()
                except Exception:
                    pass
                self._close_library_when_idle = False

        thread.finished.connect(_reap)

    def _cleanup_scan_thread(self, wait_ms: int = 8000) -> bool:
        """Stop the scan worker. Returns True when the thread is fully stopped."""
        worker = self._scan_worker
        thread = self._scan_thread
        self._scan_worker = None
        self._scan_thread = None
        if worker is not None:
            worker.abort()
            self._disconnect_worker(worker)
            # Re-attach quit so wait() can finish after run returns.
            if thread is not None:
                try:
                    worker.finished.connect(lambda *_a, t=thread: t.quit())
                except (RuntimeError, TypeError):
                    pass
        if thread is not None and thread.isRunning():
            thread.quit()
            if not thread.wait(wait_ms):
                self._linger_worker(thread, worker)
                return False
        if thread is not None:
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()
        return True

    def _stop_analyze(self, wait_ms: int = 20000) -> bool:
        """Stop analyze. Returns True when the thread is fully stopped."""
        # Bump generation first so a late finished signal cannot restart analyze.
        # Abort kills in-flight ffmpeg so this wait stays bounded.
        self._analyze_gen += 1
        worker = self._analyze_worker
        thread = self._analyze_thread
        self._analyze_worker = None
        self._analyze_thread = None
        if worker is not None:
            worker.abort()
            self._disconnect_worker(worker)
            if thread is not None:
                try:
                    worker.finished.connect(lambda *_a, t=thread: t.quit())
                except (RuntimeError, TypeError):
                    pass
        if thread is not None and thread.isRunning():
            thread.quit()
            if not thread.wait(wait_ms):
                self._linger_worker(thread, worker)
                return False
        if thread is not None:
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()
        return True

    def _scan_done(self, added: int) -> None:
        self._cleanup_scan_thread()
        if self._closing:
            return
        if added < 0:
            self._set_status("Scan failed.")
            return
        self._set_status(f"Indexed {added} new files. Mapping mood…")
        self.refresh_plan(rebuild_queue=False)
        self.start_analyze()

    def start_analyze(self) -> None:
        if self._closing:
            return
        if self._analyze_thread and self._analyze_thread.isRunning():
            return
        if not self.library.unanalyzed_ids():
            self._set_status("Mood map updated from local audio.")
            return
        self._analyze_gen += 1
        gen = self._analyze_gen
        self._analyze_worker = AnalyzeWorker(self.library)
        self._analyze_thread = start_worker(self._analyze_worker)
        self._analyze_worker.progress.connect(
            lambda name, i, n: self._set_status(f"Listening to waveform {i}/{n}: {name}")
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
        self.refresh_plan(rebuild_queue=False)
        # If scan added more tracks while we were analyzing, finish them.
        if self.library.unanalyzed_ids():
            self._set_status("More tracks to map…")
            self.start_analyze()
            return
        self._set_status("Mood map updated from local audio.")

    def _map_activated(self, track_id: int) -> None:
        """Play a map star and keep context-queue Next/Prev aligned with it."""
        if track_id in self.session_queue:
            self.queue_index = self.session_queue.index(track_id)
            self.play_id(track_id)
        else:
            self._pull_and_play(track_id)

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
            self._set_status("Context queue is empty — move the lens or replenish.")
            return
        self.queue_index = max(0, min(self.queue_index, len(self.session_queue) - 1))
        self.play_id(self.session_queue[self.queue_index])

    @Slot(int)
    def play_id(self, track_id: int, *, _depth: int = 0) -> None:
        if _depth > 48:
            self._set_status("No playable tracks left in the queue.")
            return
        track = self.library.get(track_id)
        if (
            track is None
            or not Path(track.path).exists()
            or self.library.is_playback_denied(track_id)
        ):
            if track is None:
                msg = "Track removed from library."
            elif self.library.is_playback_denied(track_id):
                msg = "Skipping unplayable track."
            else:
                msg = "File missing on disk."
            self._set_status(msg)
            next_id = self._skip_unplayable(track_id)
            if next_id is not None:
                self.play_id(next_id, _depth=_depth + 1)
            return
        self._rebuild_lock = True
        outgoing = self.player.current
        outgoing_id = outgoing.id if outgoing is not None else None
        outgoing_pos = int(self.player.backend.position() or 0) if outgoing is not None else 0
        natural_advance = self._expect_natural_advance
        self._expect_natural_advance = False

        # Interrupting an in-flight fade: settle credit for prior outgoing + pending.
        if self.player.is_crossfading() and self._crossfade_outgoing_id is not None:
            prior = self._crossfade_outgoing_id
            settle_finish = self._outgoing_settle_finish
            pending = self._pending_play_credit
            self._clear_crossfade_credit()
            if prior != track_id and settle_finish:
                self._listen_nudge(prior, skipped=False)
            # Armed incoming that we are abandoning still counts as a play.
            if (
                pending is not None
                and pending != track_id
                and self.player.current is not None
                and pending == self.player.current.id
            ):
                self._commit_play(pending)

        self._pending_play_credit = None
        self._last_hard_play_credit = None
        self.player.play_track(track)
        if self.player.is_crossfading() and outgoing_id is not None and outgoing_id != track_id:
            self._pending_play_credit = track_id
            self._crossfade_outgoing_id = outgoing_id
            if natural_advance:
                # End-of-track auto-advance: finish-nudge outgoing when the fade lands.
                self._outgoing_settle_finish = True
            else:
                # Map / matrix / search jump: credit abandon now (same 8s rule as Next).
                self._outgoing_settle_finish = False
                self._credit_listen(outgoing_id, position_ms=outgoing_pos)
        else:
            self._clear_crossfade_credit()
            self._commit_play(track_id)
            self._last_hard_play_credit = track_id
        self.transport.set_track(track.short_title, f"{track.artist}  ·  {track.album or 'Single'}", track.loved)
        self._rebuild_lock = False
        self._flush_pending_plan_refresh()
        if self.plan:
            self.map.set_tracks(self.plan.ranked, track_id)
        self._fill_queue()

    def _clear_crossfade_credit(self) -> None:
        self._crossfade_outgoing_id = None
        self._outgoing_settle_finish = False
        self._pending_play_credit = None

    def _credit_listen(self, track_id: int, *, position_ms: int) -> None:
        """Skip vs finish from how far the listener got (matches Next’s 8s rule)."""
        skipped = position_ms < 8000
        if skipped:
            self.library.record_skip(track_id)
            self.skips_window.append(time())
        self._listen_nudge(track_id, skipped=skipped)

    def _commit_play(self, track_id: int) -> None:
        self.library.record_play(track_id, time())
        self.played_history.append(track_id)
        self.played_history = self.played_history[-48:]

    def _play_restart(self, track_id: int) -> None:
        """Hard-restart a track without bumping play_count (Prev during crossfade)."""
        track = self.library.get(track_id)
        if track is None or not Path(track.path).exists():
            return
        self._rebuild_lock = True
        self._clear_crossfade_credit()
        self._expect_natural_advance = False
        # Stop so play_track hard-cuts instead of fading and re-arming credit.
        self.player.stop()
        self.player.play_track(track)
        self.transport.set_track(track.short_title, f"{track.artist}  ·  {track.album or 'Single'}", track.loved)
        self._rebuild_lock = False
        self._flush_pending_plan_refresh()
        if self.plan:
            self.map.set_tracks(self.plan.ranked, track_id)
        self._fill_queue()

    def _playback_error(self, message: str) -> None:
        """Corrupt/unsupported media: show status and skip like a missing file."""
        self._set_status(message)
        if self._handling_playback_error or self._closing:
            return
        current = self.player.current
        if current is None:
            return
        self._handling_playback_error = True
        try:
            tid = current.id
            self.library.mark_playback_failed(tid)
            # Drop deferred fade credit, or undo a hard-cut play_count bump.
            if self._pending_play_credit == tid:
                self._pending_play_credit = None
            elif self._last_hard_play_credit == tid:
                self.library.unrecord_play(tid)
                if self.played_history and self.played_history[-1] == tid:
                    self.played_history.pop()
                self._last_hard_play_credit = None
            # If we were fading into this bad file, finish-nudge the outgoing track.
            if self.player.is_crossfading() and self._crossfade_outgoing_id is not None:
                if self._outgoing_settle_finish:
                    self._listen_nudge(self._crossfade_outgoing_id, skipped=False)
                self._clear_crossfade_credit()
            self.player.stop()
            self.player.release_advance_lock()
            self._expect_natural_advance = False
            next_id = self._skip_unplayable(tid)
            if next_id is not None:
                self.play_id(next_id)
            else:
                self._set_status(f"{message} — no playable tracks left.")
        finally:
            self._handling_playback_error = False

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
            self._replenish_queue(avoid_id=track_id)
            self.queue_index = 0
        if not self.session_queue:
            self.player.release_advance_lock()
            return None
        self.queue_index = min(self.queue_index, len(self.session_queue) - 1)
        self._fill_queue()
        return self.session_queue[self.queue_index]

    def play_next(self) -> None:
        # During crossfade, current is already the incoming track at ~0ms.
        if self.player.is_crossfading() and self._crossfade_outgoing_id is not None:
            outgoing = self._crossfade_outgoing_id
            settle_finish = self._outgoing_settle_finish
            pending = self._pending_play_credit
            self._clear_crossfade_credit()
            if settle_finish:
                # Natural A→B: A essentially finished — never skip-credit it.
                self._listen_nudge(outgoing, skipped=False)
            # Jump fades already credited outgoing in play_id; do not credit again.
            if (
                pending is not None
                and self.player.current is not None
                and pending == self.player.current.id
            ):
                self._commit_play(pending)
            # Next means leave the incoming (current) track under the 8s rule.
            skipped = bool(self.player.current and self.player.backend.position() < 8000)
            if self.player.current:
                if skipped:
                    self.library.record_skip(self.player.current.id)
                    self.skips_window.append(time())
                self._listen_nudge(self.player.current.id, skipped=skipped)
            self._advance_queue(skipped=skipped)
            return
        self._clear_crossfade_credit()
        skipped = bool(self.player.current and self.player.backend.position() < 8000)
        if self.player.current:
            if skipped:
                self.library.record_skip(self.player.current.id)
                self.skips_window.append(time())
            self._listen_nudge(self.player.current.id, skipped=skipped)
        self._advance_queue(skipped=skipped)

    def play_prev(self) -> None:
        # During crossfade, restore the outgoing song without double play_count or
        # finish-nudging the barely-heard incoming track.
        if self.player.is_crossfading() and self._crossfade_outgoing_id is not None:
            outgoing = self._crossfade_outgoing_id
            settle_finish = self._outgoing_settle_finish
            self._clear_crossfade_credit()
            if settle_finish:
                self._listen_nudge(outgoing, skipped=False)
            if outgoing in self.session_queue:
                self.queue_index = self.session_queue.index(outgoing)
            self._play_restart(outgoing)
            return
        self._clear_crossfade_credit()
        self._expect_natural_advance = False
        if not self.session_queue:
            self._replenish_queue()
        if not self.session_queue:
            return
        self.queue_index = max(0, self.queue_index - 1)
        self.play_id(self.session_queue[self.queue_index])

    def _nearly_finished(self) -> None:
        # Arm crossfade / advance now; finish-credit the outgoing when the fade settles.
        self._expect_natural_advance = True
        self._advance_queue(skipped=False)

    def _crossfade_settled(self, natural: bool) -> None:
        # Finish-nudge on natural settle *and* pause/seek abort of an end-of-track fade.
        # `natural` is False when pause/seek/stop forced an immediate settle.
        _ = natural
        if self._outgoing_settle_finish and self._crossfade_outgoing_id is not None:
            self._listen_nudge(self._crossfade_outgoing_id, skipped=False)
        self._crossfade_outgoing_id = None
        self._outgoing_settle_finish = False
        credit = self._pending_play_credit
        self._pending_play_credit = None
        if (
            credit is not None
            and self.player.current is not None
            and credit == self.player.current.id
        ):
            self._commit_play(credit)

    def _track_finished_hard(self) -> None:
        # Short tracks (no nearly-finished arm): nudge + advance together.
        self._clear_crossfade_credit()
        self._expect_natural_advance = False
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
            self._replenish_queue(avoid_id=current_id)
            self.queue_index = 0
        if not self.session_queue:
            self._expect_natural_advance = False
            self.player.release_advance_lock()
            self._set_status("Context queue is empty — move the lens or add more music.")
            return
        self.queue_index = min(max(0, self.queue_index), len(self.session_queue) - 1)
        next_id = self.session_queue[self.queue_index]
        # Tiny libraries: never hard-cut restart the track that just ended.
        if not skipped and current_id is not None and next_id == current_id:
            self._expect_natural_advance = False
            self.player.release_advance_lock()
            self._set_status("Only one playable track in range — waiting.")
            return
        self.play_id(next_id)

    def _replenish_queue(self, *, avoid_id: int | None = None) -> None:
        """Build a fresh context queue from lens, time of day, and matrix lists."""
        ctx = self.current_context()
        self.band_chip.setText(ctx.band_label)
        # Skip ghost rows whose files are gone so the queue cannot refill with them.
        tracks = self._playable_tracks()
        current_id = self.player.current.id if self.player.current else None
        avoid = avoid_id if avoid_id is not None else current_id
        exclude = set(self.played_history[-24:])
        hard = {avoid} if avoid is not None else set()
        self.plan = build_plan(
            tracks, ctx, self.explicit, exclude_ids=exclude, hard_exclude_ids=hard
        )
        self.map.set_tracks(self.plan.ranked, current_id)
        self.matrix.set_plan(self.plan.by_quadrant)
        order = list(self.plan.order)
        if avoid is not None:
            filtered = [tid for tid in order if tid != avoid]
            if filtered:
                order = filtered
            elif len(tracks) > 1:
                order = [t.id for t in tracks if t.id != avoid][:18]
            else:
                # Single-track library: do not loop the same song via hard-cut.
                order = []
        self.ephemeral = {tid for tid in self.ephemeral if tid in order}
        self.session_queue = order
        self._fill_queue()
        self._set_status(
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
        # Once hard-cut media actually advances, keep the play credit on later errors.
        if (
            self._last_hard_play_credit is not None
            and pos >= 500
            and self.player.current is not None
            and self.player.current.id == self._last_hard_play_credit
        ):
            self._last_hard_play_credit = None
        self.transport.set_progress(pos, self._duration)

    def _dur(self, dur: int) -> None:
        self._duration = dur
        self.transport.set_progress(self.player.backend.position(), dur)

    def closeEvent(self, event) -> None:
        self._closing = True
        self._clear_crossfade_credit()
        self._expect_natural_advance = False
        # Abort kills ffmpeg; disconnect UI slots before wait so a timeout cannot UAF.
        analyze_done = self._stop_analyze(wait_ms=20000)
        scan_done = self._cleanup_scan_thread(wait_ms=10000)
        # Never close SQLite under a live worker (timed-out / lingering path).
        if analyze_done and scan_done and not self._lingering_workers:
            self.library.close()
        else:
            self._close_library_when_idle = True
        super().closeEvent(event)
