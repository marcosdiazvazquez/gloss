from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Signal, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class SlideViewer(QWidget):
    """Renders a single PDF page at a time, scaled to fit the available space."""

    page_changed = Signal(int)  # 0-indexed page number

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = QPdfDocument(self)
        self._current_page = 0
        self._init_ui()
        self._doc.statusChanged.connect(self._on_status_changed)

    def _init_ui(self):
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setStyleSheet("background-color: #181825;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._label)

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
            self.page_changed.emit(self._current_page)

    def prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render()
            self.page_changed.emit(self._current_page)

    def go_to_page(self, page: int):
        if 0 <= page < self._doc.pageCount() and page != self._current_page:
            self._current_page = page
            self._render()
            self.page_changed.emit(self._current_page)

    # -- Internal --

    def _on_status_changed(self, status):
        if status == QPdfDocument.Status.Ready:
            self._render()
            self.page_changed.emit(self._current_page)
        elif status == QPdfDocument.Status.Null:
            self._label.clear()

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
