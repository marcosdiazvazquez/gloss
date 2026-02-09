from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Signal, Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QScrollArea,
)


THUMB_HEIGHT = 80
THUMB_BORDER_ACTIVE = "#89b4fa"
THUMB_BORDER_INACTIVE = "#313244"
CAROUSEL_BG = "#11111b"


class _Thumbnail(QLabel):
    """Clickable slide thumbnail for the carousel."""

    clicked = Signal(int)  # page index

    def __init__(self, page: int, parent=None):
        super().__init__(parent)
        self._page = page
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(THUMB_HEIGHT)
        self.setStyleSheet(
            f"border: 2px solid {THUMB_BORDER_INACTIVE}; border-radius: 3px; padding: 1px;"
        )

    def set_active(self, active: bool):
        color = THUMB_BORDER_ACTIVE if active else THUMB_BORDER_INACTIVE
        self.setStyleSheet(
            f"border: 2px solid {color}; border-radius: 3px; padding: 1px;"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._page)
        super().mousePressEvent(event)


class SlideViewer(QWidget):
    """Renders a single PDF page at a time, scaled to fit the available space."""

    page_changed = Signal(int)  # 0-indexed page number

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = QPdfDocument(self)
        self._current_page = 0
        self._thumbnails: list[_Thumbnail] = []
        self._init_ui()
        self._doc.statusChanged.connect(self._on_status_changed)

    def _init_ui(self):
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._label)

        # Carousel
        carousel_wrapper = QWidget()
        carousel_wrapper.setFixedHeight(THUMB_HEIGHT + 16)
        carousel_wrapper.setStyleSheet(f"background-color: {CAROUSEL_BG};")
        carousel_outer = QVBoxLayout(carousel_wrapper)
        carousel_outer.setContentsMargins(8, 8, 8, 8)
        carousel_outer.setSpacing(0)

        self._carousel_scroll = QScrollArea()
        self._carousel_scroll.setWidgetResizable(True)
        self._carousel_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._carousel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._carousel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._carousel_scroll.setFixedHeight(THUMB_HEIGHT)
        self._carousel_scroll.setStyleSheet(f"background-color: {CAROUSEL_BG};")
        carousel_outer.addWidget(self._carousel_scroll)

        self._carousel_container = QWidget()
        self._carousel_container.setStyleSheet(f"background-color: {CAROUSEL_BG};")
        self._carousel_layout = QHBoxLayout(self._carousel_container)
        self._carousel_layout.setContentsMargins(0, 0, 0, 0)
        self._carousel_layout.setSpacing(6)
        self._carousel_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._carousel_scroll.setWidget(self._carousel_container)

        layout.addWidget(carousel_wrapper)

    # -- Public API --

    def load_pdf(self, path: str | Path):
        self._doc.close()
        self._current_page = 0
        self._doc.load(str(path))

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def page_count(self) -> int:
        return self._doc.pageCount()

    def next_page(self):
        if self._current_page < self._doc.pageCount() - 1:
            self._current_page += 1
            self._render()
            self._update_carousel()
            self.page_changed.emit(self._current_page)

    def prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render()
            self._update_carousel()
            self.page_changed.emit(self._current_page)

    def go_to_page(self, page: int):
        if 0 <= page < self._doc.pageCount() and page != self._current_page:
            self._current_page = page
            self._render()
            self._update_carousel()
            self.page_changed.emit(self._current_page)

    # -- Internal --

    def _on_status_changed(self, status):
        if status == QPdfDocument.Status.Ready:
            self._build_carousel()
            self._render()
            self._update_carousel()
            self.page_changed.emit(self._current_page)
        elif status == QPdfDocument.Status.Null:
            self._label.clear()
            self._clear_carousel()

    def _render(self):
        if self._doc.status() != QPdfDocument.Status.Ready:
            return

        available = self._label.size()
        if available.width() <= 0 or available.height() <= 0:
            return

        page_size = self._doc.pagePointSize(self._current_page)
        if page_size.width() <= 0 or page_size.height() <= 0:
            return

        # Scale to fit while preserving aspect ratio
        dpr = self.devicePixelRatioF()
        scale = min(
            available.width() / page_size.width(),
            available.height() / page_size.height(),
        )
        render_size = QSize(
            int(page_size.width() * scale * dpr),
            int(page_size.height() * scale * dpr),
        )

        image = self._doc.render(self._current_page, render_size)
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)
        self._label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    # -- Carousel --

    def _clear_carousel(self):
        self._thumbnails.clear()
        while self._carousel_layout.count():
            item = self._carousel_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_carousel(self):
        self._clear_carousel()
        total = self._doc.pageCount()
        if total <= 0:
            return

        dpr = self.devicePixelRatioF()
        for i in range(total):
            thumb = _Thumbnail(i, self._carousel_container)
            thumb.clicked.connect(self.go_to_page)

            # Render thumbnail
            page_size = self._doc.pagePointSize(i)
            if page_size.width() > 0 and page_size.height() > 0:
                thumb_h = THUMB_HEIGHT - 6  # account for border/padding
                scale = thumb_h / page_size.height()
                thumb_w = int(page_size.width() * scale)
                thumb.setFixedWidth(thumb_w + 6)

                render_size = QSize(
                    int(page_size.width() * scale * dpr),
                    int(page_size.height() * scale * dpr),
                )
                image = self._doc.render(i, render_size)
                pixmap = QPixmap.fromImage(image)
                pixmap.setDevicePixelRatio(dpr)
                thumb.setPixmap(pixmap)

            self._carousel_layout.addWidget(thumb)
            self._thumbnails.append(thumb)

    def _update_carousel(self):
        for i, thumb in enumerate(self._thumbnails):
            thumb.set_active(i == self._current_page)

        # Scroll to make current thumbnail visible
        if self._current_page < len(self._thumbnails):
            thumb = self._thumbnails[self._current_page]
            self._carousel_scroll.ensureWidgetVisible(thumb, 50, 0)
