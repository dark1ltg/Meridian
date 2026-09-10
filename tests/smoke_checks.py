"""Shared smoke checks used by pytest and scripts/smoke_test.py."""

from __future__ import annotations

from pathlib import Path

from meridian import __version__
from meridian.features import analyze_audio, mood_confidence
from meridian.library import Library


def check_version() -> None:
    parts = __version__.split(".")
    assert len(parts) >= 2, f"unexpected version: {__version__!r}"
    assert all(p.isdigit() for p in parts[:3] if p), f"unexpected version: {__version__!r}"


def check_confidence() -> None:
    c, note = mood_confidence(tag_key="metal", pcm_ok=True, bpm_ok=True)
    assert "tag:metal" in note and "PCM" in note and c > 0.7

    c2, n2 = mood_confidence(tag_key="metal", pcm_ok=True, bpm_conflict=True)
    assert "BPM conflict" in n2 and c2 < c

    c3, n3 = mood_confidence(pcm_ok=True, pcm_unstable=True)
    c4, _ = mood_confidence(pcm_ok=True, pcm_unstable=False)
    assert "PCM weak" in n3 and c3 < c4

    result = analyze_audio("/nonexistent/x.flac", "metal", "t", "a", 140.0)
    assert result.confidence_note and result.confidence >= 0


def _seed_library(lib: Library, n: int = 16) -> None:
    for i in range(n):
        lib.upsert_track(
            {
                "path": f"/m/{i}.mp3",
                "title": f"t{i}",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.2 + i * 0.04,
                "energy": 0.3 + (i % 5) * 0.1,
                "mood_confidence": 0.85 if i < 12 else 0.25,
                "confidence_note": "seed",
                "low_trust": 0 if i < 12 else 1,
                "added_at": 0,
                "mtime": 0,
                "analyzed": 1,
            }
        )


def check_library_moods(db_path: Path) -> None:
    lib = Library(db_path)
    try:
        _seed_library(lib)
        lib.set_mood(1, 0.99, 0.99, pinned=True)
        pin_v = lib.get(1).valence
        assert lib.get(1).pinned and lib.get(1).mood_confidence == 1.0

        # Rescan-style upsert must not strip pin confidence.
        lib.upsert_track(
            {
                "path": "/m/0.mp3",
                "title": "t0",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.1,
                "energy": 0.1,
                "mood_confidence": 0.2,
                "confidence_note": "pre-analyze",
                "low_trust": 1,
                "added_at": 999,
                "mtime": 1,
                "analyzed": 0,
            }
        )
        pinned = lib.get(1)
        assert abs(pinned.valence - pin_v) < 1e-9
        assert pinned.mood_confidence == 1.0
        assert pinned.confidence_note == "pinned"
        assert pinned.analyzed

        n_smooth = lib.smooth_album_moods()
        assert n_smooth >= 0
        assert any("album smooth" in (t.confidence_note or "") for t in lib.all_tracks())

        n_sc = lib.rescale_moods_by_percentile(min_group=8)
        assert abs(lib.get(1).valence - pin_v) < 1e-9, "pin moved by rescale"
        assert n_sc > 0
        assert any(
            "relative rescale" in (t.confidence_note or "")
            for t in lib.all_tracks()
            if not t.pinned
        )

        tid = next(t.id for t in lib.all_tracks() if not t.pinned)
        before = lib.get(tid).mood_confidence
        lib.nudge_mood_from_listen(tid, lens_x=0.9, lens_y=0.9, skipped=False)
        after = lib.get(tid)
        assert after.mood_confidence >= before - 1e-9
        assert "listen finish" in (after.confidence_note or "")

        lib.nudge_mood_from_listen(tid, lens_x=0.1, lens_y=0.1, skipped=True)
        assert "listen skip" in (lib.get(tid).confidence_note or "")

        assert lib.nudge_mood_from_listen(1, lens_x=0.1, lens_y=0.1, skipped=False) is False
        assert abs(lib.get(1).valence - pin_v) < 1e-9

        lib.set_analyzed_mood(
            1, 0.11, 0.22, 90.0, confidence=0.2, low_trust=True, confidence_note="overwrite?"
        )
        t1 = lib.get(1)
        assert abs(t1.valence - pin_v) < 1e-9 and t1.pinned and t1.mood_confidence == 1.0
        assert t1.bpm == 120.0  # pinned BPM must not be overwritten
    finally:
        lib.close()


