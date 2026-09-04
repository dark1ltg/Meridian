from __future__ import annotations

from math import hypot

from PySide6.QtCore import QRectF, QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QPen, QRadialGradient, QPainterPath
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsScene, QGraphicsView

from meridian.context import LENS_RADIUS_DEFAULT, LENS_RADIUS_MAX, LENS_RADIUS_MIN
from meridian.queue_engine import Quadrant, RankedTrack
from meridian.ui.fonts import sans
from meridian.ui.palette import PLAYLIST_QCOLOR, STAR_RADIUS, STAR_Z


class TrackStar(QGraphicsEllipseItem):
    def __init__(self, ranked: RankedTrack, parent=None) -> None:
        r = STAR_RADIUS[ranked.quadrant]
        super().__init__(-r, -r, r * 2, r * 2, parent)
        self.ranked = ranked
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setToolTip(ranked.track.label)
        self._map: MoodMap | None = None
        self._press_scene: QPointF | None = None
        self.apply_style(ranked, current=False)

    def apply_style(self, ranked: RankedTrack, current: bool) -> None:
        self.ranked = ranked
        r = STAR_RADIUS[ranked.quadrant]
        if ranked.track.loved:
            r += 0.8
        self.setRect(-r, -r, r * 2, r * 2)
        color = QColor(PLAYLIST_QCOLOR[ranked.quadrant])
        self.setBrush(QBrush(color))
        if current:
            self.setPen(QPen(QColor("#ffffff"), 2.0))
            self.setZValue(14)
        elif ranked.track.loved:
            self.setPen(QPen(QColor("#fff4c2"), 1.4))
            self.setZValue(STAR_Z[ranked.quadrant] + 1)
        else:
            self.setPen(QPen(QColor(8, 12, 22, 220), 1.1))
            self.setZValue(STAR_Z[ranked.quadrant])
        self.setToolTip(f"{ranked.track.label}\n{ranked.quadrant.value.upper()}")

    def hoverEnterEvent(self, event) -> None:
        self.setScale(1.45)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.setScale(1.0)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            pos: QPointF = value
            pos.setX(max(40.0, min(760.0, pos.x())))
            pos.setY(max(36.0, min(560.0, pos.y())))
            return pos
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        self._press_scene = event.scenePos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if not self._map:
            return
        dragged = False
        if self._press_scene is not None:
            delta = event.scenePos() - self._press_scene
            dragged = hypot(delta.x(), delta.y()) > 8
        self._press_scene = None
        if dragged:
            self._map.star_moved(self)
        else:
            self._map.snap_lens_to_star(self)


class LensItem(QGraphicsEllipseItem):
    def __init__(self) -> None:
        super().__init__(-90, -90, 180, 180)
        self.setBrush(QBrush(QColor(109, 74, 255, 42)))
        ring = QPen(QColor("#6D4AFF"), 2.5)
        ring.setCosmetic(True)
        ring.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(ring)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(20)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._map: MoodMap | None = None
        halo = QPen(QColor("#F4F1FF"), 3.7)
        halo.setCosmetic(True)
        halo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._halo = QGraphicsEllipseItem(-90, -90, 180, 180, self)
        self._halo.setPen(halo)
        self._halo.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._halo.setZValue(-1)

    def setRect(self, *args) -> None:
        super().setRect(*args)
        self._halo.setRect(self.rect())

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            pos: QPointF = value
            pos.setX(max(80.0, min(720.0, pos.x())))
            pos.setY(max(70.0, min(530.0, pos.y())))
            return pos
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._map:
            self._map.lens_moved()
        return super().itemChange(change, value)


