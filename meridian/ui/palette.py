from __future__ import annotations

from PySide6.QtGui import QColor

from meridian.queue_engine import Quadrant

# High-contrast playlist colors on the dark map (and matching list text).
PLAYLIST_HEX = {
    Quadrant.NOW: "#FFBF00",
    Quadrant.DEEP: "#00E5FF",
    Quadrant.FILL: "#FF3D8F",
    Quadrant.SHELF: "#8BFF4D",
}

PLAYLIST_QCOLOR = {q: QColor(h) for q, h in PLAYLIST_HEX.items()}

STAR_RADIUS = {
    Quadrant.NOW: 6.8,
    Quadrant.DEEP: 6.4,
    Quadrant.FILL: 6.2,
    Quadrant.SHELF: 5.2,
}

STAR_Z = {
    Quadrant.NOW: 11,
    Quadrant.DEEP: 10,
    Quadrant.FILL: 9,
    Quadrant.SHELF: 7,
}
