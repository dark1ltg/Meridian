from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QStandardPaths


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS folders (
    path TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT,
    artist TEXT,
    album TEXT,
    albumartist TEXT,
    genre TEXT,
    duration_ms INTEGER DEFAULT 0,
    year INTEGER,
    bpm REAL,
    valence REAL NOT NULL DEFAULT 0.5,
    energy REAL NOT NULL DEFAULT 0.5,
    mood_confidence REAL NOT NULL DEFAULT 0.5,
    confidence_note TEXT,
    low_trust INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    loved INTEGER NOT NULL DEFAULT 0,
    play_count INTEGER NOT NULL DEFAULT 0,
    skip_count INTEGER NOT NULL DEFAULT 0,
    last_played REAL,
    added_at REAL,
    mtime REAL,
    analyzed INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tracks_mood ON tracks(valence, energy);
"""


@dataclass(slots=True)
class Track:
    id: int
    path: str
    title: str
    artist: str
    album: str
    albumartist: str
    genre: str
    duration_ms: int
    year: int | None
    bpm: float | None
    valence: float
    energy: float
    mood_confidence: float
    confidence_note: str
    low_trust: bool
    pinned: bool
    loved: bool
    play_count: int
    skip_count: int
    last_played: float | None
    added_at: float | None
    mtime: float | None
    analyzed: bool

    @property
    def label(self) -> str:
        artist = self.artist or self.albumartist or "Unknown"
        title = self.title or Path(self.path).stem
        return f"{artist} — {title}"

    @property
    def short_title(self) -> str:
        return self.title or Path(self.path).stem


def data_dir() -> Path:
    root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    root.mkdir(parents=True, exist_ok=True)
    return root


class Library:
    def __init__(self, db_path: Path | None = None) -> None:
        self.path = db_path or (data_dir() / "library.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        with self.lock:
            cols = {str(r[1]) for r in self.conn.execute("PRAGMA table_info(tracks)")}
            if "low_trust" not in cols:
                self.conn.execute(
                    "ALTER TABLE tracks ADD COLUMN low_trust INTEGER NOT NULL DEFAULT 0"
                )
            if "albumartist" not in cols:
                self.conn.execute("ALTER TABLE tracks ADD COLUMN albumartist TEXT")
            if "mood_confidence" not in cols:
                self.conn.execute(
                    "ALTER TABLE tracks ADD COLUMN mood_confidence REAL NOT NULL DEFAULT 0.5"
                )
                # Approximate from existing binary flag until the next analyze.
                self.conn.execute(
                    "UPDATE tracks SET mood_confidence = CASE WHEN low_trust = 1 THEN 0.30 ELSE 0.80 END"
                )
            if "confidence_note" not in cols:
                self.conn.execute("ALTER TABLE tracks ADD COLUMN confidence_note TEXT")
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def folders(self) -> list[str]:
        with self.lock:
            rows = self.conn.execute("SELECT path FROM folders ORDER BY path").fetchall()
        return [r["path"] for r in rows]

    def add_folder(self, path: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR IGNORE INTO folders(path) VALUES (?)", (path,))
            self.conn.commit()

    def remove_folder(self, path: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM folders WHERE path = ?", (path,))
            self.conn.commit()

    def upsert_track(self, values: dict) -> int:
        path = values["path"]
        with self.lock:
            existing = self.conn.execute(
                "SELECT id, pinned FROM tracks WHERE path = ?", (path,)
            ).fetchone()
            if existing:
                payload = dict(values)
                # Preserve original import time on updates.
                payload.pop("added_at", None)
                if int(existing["pinned"] or 0):
                    # Pins keep mood + trust metadata; analyze still protects coords.
                    for key in (
                        "valence",
                        "energy",
                        "mood_confidence",
                        "low_trust",
                        "confidence_note",
                        "analyzed",
                    ):
                        payload.pop(key, None)
                fields = [k for k in payload if k != "path"]
                if fields:
                    assignments = ", ".join(f"{k} = ?" for k in fields)
                    params = [payload[k] for k in fields] + [path]
                    self.conn.execute(f"UPDATE tracks SET {assignments} WHERE path = ?", params)
                self.conn.commit()
                return int(existing["id"])
            cols = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            cur = self.conn.execute(
                f"INSERT INTO tracks ({cols}) VALUES ({placeholders})",
                list(values.values()),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def set_mood(self, track_id: int, valence: float, energy: float, pinned: bool = True) -> None:
        with self.lock:
            # User pin ⇒ full confidence; clear low-trust dimming.
            self.conn.execute(
                """
                UPDATE tracks
                SET valence = ?, energy = ?, pinned = ?,
                    mood_confidence = 1.0, low_trust = 0, confidence_note = 'pinned'
                WHERE id = ?
                """,
                (valence, energy, int(pinned), track_id),
            )
            self.conn.commit()

    @staticmethod
    def _append_note(existing: str | None, addition: str) -> str:
        base = (existing or "").strip()
        add = addition.strip()
        if not add:
            return base
        if not base:
            return add
        if add in base:
            return base
        return f"{base} · {add}"

    def nudge_mood_from_listen(
        self,
        track_id: int,
        *,
        lens_x: float,
        lens_y: float,
        skipped: bool,
        amount: float = 0.014,
        max_step: float = 0.025,
    ) -> bool:
        """Offline personalization: tiny unpinned drift from skip vs finish under the lens."""
        from meridian.features import confidence_low_trust

        with self.lock:
            row = self.conn.execute(
                """
                SELECT valence, energy, pinned, mood_confidence, confidence_note
                FROM tracks WHERE id = ?
                """,
                (track_id,),
            ).fetchone()
            if not row or int(row["pinned"]):
                return False
            v = float(row["valence"])
            e = float(row["energy"])
            conf = float(row["mood_confidence"] if row["mood_confidence"] is not None else 0.5)
            dx = float(lens_x) - v
            dy = float(lens_y) - e
            if skipped:
                dx = -dx
                dy = -dy
            step = float(amount)
            dv = max(-max_step, min(max_step, step * dx))
            de = max(-max_step, min(max_step, step * dy))
            if abs(dv) < 1e-6 and abs(de) < 1e-6:
                # If already on the lens, push skips slightly toward higher energy variance.
                if skipped:
                    de = max_step * 0.35
                else:
                    return False
            nv = max(0.03, min(0.97, v + dv))
            ne = max(0.03, min(0.97, e + de))
            if skipped:
                nconf = max(0.12, conf - 0.04)
                note = self._append_note(row["confidence_note"], "listen skip")
            else:
                nconf = min(0.95, conf + 0.05)
                note = self._append_note(row["confidence_note"], "listen finish")
            self.conn.execute(
                """
                UPDATE tracks
                SET valence = ?, energy = ?, mood_confidence = ?, low_trust = ?, confidence_note = ?
                WHERE id = ? AND pinned = 0
                """,
                (nv, ne, nconf, int(confidence_low_trust(nconf)), note, track_id),
            )
            self.conn.commit()
            return True

    def set_analyzed_mood(
        self,
        track_id: int,
        valence: float,
        energy: float,
        bpm: float | None,
        *,
        confidence: float = 0.5,
        low_trust: bool = False,
        confidence_note: str = "",
    ) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE tracks
                SET valence = CASE WHEN pinned = 1 THEN valence ELSE ? END,
                    energy = CASE WHEN pinned = 1 THEN energy ELSE ? END,
                    bpm = ?,
                    mood_confidence = CASE WHEN pinned = 1 THEN mood_confidence ELSE ? END,
                    low_trust = CASE WHEN pinned = 1 THEN low_trust ELSE ? END,
                    confidence_note = CASE WHEN pinned = 1 THEN confidence_note ELSE ? END,
                    analyzed = 1
                WHERE id = ?
                """,
                (
                    valence,
                    energy,
                    bpm,
                    float(confidence),
                    int(low_trust),
                    confidence_note or "",
                    track_id,
                ),
            )
            self.conn.commit()

    def smooth_album_moods(self, max_shift: float = 0.08, blend: float = 0.30) -> int:
        """Gently pull unpinned tracks toward their album median mood (no ffmpeg).

        Groups by albumartist when present (VA/OST/classical-safe), else artist.
        """
        return self._smooth_group_moods(
            group_sql="""
                SELECT id, artist, albumartist, album, valence, energy, pinned,
                       low_trust, mood_confidence, confidence_note
                FROM tracks
                WHERE album IS NOT NULL AND TRIM(album) != ''
                  AND (
                    (albumartist IS NOT NULL AND TRIM(albumartist) != '')
                    OR (artist IS NOT NULL AND TRIM(artist) != '')
                  )
                """,
            key_fn=lambda row: (
                (
                    (lambda aa, ar: aa if aa and aa.lower() not in {"various artists", "various", "va"} else ar)(
                        str(row["albumartist"] or "").strip(),
                        str(row["artist"] or "").strip(),
                    )
                ).lower(),
                str(row["album"] or "").lower().strip(),
            ),
            min_group=4,
            max_shift=max_shift,
            blend=blend,
            note_tag="album smooth",
        )

    def smooth_artist_moods(self, max_shift: float = 0.06, blend: float = 0.22) -> int:
        """Gently pull unpinned tracks toward their artist median mood (no ffmpeg)."""
        return self._smooth_group_moods(
            group_sql="""
                SELECT id, artist, valence, energy, pinned,
                       low_trust, mood_confidence, confidence_note
                FROM tracks
                WHERE artist IS NOT NULL AND TRIM(artist) != ''
                """,
            key_fn=lambda row: str(row["artist"]).lower(),
            min_group=6,
            max_shift=max_shift,
            blend=blend,
            note_tag="artist smooth",
        )

    def _smooth_group_moods(
        self,
        *,
        group_sql: str,
        key_fn,
        min_group: int,
        max_shift: float,
        blend: float,
        note_tag: str = "group smooth",
    ) -> int:
        from statistics import median

        from meridian.features import confidence_low_trust

        with self.lock:
            rows = self.conn.execute(group_sql).fetchall()

        groups: dict = {}
        for row in rows:
            groups.setdefault(key_fn(row), []).append(row)

        # valence, energy, confidence, low_trust, note, id
        updates: list[tuple[float, float, float, int, str, int]] = []
        for items in groups.values():
            if len(items) < min_group:
                continue
            # Prefer high-trust median when available so low-trust tracks snap toward
            # confident neighbors; fall back to full-group median.
            trusted = [i for i in items if not int(i["low_trust"] or 0)]
            med_src = trusted if len(trusted) >= 2 else items
            med_v = float(median(float(i["valence"]) for i in med_src))
            med_e = float(median(float(i["energy"]) for i in med_src))
            for item in items:
                if int(item["pinned"]):
                    continue
                # Only nudge low-trust placements — keep confident stars put (#6).
                if not int(item["low_trust"] or 0):
                    continue
                v0 = float(item["valence"])
                e0 = float(item["energy"])
                v = (1.0 - blend) * v0 + blend * med_v
                e = (1.0 - blend) * e0 + blend * med_e
                v = v0 + max(-max_shift, min(max_shift, v - v0))
                e = e0 + max(-max_shift, min(max_shift, e - e0))
                v = max(0.03, min(0.97, v))
                e = max(0.03, min(0.97, e))
                if abs(v - v0) <= 1e-9 and abs(e - e0) <= 1e-9:
                    continue
                conf0 = float(item["mood_confidence"] if item["mood_confidence"] is not None else 0.3)
                # Snapping toward trusted neighbors raises confidence into mid band.
                conf = min(0.62, max(conf0, 0.42) + 0.12)
                note = self._append_note(item["confidence_note"] if "confidence_note" in item.keys() else "", note_tag)
                updates.append((v, e, conf, int(confidence_low_trust(conf)), note, int(item["id"])))

        if not updates:
            return 0
        with self.lock:
            self.conn.executemany(
                """
                UPDATE tracks
                SET valence = ?, energy = ?, mood_confidence = ?, low_trust = ?, confidence_note = ?
                WHERE id = ? AND pinned = 0
                """,
                updates,
            )
            self.conn.commit()
        return len(updates)

    def rescale_moods_by_percentile(self, min_group: int = 12) -> int:
        """P4: library/genre percentile rescale for relative placement (no ffmpeg).

        Pins are never moved. High-confidence stars get a tiny blend; low-confidence
        stars get a stronger pull so neighbors rank better inside the library.
        """
        from meridian.features import (
            CONFIDENCE_HIGH,
            CONFIDENCE_LOW,
            genre_match,
        )

        with self.lock:
            rows = self.conn.execute(
                """
                SELECT id, genre, valence, energy, pinned, mood_confidence, confidence_note
                FROM tracks
                """
            ).fetchall()

        if len(rows) < min_group:
            return 0

        groups: dict[str, list] = {}
        for row in rows:
            key = genre_match(row["genre"] or "") or "_global_"
            groups.setdefault(key, []).append(row)

        # Fold undersized genre buckets into the global pool for stable ranks.
        global_rows = list(groups.pop("_global_", []))
        for key, items in list(groups.items()):
            if len(items) < min_group:
                global_rows.extend(items)
                del groups[key]
        if len(global_rows) >= min_group:
            groups["_global_"] = global_rows

        updates: list[tuple[float, float, str, int]] = []
        for items in groups.values():
            n = len(items)
            if n < min_group:
                continue
            # Rank within group (average ranks for ties via sorted index).
            order_v = sorted(range(n), key=lambda i: float(items[i]["valence"]))
            order_e = sorted(range(n), key=lambda i: float(items[i]["energy"]))
            pct_v = [0.0] * n
            pct_e = [0.0] * n
            denom = max(n - 1, 1)
            for rank, idx in enumerate(order_v):
                pct_v[idx] = rank / denom
            for rank, idx in enumerate(order_e):
                pct_e[idx] = rank / denom

            for i, item in enumerate(items):
                if int(item["pinned"]):
                    continue
                conf = float(item["mood_confidence"] if item["mood_confidence"] is not None else 0.5)
                if conf >= CONFIDENCE_HIGH:
                    blend, max_shift = 0.08, 0.03
                elif conf >= CONFIDENCE_LOW:
                    blend, max_shift = 0.25, 0.07
                else:
                    blend, max_shift = 0.45, 0.12
                v0 = float(item["valence"])
                e0 = float(item["energy"])
                target_v = 0.10 + 0.80 * pct_v[i]
                target_e = 0.10 + 0.80 * pct_e[i]
                v = (1.0 - blend) * v0 + blend * target_v
                e = (1.0 - blend) * e0 + blend * target_e
                v = v0 + max(-max_shift, min(max_shift, v - v0))
                e = e0 + max(-max_shift, min(max_shift, e - e0))
                v = max(0.03, min(0.97, v))
                e = max(0.03, min(0.97, e))
                if abs(v - v0) < 1e-9 and abs(e - e0) < 1e-9:
                    continue
                note = self._append_note(
                    item["confidence_note"] if "confidence_note" in item.keys() else "",
                    "relative rescale",
                )
                updates.append((v, e, note, int(item["id"])))

        if not updates:
            return 0
        with self.lock:
            self.conn.executemany(
                """
                UPDATE tracks
                SET valence = ?, energy = ?, confidence_note = ?
                WHERE id = ? AND pinned = 0
                """,
                updates,
            )
            self.conn.commit()
        return len(updates)

    def toggle_loved(self, track_id: int) -> bool:
        with self.lock:
            row = self.conn.execute("SELECT loved FROM tracks WHERE id = ?", (track_id,)).fetchone()
            if not row:
                return False
            loved = 0 if row["loved"] else 1
            self.conn.execute("UPDATE tracks SET loved = ? WHERE id = ?", (loved, track_id))
            self.conn.commit()
            return bool(loved)

    def record_play(self, track_id: int, timestamp: float) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE tracks
                SET play_count = play_count + 1, last_played = ?
                WHERE id = ?
                """,
                (timestamp, track_id),
            )
            self.conn.commit()

    def record_skip(self, track_id: int) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE tracks SET skip_count = skip_count + 1 WHERE id = ?",
                (track_id,),
            )
            self.conn.commit()

    def delete_missing(self, existing_paths: Iterable[str]) -> None:
        keep = set(existing_paths)
        with self.lock:
            rows = self.conn.execute("SELECT id, path FROM tracks").fetchall()
            dead = [r["id"] for r in rows if r["path"] not in keep]
            if dead:
                self.conn.executemany("DELETE FROM tracks WHERE id = ?", [(i,) for i in dead])
                self.conn.commit()

    def all_tracks(self) -> list[Track]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM tracks ORDER BY artist, album, title").fetchall()
        return [self._track(r) for r in rows]

    def get(self, track_id: int) -> Track | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return self._track(row) if row else None

    def search(self, query: str, limit: int = 40) -> list[Track]:
        needle = query.strip()
        if not needle:
            return []
        like = f"%{needle}%"
        prefix = f"{needle}%"
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT * FROM tracks
                WHERE title LIKE ? COLLATE NOCASE
                   OR artist LIKE ? COLLATE NOCASE
                   OR album LIKE ? COLLATE NOCASE
                   OR path LIKE ? COLLATE NOCASE
                ORDER BY
                    CASE
                        WHEN title LIKE ? COLLATE NOCASE THEN 0
                        WHEN artist LIKE ? COLLATE NOCASE THEN 1
                        ELSE 2
                    END,
                    artist, title
                LIMIT ?
                """,
                (like, like, like, like, prefix, prefix, limit),
            ).fetchall()
        return [self._track(r) for r in rows]

    def unanalyzed_ids(self) -> list[int]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id FROM tracks WHERE analyzed = 0"
            ).fetchall()
        return [int(r["id"]) for r in rows]

    def mark_all_pending_analysis(self) -> int:
        """Mark every track for re-analysis (Rescan). Pinned moods stay protected in set_analyzed_mood."""
        with self.lock:
            cur = self.conn.execute("UPDATE tracks SET analyzed = 0")
            self.conn.commit()
            return int(cur.rowcount)

    def existing_mtime(self, path: str) -> float | None:
        with self.lock:
            row = self.conn.execute("SELECT mtime FROM tracks WHERE path = ?", (path,)).fetchone()
        return float(row["mtime"]) if row and row["mtime"] is not None else None

    @staticmethod
    def _track(row: sqlite3.Row) -> Track:
        return Track(
            id=int(row["id"]),
            path=row["path"],
            title=row["title"] or "",
            artist=row["artist"] or "",
            album=row["album"] or "",
            albumartist=(row["albumartist"] or "") if "albumartist" in row.keys() else "",
            genre=row["genre"] or "",
            duration_ms=int(row["duration_ms"] or 0),
            year=row["year"],
            bpm=row["bpm"],
            valence=float(row["valence"]),
            energy=float(row["energy"]),
            mood_confidence=(
                float(row["mood_confidence"])
                if "mood_confidence" in row.keys() and row["mood_confidence"] is not None
                else (0.30 if (row["low_trust"] if "low_trust" in row.keys() else 0) else 0.80)
            ),
            confidence_note=(
                (row["confidence_note"] or "")
                if "confidence_note" in row.keys()
                else ""
            ),
            low_trust=bool(row["low_trust"]) if "low_trust" in row.keys() else False,
            pinned=bool(row["pinned"]),
            loved=bool(row["loved"]),
            play_count=int(row["play_count"]),
            skip_count=int(row["skip_count"]),
            last_played=row["last_played"],
            added_at=row["added_at"],
            mtime=row["mtime"],
            analyzed=bool(row["analyzed"]),
        )