def check_empty_scan_does_not_wipe(db_path: Path) -> None:
    from meridian.scanner import ScanWorker

    lib = Library(db_path)
    try:
        _seed_library(lib, n=4)
        assert len(lib.all_tracks()) == 4
        lib.add_folder("/nonexistent/meridian-empty-scan-guard")
        worker = ScanWorker(lib, force=False)
        added = worker._scan()
        assert added == 0
        assert len(lib.all_tracks()) == 4, "empty/missing folders must not wipe library"

        # Existing but empty folder must also keep prior rows (no delete_missing wipe).
        empty = db_path.parent / "empty-music-root"
        empty.mkdir(parents=True, exist_ok=True)
        lib.add_folder(str(empty))
        added = ScanWorker(lib, force=False)._scan()
        assert added == 0
        assert len(lib.all_tracks()) == 4, "empty existing folder must not wipe library"
    finally:
        lib.close()


def check_multi_root_empty_does_not_wipe(tmp_dir: Path) -> None:
    """One root with audio + one empty root must not prune tracks under the empty root."""
    from meridian.scanner import ScanWorker

    db_path = tmp_dir / "multi-root.sqlite"
    root_a = tmp_dir / "root-a"
    root_b = tmp_dir / "root-b"
    root_a.mkdir(parents=True)
    root_b.mkdir(parents=True)
    keep = root_a / "keep.mp3"
    keep.write_bytes(b"ID3")
    ghost = root_b / "ghost.mp3"

    lib = Library(db_path)
    try:
        lib.upsert_track(
            {
                "path": str(ghost),
                "title": "ghost",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.5,
                "energy": 0.5,
                "mood_confidence": 0.5,
                "confidence_note": "seed",
                "low_trust": 0,
                "added_at": 0,
                "mtime": 0,
                "analyzed": 1,
            }
        )
        lib.add_folder(str(root_a))
        lib.add_folder(str(root_b))
        ScanWorker(lib, force=False)._scan()
        paths = {t.path for t in lib.all_tracks()}
        assert str(keep) in paths, "audio under a live root must still be indexed"
        assert str(ghost) in paths, (
            "empty sibling root must not wipe DB tracks under that root"
        )
    finally:
        lib.close()


def check_sparse_mount_does_not_wipe(tmp_dir: Path) -> None:
    """One leftover file on a near-empty mount must not prune the rest of that root."""
    from meridian.scanner import ScanWorker

    db_path = tmp_dir / "sparse.sqlite"
    root = tmp_dir / "sparse-root"
    root.mkdir(parents=True)
    leftover = root / "leftover.mp3"
    leftover.write_bytes(b"ID3")

    lib = Library(db_path)
    try:
        for i in range(6):
            lib.upsert_track(
                {
                    "path": str(root / f"gone{i}.mp3"),
                    "title": f"gone{i}",
                    "artist": "Band",
                    "albumartist": "Band",
                    "album": "LP",
                    "genre": "Metal",
                    "duration_ms": 1,
                    "year": None,
                    "bpm": 120,
                    "valence": 0.5,
                    "energy": 0.5,
                    "mood_confidence": 0.5,
                    "confidence_note": "seed",
                    "low_trust": 0,
                    "added_at": 0,
                    "mtime": 0,
                    "analyzed": 1,
                }
            )
        lib.add_folder(str(root))
        assert lib.count_tracks_under(root) == 6
        ScanWorker(lib, force=False)._scan()
        paths = {t.path for t in lib.all_tracks()}
        for i in range(6):
            assert str(root / f"gone{i}.mp3") in paths, (
                "sparse/wrong mount must not mass-prune known tracks"
            )
        assert str(leftover) in paths
    finally:
        lib.close()