class MoodMap(QGraphicsView):
    lens_changed = Signal(float, float, float)
    track_pinned = Signal(int, float, float)
    track_activated = Signal(int)
    track_hovered = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setBackgroundBrush(QBrush(QColor("#0e1424")))
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#6D4AFF"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#0b1020"))
        self.setPalette(pal)
        self._scene = QGraphicsScene(0, 0, 800, 600, self)
        self._scene.setPalette(pal)
        self.setScene(self._scene)
        self._stars: dict[int, TrackStar] = {}
        self._radius = LENS_RADIUS_DEFAULT
        self._draw_backdrop()
        self.lens = LensItem()
        self._scene.addItem(self.lens)
        self.lens.setPos(420, 300)
        self.lens._map = self

    def _draw_backdrop(self) -> None:
        rect = QRectF(40, 36, 720, 524)
        panel = self._scene.addRect(rect, QPen(QColor("#1f2a44"), 1.2), QBrush(QColor("#121a2e")))
        panel.setZValue(0)
        for i in range(1, 4):
            y = 36 + 524 * i / 4
            line = self._scene.addLine(40, y, 760, y, QPen(QColor(255, 255, 255, 18), 1))
            line.setZValue(1)
            x = 40 + 720 * i / 4
            v = self._scene.addLine(x, 36, x, 560, QPen(QColor(255, 255, 255, 18), 1))
            v.setZValue(1)
        font = sans(11)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        for x, y, text in ((400, 22, "KINETIC  ↑"), (400, 582, "STILL  ↓")):
            item = self._scene.addSimpleText(text, font)
            item.setBrush(QBrush(QColor("#8b95ad")))
            item.setPos(x - item.boundingRect().width() / 2, y - 8)
            item.setZValue(2)
        for x, y, text, angle in ((16, 298, "SHADOW", -90), (784, 298, "GLOW", 90)):
            item = self._scene.addSimpleText(text, font)
            item.setBrush(QBrush(QColor("#8b95ad")))
            br = item.boundingRect()
            item.setTransformOriginPoint(br.center())
            item.setRotation(angle)
            item.setPos(x - br.width() / 2, y - br.height() / 2)
            item.setZValue(2)
        glow = QRadialGradient(400, 300, 280)
        glow.setColorAt(0.0, QColor(110, 200, 197, 28))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        path = QPainterPath()
        path.addEllipse(QPointF(400, 300), 280, 220)
        gitem = self._scene.addPath(path, QPen(Qt.PenStyle.NoPen), QBrush(glow))
        gitem.setZValue(1)
        legend_x = 52
        legend_y = 48
        font_l = sans(11, medium=True)
        font_l.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        for q in (Quadrant.NOW, Quadrant.DEEP, Quadrant.FILL, Quadrant.SHELF):
            dot = self._scene.addEllipse(
                legend_x, legend_y, 8, 8, QPen(Qt.PenStyle.NoPen), QBrush(PLAYLIST_QCOLOR[q])
            )
            dot.setZValue(4)
            label = self._scene.addSimpleText(q.value.upper(), font_l)
            label.setBrush(QBrush(PLAYLIST_QCOLOR[q]))
            label.setPos(legend_x + 12, legend_y - 3)
            label.setZValue(4)
            legend_x += 78

    def mood_to_pos(self, valence: float, energy: float) -> QPointF:
        x = 40 + valence * 720
        y = 560 - energy * 524
        return QPointF(x, y)

    def pos_to_mood(self, pos: QPointF) -> tuple[float, float]:
        valence = (pos.x() - 40) / 720
        energy = (560 - pos.y()) / 524
        return max(0.0, min(1.0, valence)), max(0.0, min(1.0, energy))

    def set_tracks(self, ranked: list[RankedTrack], current_id: int | None) -> None:
        keep = {r.track.id for r in ranked}
        for tid in list(self._stars):
            if tid not in keep:
                self._scene.removeItem(self._stars.pop(tid))
        for item in ranked:
            pos = self.mood_to_pos(item.track.valence, item.track.energy)
            star = self._stars.get(item.track.id)
            if star is None:
                star = TrackStar(item)
                star._map = self
                self._scene.addItem(star)
                self._stars[item.track.id] = star
                star.setPos(pos)
            else:
                if not star.isSelected():
                    star.setPos(pos)
            star.apply_style(item, current=item.track.id == current_id)

    def lens_mood(self) -> tuple[float, float, float]:
        vx, ey = self.pos_to_mood(self.lens.pos())
        return vx, ey, self._radius

    def set_lens(self, valence: float, energy: float, radius: float) -> None:
        self._radius = max(LENS_RADIUS_MIN, min(LENS_RADIUS_MAX, radius))
        self.lens.setPos(self.mood_to_pos(valence, energy))
        px = 90 * (self._radius / LENS_RADIUS_DEFAULT)
        self.lens.setRect(-px, -px, px * 2, px * 2)

    def snap_lens_to_star(self, star: TrackStar) -> None:
        track = star.ranked.track
        star.setPos(self.mood_to_pos(track.valence, track.energy))
        self.set_lens(track.valence, track.energy, self._radius)

    def lens_moved(self) -> None:
        x, y, r = self.lens_mood()
        self.lens_changed.emit(x, y, r)

    def star_moved(self, star: TrackStar) -> None:
        v, e = self.pos_to_mood(star.pos())
        self.track_pinned.emit(star.ranked.track.id, v, e)

    def wheelEvent(self, event) -> None:
        # Finer steps near the small end so the pull neighborhood can tighten precisely.
        step = 0.01 if self._radius <= 0.12 else 0.02
        delta = step if event.angleDelta().y() > 0 else -step
        self._radius = max(LENS_RADIUS_MIN, min(LENS_RADIUS_MAX, self._radius + delta))
        self.set_lens(*self.lens_mood())
        self.lens_moved()

    def mouseDoubleClickEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, TrackStar):
            self.track_activated.emit(item.ranked.track.id)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, TrackStar):
            self.track_hovered.emit(item.ranked.track.label)
        super().mouseMoveEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
