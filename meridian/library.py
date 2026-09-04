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
    genre TEXT,
    duration_ms INTEGER DEFAULT 0,
    year INTEGER,
    bpm REAL,
    valence REAL NOT NULL DEFAULT 0.5,
    energy REAL NOT NULL DEFAULT 0.5,
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
    genre: str
    duration_ms: int
    year: int | None
    bpm: float | None
    valence: float
    energy: float
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
        artist = self.artist or "Unknown"
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
                if int(existing["pinned"] or 0):
                    payload.pop("valence", None)
                    payload.pop("energy", None)
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
            self.conn.execute(
                "UPDATE tracks SET valence = ?, energy = ?, pinned = ? WHERE id = ?",
                (valence, energy, int(pinned), track_id),
            )
            self.conn.commit()

    def set_analyzed_mood(self, track_id: int, valence: float, energy: float, bpm: float | None) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE tracks
                SET valence = CASE WHEN pinned = 1 THEN valence ELSE ? END,
                    energy = CASE WHEN pinned = 1 THEN energy ELSE ? END,
                    bpm = ?,
                    analyzed = 1
                WHERE id = ?
                """,
                (valence, energy, bpm, track_id),
            )
            self.conn.commit()

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
            genre=row["genre"] or "",
            duration_ms=int(row["duration_ms"] or 0),
            year=row["year"],
            bpm=row["bpm"],
            valence=float(row["valence"]),
            energy=float(row["energy"]),
            pinned=bool(row["pinned"]),
            loved=bool(row["loved"]),
            play_count=int(row["play_count"]),
            skip_count=int(row["skip_count"]),
            last_played=row["last_played"],
            added_at=row["added_at"],
            mtime=row["mtime"],
            analyzed=bool(row["analyzed"]),
        )