def check_playback_error_auto_skips() -> None:
    """Corrupt/unsupported media must skip, denylist, and undo hard-cut play credit."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from meridian.ui.main_window import MainWindow

    w = MainWindow.__new__(MainWindow)
    w._closing = False
    w._handling_playback_error = False
    w._crossfade_outgoing_id = None
    w._outgoing_settle_finish = False
    w._expect_natural_advance = False
    w._pending_play_credit = None
    w._last_hard_play_credit = 7
    w.played_history = [7]
    calls: list[tuple] = []
    w._set_status = lambda m: calls.append(("status", m))  # type: ignore[method-assign]
    w._clear_crossfade_credit = lambda: None  # type: ignore[method-assign]
    w._listen_nudge = lambda *_a, **_k: None  # type: ignore[method-assign]
    w._skip_unplayable = lambda tid: 42  # type: ignore[method-assign]
    w.play_id = lambda tid: calls.append(("play", tid))  # type: ignore[method-assign]
    w.library = MagicMock()
    w.player = MagicMock()
    w.player.current = SimpleNamespace(id=7)
    w.player.is_crossfading.return_value = False

    MainWindow._playback_error(w, "ResourceError: Unsupported media")
    assert ("play", 42) in calls
    assert any(c[0] == "status" and "ResourceError" in c[1] for c in calls)
    w.library.mark_playback_failed.assert_called_with(7)
    w.library.unrecord_play.assert_called_with(7)
    assert w.played_history == []
    assert w._last_hard_play_credit is None
    w.player.stop.assert_called()
    w.player.release_advance_lock.assert_called()


def check_player_ignores_outgoing_errors() -> None:
    """During crossfade, only the active (incoming) deck may emit error_occurred."""
    from unittest.mock import patch

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from meridian.player import Player

    p = Player()
    seen: list[str] = []
    p.error_occurred.connect(lambda m: seen.append(m))
    # Simulate crossfade: active is incoming deck 1; deck 0 is outgoing.
    p._crossfading = True
    p._active = 1
    p._on_error(0)
    assert seen == [], "outgoing deck errors must be ignored during crossfade"
    with patch.object(p._decks[1].player, "errorString", return_value="Incoming failed"):
        p._on_error(1)
    assert seen == ["Incoming failed"]


def check_nearly_finished_duration_guards() -> None:
    """Provisional short durations must not arm crossfade auto-advance."""
    from PySide6.QtWidgets import QApplication
    from unittest.mock import MagicMock

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from meridian.player import CROSSFADE_MS, Player

    p = Player()
    armed: list[bool] = []
    p.track_nearly_finished.connect(lambda: armed.append(True))
    p._active = 0
    p._crossfading = False
    p._advance_emitted = False

    backend = MagicMock()
    p._decks[0].player = backend  # type: ignore[index]

    # Underestimated VBR duration early in the track — must not arm.
    backend.duration.return_value = 5000
    p._on_position(0, 4000)
    assert armed == [] and not p._advance_emitted

    # Long track but still in the first 10s — must not arm.
    backend.duration.return_value = 180_000
    p._on_position(0, 8000)
    assert armed == [] and not p._advance_emitted

    # Past 10s with remaining inside the fade window — arm.
    fade = p._fade_ms(180_000)
    assert fade <= CROSSFADE_MS
    p._on_position(0, 180_000 - fade)
    assert armed == [True] and p._advance_emitted


def check_incoming_end_ignores_spurious_eom() -> None:
    """Early EndOfMedia on a long incoming track must not count as finished."""
    from PySide6.QtWidgets import QApplication
    from unittest.mock import MagicMock

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from meridian.player import CROSSFADE_MS, Player

    p = Player()
    backend = MagicMock()
    p._decks[0].player = backend  # type: ignore[index]
    p._active = 0

    backend.position.return_value = 0
    backend.duration.return_value = 180_000
    assert p._incoming_end_is_real() is False

    backend.position.return_value = 800
    assert p._incoming_end_is_real() is True

    backend.position.return_value = 0
    backend.duration.return_value = CROSSFADE_MS
    assert p._incoming_end_is_real() is True


def check_decode_abort_helpers() -> None:
    from meridian.features import (
        clear_decode_abort,
        decode_abort_requested,
        request_decode_abort,
    )

    clear_decode_abort()
    assert decode_abort_requested() is False
    request_decode_abort()
    assert decode_abort_requested() is True
    clear_decode_abort()
    assert decode_abort_requested() is False


def check_partial_and_symlink_scan(tmp_dir: Path) -> None:
    from meridian.scanner import ScanWorker

    db_path = tmp_dir / "partial.sqlite"
    music = tmp_dir / "music"
    visible = music / "ok"
    blocked = music / "blocked"
    visible.mkdir(parents=True)
    blocked.mkdir(parents=True)
    (visible / "keep.mp3").write_bytes(b"ID3")
    (blocked / "hidden.mp3").write_bytes(b"ID3")

    outside = tmp_dir / "outside"
    outside.mkdir()
    (outside / "leak.mp3").write_bytes(b"ID3")
    leak_link = visible / "leak-link.mp3"
    leak_link.symlink_to(outside / "leak.mp3")

    lib = Library(db_path)
    try:
        # Seed a track under the blocked subtree so a partial walk must not delete it.
        lib.upsert_track(
            {
                "path": str(blocked / "hidden.mp3"),
                "title": "hidden",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.5,
                "energy": 0.5,
                "mood_confidence": 0.5,
                "confidence_note": "seed",
                "low_trust": 0,
                "added_at": 0,
                "mtime": 0,
                "analyzed": 1,
            }
        )
        lib.add_folder(str(music))
        blocked.chmod(0o000)
        try:
            ScanWorker(lib, force=False)._scan()
        finally:
            blocked.chmod(0o755)
        paths = {t.path for t in lib.all_tracks()}
        assert str(blocked / "hidden.mp3") in paths, "partial/unreadable tree must not prune"
        assert str(leak_link) not in paths, "out-of-root file symlink must be ignored"
        # only_under: tracks outside pruned roots stay
        other = tmp_dir / "other-lib" / "song.mp3"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"ID3")
        lib.upsert_track(
            {
                "path": str(other),
                "title": "other",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.5,
                "energy": 0.5,
                "mood_confidence": 0.5,
                "confidence_note": "seed",
                "low_trust": 0,
                "added_at": 0,
                "mtime": 0,
                "analyzed": 1,
            }
        )
        lib.delete_missing([str(visible / "keep.mp3")], only_under=[music.resolve()])
        paths = {t.path for t in lib.all_tracks()}
        assert str(other) in paths, "delete_missing must not touch paths outside only_under"
    finally:
        try:
            blocked.chmod(0o755)
        except OSError:
            pass
        lib.close()


def check_analyze_failed_marks_done(db_path: Path) -> None:
    lib = Library(db_path)
    try:
        _seed_library(lib, n=2)
        tid = lib.all_tracks()[0].id
        lib.conn.execute("UPDATE tracks SET analyzed = 0 WHERE id = ?", (tid,))
        lib.conn.commit()
        lib.mark_analyze_failed(tid)
        t = lib.get(tid)
        assert t is not None and t.analyzed
        assert "analyze failed" in (t.confidence_note or "")
        assert tid not in lib.unanalyzed_ids()

        # Even if the DB row is forced back to pending, process denylist blocks the poison loop.
        lib.conn.execute("UPDATE tracks SET analyzed = 0 WHERE id = ?", (tid,))
        lib.conn.commit()
        assert tid not in lib.unanalyzed_ids()

        # Proper upsert reset (scan re-queue) clears the sticky denylist entry.
        row = lib.get(tid)
        lib.upsert_track(
            {
                "path": row.path,
                "title": row.title,
                "artist": row.artist,
                "albumartist": row.albumartist,
                "album": row.album,
                "genre": row.genre,
                "duration_ms": row.duration_ms,
                "year": row.year,
                "bpm": row.bpm,
                "valence": row.valence,
                "energy": row.energy,
                "mood_confidence": row.mood_confidence,
                "confidence_note": row.confidence_note or "",
                "low_trust": int(row.low_trust),
                "analyzed": 0,
                "mtime": row.mtime,
                "added_at": row.added_at,
            }
        )
        assert tid not in lib._analyze_denylist
        assert tid in lib.unanalyzed_ids()
    finally:
        lib.close()


def check_build_plan_hard_exclude() -> None:
    from meridian.context import Mode, make_context
    from meridian.library import Track
    from meridian.queue_engine import build_plan, mix_counts

    def t(i: int, *, artist: str = "Band", album: str = "LP", plays: int = 0, skips: int = 0) -> Track:
        return Track(
            id=i,
            path=f"/m/{i}.mp3",
            title=f"t{i}",
            artist=artist,
            album=album,
            albumartist=artist,
            genre="Metal",
            duration_ms=1000,
            year=None,
            bpm=120.0,
            valence=0.5,
            energy=0.5,
            mood_confidence=0.8,
            confidence_note="seed",
            low_trust=False,
            pinned=False,
            loved=False,
            play_count=plays,
            skip_count=skips,
            last_played=None,
            added_at=0.0,
            mtime=0.0,
            analyzed=True,
        )

    tracks = [t(1), t(2), t(3)]
    ctx = make_context(Mode.WANDER, 0.5, 0.5, 0.25, 0.0)
    plan = build_plan(tracks, ctx, [], exclude_ids={1}, hard_exclude_ids={1})
    assert 1 not in plan.order, "hard_exclude must keep the just-finished track out"
    solo = build_plan([t(1)], ctx, [], hard_exclude_ids={1})
    assert solo.order == [], "single-track hard_exclude must not refill with itself"

    # Artist anti-repeat when alternatives exist.
    mixed = [t(i, artist=f"A{i % 5}", album=f"Alb{i}") for i in range(1, 21)]
    plan2 = build_plan(mixed, ctx, [], length=10)
    from collections import Counter

    artist_counts = Counter(
        next(x.artist for x in mixed if x.id == tid) for tid in plan2.order
    )
    assert all(n <= 2 for n in artist_counts.values()), artist_counts

    # Mode mix + skip pressure reshape take sizes.
    focus = mix_counts(make_context(Mode.FOCUS, 0.5, 0.5, 0.25, 0.0))
    charge = mix_counts(make_context(Mode.CHARGE, 0.5, 0.5, 0.25, 0.0))
    pressured = mix_counts(make_context(Mode.WANDER, 0.5, 0.5, 0.25, 1.0))
    calm = mix_counts(make_context(Mode.WANDER, 0.5, 0.5, 0.25, 0.0))
    assert focus[1] >= focus[3]  # NOW >= FILL in Focus
    assert charge[1] >= calm[1]  # Charge leans NOW
    assert pressured[3] > calm[3]  # skip pressure grows FILL
    assert pressured[1] < calm[1]  # and shrinks NOW

    # Finish/skip importance: finished tracks outrank often-skipped peers at same mood.
    from meridian.queue_engine import Quadrant, classify

    finished = t(1, plays=8, skips=1)
    skipped = t(2, plays=1, skips=8)
    ranked = classify([finished, skipped], ctx, set())
    by_id = {r.track.id: r for r in ranked}
    assert by_id[1].importance > by_id[2].importance

    # Dense same-artist NOW/DEEP/FILL must not gap-fill into a SHELF-heavy queue.
    def t_mood(
        i: int,
        *,
        artist: str,
        album: str,
        valence: float,
        energy: float,
    ) -> Track:
        return Track(
            id=i,
            path=f"/m/{i}.mp3",
            title=f"t{i}",
            artist=artist,
            album=album,
            albumartist=artist,
            genre="Metal",
            duration_ms=1000,
            year=None,
            bpm=120.0,
            valence=valence,
            energy=energy,
            mood_confidence=0.8,
            confidence_note="seed",
            low_trust=False,
            pinned=False,
            loved=False,
            play_count=0,
            skip_count=0,
            last_played=None,
            added_at=0.0,
            mtime=0.0,
            analyzed=True,
        )

    near = [
        t_mood(i, artist="ClusterA" if i % 2 == 0 else "ClusterB", album=f"Alb{i % 3}", valence=0.5, energy=0.5)
        for i in range(1, 25)
    ]
    far = [
        t_mood(100 + i, artist=f"Far{i}", album=f"F{i}", valence=0.05, energy=0.95)
        for i in range(40)
    ]
    crowded = build_plan(near + far, ctx, [], length=18)
    shelf_ids = {r.track.id for r in crowded.by_quadrant.get(Quadrant.SHELF, [])}
    shelf_in_q = sum(1 for tid in crowded.order if tid in shelf_ids)
    near_ids = {tr.id for tr in near}
    near_in_q = sum(1 for tid in crowded.order if tid in near_ids)
    assert near_in_q >= 12, (near_in_q, crowded.order, shelf_in_q)
    assert shelf_in_q <= 5, (shelf_in_q, crowded.order)


def check_renewal_queue_scoring() -> None:
    """Renew Queue soft demotion — not skips; small pools may reuse."""
    from collections import Counter

    from meridian.context import Mode, make_context
    from meridian.library import Track
    from meridian.queue_engine import (
        RenewalContext,
        build_plan,
        classify,
        preferred_pool_size,
        renewal_penalty_ids,
        renewal_penalty_strength,
    )

    def t(
        i: int,
        *,
        artist: str | None = None,
        album: str | None = None,
        valence: float = 0.5,
        energy: float = 0.5,
        loved: bool = False,
        pinned: bool = False,
        plays: int = 0,
        skips: int = 0,
    ) -> Track:
        return Track(
            id=i,
            path=f"/m/{i}.mp3",
            title=f"t{i}",
            artist=artist or f"Artist{i}",
            album=album or f"Album{i}",
            albumartist=artist or f"Artist{i}",
            genre="Metal",
            duration_ms=1000,
            year=None,
            bpm=120.0,
            valence=valence,
            energy=energy,
            mood_confidence=0.8,
            confidence_note="seed",
            low_trust=False,
            pinned=pinned,
            loved=loved,
            play_count=plays,
            skip_count=skips,
            last_played=None,
            added_at=0.0,
            mtime=0.0,
            analyzed=True,
        )

    ctx = make_context(Mode.WANDER, 0.5, 0.5, 0.28, 0.0)

    # Normal path unchanged: renewal=None matches no-kwargs.
    base_tracks = [
        t(i, valence=0.48 + (i % 7) * 0.01, energy=0.47 + (i % 5) * 0.01)
        for i in range(1, 41)
    ]
    normal = build_plan(base_tracks, ctx, [])
    also_normal = build_plan(base_tracks, ctx, [], renewal=None)
    assert normal.order == also_normal.order

    # Penalty strength: tiny pool off; small lower; streak bounded.
    assert renewal_penalty_strength(8, 0) == 0.0
    assert renewal_penalty_strength(18, 0) == 0.10
    assert renewal_penalty_strength(40, 0) == 0.15
    assert renewal_penalty_strength(40, 3) == 0.27
    assert renewal_penalty_strength(40, 99) == 0.27

    # Penalty ids omit heard / loved / pinned / explicit / exempt.
    tracks_meta = [
        t(1),
        t(2, loved=True),
        t(3, pinned=True),
        t(4),
        t(5),
    ]
    renewal = RenewalContext(
        prior_queue_ids=frozenset({1, 2, 3, 4, 5}),
        renew_streak=0,
        exempt_ids=frozenset({5}),
        heard_ids=frozenset({1}),
    )
    penalized = renewal_penalty_ids(renewal, tracks_meta, explicit_ids={4})
    assert penalized == set()

    # Large pool: renew prefers tracks outside the prior queue when peers are close.
    cluster = [
        t(i, artist=f"A{i}", album=f"L{i}", valence=0.50, energy=0.50)
        for i in range(1, 36)
    ]
    first = build_plan(cluster, ctx, [], length=18)
    assert len(first.order) == 18
    prior = frozenset(first.order)
    renewed = build_plan(
        cluster,
        ctx,
        [],
        length=18,
        renewal=RenewalContext(prior_queue_ids=prior, renew_streak=0),
    )
    assert preferred_pool_size(renewed.ranked) >= 12
    overlap = len(prior.intersection(renewed.order))
    assert overlap < len(first.order), (overlap, first.order[:5], renewed.order[:5])

    # Soft, not absolute: a clearly best prior track can still be selected.
    best = t(1, artist="Best", album="Solo", valence=0.50, energy=0.50, plays=12)
    weaker = [
        t(i, artist=f"W{i}", album=f"W{i}", valence=0.62, energy=0.62)
        for i in range(2, 30)
    ]
    soft = build_plan(
        [best] + weaker,
        ctx,
        [],
        length=12,
        renewal=RenewalContext(prior_queue_ids=frozenset({1}), renew_streak=0),
    )
    assert 1 in soft.order

    # Loved in prior queue is not demoted away when it fits.
    loved = t(1, artist="Love", album="L", valence=0.50, energy=0.50, loved=True)
    others = [
        t(i, artist=f"O{i}", album=f"O{i}", valence=0.51, energy=0.51)
        for i in range(2, 30)
    ]
    love_plan = build_plan(
        [loved] + others,
        ctx,
        [],
        length=12,
        renewal=RenewalContext(prior_queue_ids=frozenset({1}), renew_streak=0),
    )
    assert 1 in love_plan.order

    # Tiny pool: penalty off — reuse is required / allowed.
    tiny = [t(i, valence=0.5, energy=0.5) for i in range(1, 9)]
    tiny_first = build_plan(tiny, ctx, [], length=8)
    tiny_renew = build_plan(
        tiny,
        ctx,
        [],
        length=8,
        renewal=RenewalContext(
            prior_queue_ids=frozenset(tiny_first.order),
            renew_streak=2,
        ),
    )
    assert len(tiny_renew.order) == len(tiny_first.order)
    assert set(tiny_renew.order) == set(tiny_first.order)

    # Multiple renews stay in-context (high fit), not a random walk to far moods.
    big = [
        t(i, artist=f"B{i % 9}", album=f"Alb{i}", valence=0.50, energy=0.50)
        for i in range(1, 50)
    ]
    far_away = [
        t(200 + i, artist=f"Z{i}", album=f"Z{i}", valence=0.05, energy=0.95)
        for i in range(1, 10)
    ]
    library = big + far_away
    q0 = build_plan(library, ctx, [], length=18)
    q1 = build_plan(
        library,
        ctx,
        [],
        length=18,
        renewal=RenewalContext(prior_queue_ids=frozenset(q0.order), renew_streak=0),
    )
    q2 = build_plan(
        library,
        ctx,
        [],
        length=18,
        renewal=RenewalContext(prior_queue_ids=frozenset(q1.order), renew_streak=1),
    )
    q3 = build_plan(
        library,
        ctx,
        [],
        length=18,
        renewal=RenewalContext(prior_queue_ids=frozenset(q2.order), renew_streak=2),
    )
    far_ids = {200 + i for i in range(1, 10)}
    for plan in (q1, q2, q3):
        assert sum(1 for tid in plan.order if tid in far_ids) <= 2, plan.order

    artists = Counter(
        next(x.artist for x in library if x.id == tid) for tid in q1.order
    )
    assert all(n <= 2 for n in artists.values()), artists

    # Renewal must not mutate listening counters (queue-selection only).
    before = [(tr.id, tr.skip_count, tr.play_count) for tr in cluster]
    build_plan(
        cluster,
        ctx,
        [],
        renewal=RenewalContext(prior_queue_ids=frozenset(range(1, 19)), renew_streak=1),
    )
    after = [(tr.id, tr.skip_count, tr.play_count) for tr in cluster]
    assert before == after

    # Actual skip history still shapes importance when present.
    finished = t(1, plays=8, skips=1, valence=0.5, energy=0.5)
    skipped = t(2, plays=1, skips=8, valence=0.5, energy=0.5)
    ranked = classify([finished, skipped], ctx, set())
    by_id = {r.track.id: r for r in ranked}
    assert by_id[1].importance > by_id[2].importance


def check_mood_map_helpers() -> None:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPointF

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from meridian.ui.mood_map import (
        HIT_RADIUS_SKY,
        HIT_RADIUS_SKY_GRAB,
        LIVE_STARS_ZOOM,
        MoodMap,
    )
    from meridian.context import LENS_RADIUS_DEFAULT
    from meridian.queue_engine import Quadrant
    from types import SimpleNamespace

    m = MoodMap()
    assert hasattr(m, "_ensure_interactive_star")
    assert hasattr(m, "_sky_hold_id")
    assert hasattr(m, "_drag_locked_ids")
    assert hasattr(m, "set_radius_scale")
    assert hasattr(m, "_field_signature")
    assert hasattr(m, "_track_star_from_item")
    assert LIVE_STARS_ZOOM == 2.4
    assert HIT_RADIUS_SKY >= 10
    assert HIT_RADIUS_SKY_GRAB < HIT_RADIUS_SKY
    assert m.lens.zValue() < 7, "lens must sit under live stars for hit-testing"
    assert m._ensure_interactive_star(999) is None

    # Lens ellipse matches mood radius on map axes (and mode scale).
    m.set_radius_scale(1.0)
    m.set_lens(0.5, 0.5, LENS_RADIUS_DEFAULT)
    rx = m.lens.rect().width() / 2
    ry = m.lens.rect().height() / 2
    assert abs(rx - LENS_RADIUS_DEFAULT * 720) < 0.5
    assert abs(ry - LENS_RADIUS_DEFAULT * 524) < 0.5
    m.set_radius_scale(0.78)
    assert abs(m.lens.rect().width() / 2 - LENS_RADIUS_DEFAULT * 0.78 * 720) < 0.5

    # Mid-drag set_tracks must not wipe the held star position.
    track = SimpleNamespace(
        id=1,
        valence=0.2,
        energy=0.8,
        label="T",
        loved=False,
        pinned=False,
        mood_confidence=0.9,
        confidence_note="",
    )
    ranked = SimpleNamespace(track=track, quadrant=Quadrant.NOW, fit=1.0, importance=1.0)
    m.set_tracks([ranked], None)
    star = m._ensure_interactive_star(1)
    assert star is not None
    drag = QPointF(600.0, 250.0)
    star.setPos(drag)
    m._positions[1] = QPointF(drag)
    m._sky_hold_id = 1
    m.set_tracks([ranked], None)
    assert abs(m._stars[1].pos().x() - 600.0) < 0.5
    assert abs(m._positions[1].x() - 600.0) < 0.5

    # Sky candidate (press before drag) must also survive set_tracks.
    m._sky_hold_id = None
    m._sky_candidate_id = 1
    star.setPos(QPointF(610.0, 260.0))
    m._positions[1] = QPointF(610.0, 260.0)
    assert 1 in m._drag_locked_ids()
    m.set_tracks([ranked], None)
    assert abs(m._positions[1].x() - 610.0) < 0.5
    m._sky_candidate_id = None

    # Identical set_tracks must not allocate a new starfield pixmap.
    m.set_tracks([ranked], None)  # settle positions from mood coords
    pix0 = m._field.pixmap()
    key0 = pix0.cacheKey()
    m.set_tracks([ranked], None)
    assert m._field.pixmap().cacheKey() == key0

    # Backdrop rebuild must not leak chrome items.
    n0 = len(m._sky_chrome)
    m._draw_backdrop()
    assert len(m._sky_chrome) == n0


def run_all_smoke_checks(tmp_dir: Path) -> None:
    """Run every smoke check (used by scripts/smoke_test.py)."""
    check_version()
    check_confidence()
    check_library_moods(tmp_dir / "smoke.sqlite")
    check_empty_scan_does_not_wipe(tmp_dir / "wipe.sqlite")
    check_multi_root_empty_does_not_wipe(tmp_dir / "multi-root")
    check_sparse_mount_does_not_wipe(tmp_dir / "sparse")
    check_playback_error_auto_skips()
    check_player_ignores_outgoing_errors()
    check_nearly_finished_duration_guards()
    check_incoming_end_ignores_spurious_eom()
    check_decode_abort_helpers()
    check_partial_and_symlink_scan(tmp_dir / "scan-guards")
    check_analyze_failed_marks_done(tmp_dir / "fail.sqlite")
    check_build_plan_hard_exclude()
    check_renewal_queue_scoring()
    check_mood_map_helpers()
