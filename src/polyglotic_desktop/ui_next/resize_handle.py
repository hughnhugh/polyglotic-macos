"""Inner resize handles for a Cocoa window's client area."""

from collections.abc import Callable

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from polyglotic_desktop.ui_next.views.placement import Edge, Preset, Rect, Size, resized

CURSORS = {
    Edge.LEFT: Qt.CursorShape.SizeHorCursor,
    Edge.RIGHT: Qt.CursorShape.SizeHorCursor,
    Edge.TOP: Qt.CursorShape.SizeVerCursor,
    Edge.BOTTOM: Qt.CursorShape.SizeVerCursor,
    Edge.LEFT | Edge.TOP: Qt.CursorShape.SizeFDiagCursor,
    Edge.RIGHT | Edge.BOTTOM: Qt.CursorShape.SizeFDiagCursor,
    Edge.RIGHT | Edge.TOP: Qt.CursorShape.SizeBDiagCursor,
    Edge.LEFT | Edge.BOTTOM: Qt.CursorShape.SizeBDiagCursor,
}

GRIP = 8
CORNER = 12


class PanelResizeCursor(QWidget):
    """A native resize cursor when active, an in-panel arrow when another app owns it."""

    def __init__(self, owner: QWidget, refresh: Callable[[int], bool]) -> None:
        super().__init__(owner)
        self.setObjectName("caption.resize_hint")
        self.owner = owner
        self.refresh = refresh
        self.edge = Edge.NONE
        self.setFixedSize(22, 22)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def follow(self, pos: QPointF, edge: Edge) -> None:
        if not edge and not self.edge:
            return
        self.edge = edge
        native = self.refresh(int(self.owner.window().winId()))
        if not edge or native:
            self.hide()
            return
        # Keep the arrows inside the panel, just beside the actual pointer.
        # The app underneath keeps the user's keyboard focus.
        radius = self.width() // 2
        x = max(0, min(self.owner.width() - self.width(), round(pos.x()) - radius))
        y = max(0, min(self.owner.height() - self.height(), round(pos.y()) - radius))
        self.move(x, y)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        shape = CURSORS[self.edge]
        angle = {
            Qt.CursorShape.SizeHorCursor: 0,
            Qt.CursorShape.SizeVerCursor: 90,
            Qt.CursorShape.SizeFDiagCursor: 45,
            Qt.CursorShape.SizeBDiagCursor: -45,
        }[shape]
        painter.rotate(angle)
        path = QPainterPath(QPointF(-8, 0))
        path.lineTo(8, 0)
        for sign in (-1, 1):
            path.moveTo(4 * sign, -4)
            path.lineTo(8 * sign, 0)
            path.lineTo(4 * sign, 4)
        for colour, width in (("black", 4), ("white", 1.8)):
            painter.setPen(
                QPen(
                    QColor(colour),
                    width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(path)
        painter.end()


class ResizeHandle(QWidget):
    """An eight-point strip, or a twelve-point corner, inside the native frame."""

    def __init__(self, parent: QWidget, edges: Edge) -> None:
        super().__init__(parent)
        self.edges = edges
        self.setCursor(CURSORS[edges])
        self.drag: tuple[QPoint, Rect, Rect] | None = None

    def fit(self) -> None:
        window = self.window()
        self.setVisible(not window.isMaximized() and not window.isFullScreen())
        width, height = window.width(), window.height()
        horizontal = self.edges & (Edge.LEFT | Edge.RIGHT)
        vertical = self.edges & (Edge.TOP | Edge.BOTTOM)
        if horizontal and vertical:
            w = h = CORNER
        elif horizontal:
            w, h = GRIP, height - 2 * CORNER
        else:
            w, h = width - 2 * CORNER, GRIP
        x = width - w if self.edges & Edge.RIGHT else 0 if horizontal else CORNER
        y = height - h if self.edges & Edge.BOTTOM else 0 if vertical else CORNER
        self.setGeometry(x, y, w, h)
        self.raise_()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        window = self.window()
        frame = window.frameGeometry()
        room = window.screen().availableGeometry()
        room.setTop(room.top() + window.geometry().top() - frame.top())
        client = window.geometry()
        self.drag = (
            event.globalPosition().toPoint(),
            Rect(client.x(), client.y(), client.width(), client.height()),
            Rect(room.x(), room.y(), room.width(), room.height()),
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.drag is None:
            return
        start, rect, room = self.drag
        delta = event.globalPosition().toPoint() - start
        window = self.window()
        result = resized(
            rect,
            self.edges,
            delta.x(),
            delta.y(),
            Preset.CUSTOM,
            Size(window.minimumWidth(), window.minimumHeight()),
            room,
        )
        window.setGeometry(*result.as_list())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag = None
