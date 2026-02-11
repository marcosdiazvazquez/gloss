"""Lecture view — slide viewer + notes panel side by side."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
)
from PySide6.QtCore import Signal, Qt, QEvent
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QApplication

from src.models import storage
from src.models.session import Session, SlideData
from src.utils.config import COURSES_DIR
from src.views.home_view import COURSE_COLORS
from src.widgets.slide_viewer import SlideViewer
from src.widgets.notes_editor import NotesEditor


class LectureView(QWidget):
    """Slide viewer + notes panel — the core lecture experience."""

    back_requested = Signal()
    review_requested = Signal(str, str)  # course_id, lecture_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._course_id: str = ""
        self._lecture_id: str = ""
        self._session: Session | None = None
        self._init_ui()
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.KeyPress
                and self.isVisible()
                and not self._editor.hasFocus()):
            if event.key() == Qt.Key.Key_Tab:
                self._editor.setFocus()
                return True
            elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_K):
                self._prev_slide()
                return True
            elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_J):
                self._next_slide()
                return True
        return super().eventFilter(obj, event)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Top navigation bar --
        nav_bar = QWidget()
        nav_bar.setFixedHeight(50)
        nav_bar.setStyleSheet("background-color: #181825;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(12, 4, 12, 4)

        self._prev_btn = QPushButton("< Prev")
        self._prev_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; color: #89b4fa; }"
            "QPushButton:hover { background-color: #313244; color: #b4befe; }"
        )
        self._prev_btn.clicked.connect(self._prev_slide)
        sp = self._prev_btn.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self._prev_btn.setSizePolicy(sp)
        nav_layout.addWidget(self._prev_btn)

        nav_layout.addStretch()

        self._page_label = QLabel("Slide 0 of 0")
        self._page_label.setStyleSheet("color: #cdd6f4;")
        nav_layout.addWidget(self._page_label)

        nav_layout.addStretch()

        self._next_btn = QPushButton("Next >")
        self._next_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; color: #89b4fa; }"
            "QPushButton:hover { background-color: #313244; color: #b4befe; }"
        )
        self._next_btn.clicked.connect(self._next_slide)
        sp = self._next_btn.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self._next_btn.setSizePolicy(sp)
        nav_layout.addWidget(self._next_btn)

        layout.addWidget(nav_bar)

        # -- Splitter: slide viewer (left 60%) + notes editor (right 40%) --
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(8, 0, 8, 0)
        content_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        self._viewer = SlideViewer()
        self._viewer.setStyleSheet(
            "SlideViewer { background-color: #181825; border: 1px solid #313244; border-radius: 8px; }"
        )
        self._editor = NotesEditor()
        self._editor.setStyleSheet(
            "NotesEditor { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 8px; padding: 8px; }"
        )

        self._viewer.setMinimumWidth(250)
        self._editor.setMinimumWidth(250)

        self._splitter.addWidget(self._viewer)
        self._splitter.addWidget(self._editor)
        self._splitter.setSizes([600, 400])  # 60/40 split
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet(
            "QSplitter::handle {"
            "  background-color: #45475a;"
            "}"
            "QSplitter::handle:hover {"
            "  background-color: #89b4fa;"
            "}"
        )

        content_layout.addWidget(self._splitter)
        layout.addWidget(content_area, 1)

        # -- Bottom bar --
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(50)
        bottom_bar.setStyleSheet("background-color: #181825;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(40, 4, 40, 4)

        home_btn = QPushButton("Home")
        home_btn.setStyleSheet(
            "QPushButton { padding: 4px 16px; color: #94e2d5; }"
            "QPushButton:hover { background-color: #313244; color: #a6e3a1; }"
        )
        home_btn.clicked.connect(self.back_requested.emit)
        bottom_layout.addWidget(home_btn)

        bottom_layout.addStretch()

        review_btn = QPushButton("Enter Review Mode")
        review_btn.setStyleSheet(
            "QPushButton { padding: 4px 16px; color: #cba6f7; }"
            "QPushButton:hover { background-color: #313244; color: #f5c2e7; }"
        )
        review_btn.clicked.connect(
            lambda: self.review_requested.emit(self._course_id, self._lecture_id)
        )
        bottom_layout.addWidget(review_btn)

        layout.addWidget(bottom_bar)

        # -- Signals --
        self._viewer.page_changed.connect(self._on_page_changed)
        self._editor.notes_changed.connect(self._save_current_notes)

    # -- Public API ---------------------------------------------------------

    def handle_escape(self):
        """First Escape: leave editor → slide view. Second Escape: go home."""
        if self._editor.hasFocus():
            self._viewer.setFocus()
        else:
            self._flush_notes()
            self.back_requested.emit()

    def load(self, course_id: str, lecture_id: str):
        # Save notes from previous session if any
        self._flush_notes()

        self._course_id = course_id
        self._lecture_id = lecture_id
        self._session = storage.load_session(course_id, lecture_id)

        # Determine course color (same index logic as home view)
        courses = storage.list_courses()
        color = "#cdd6f4"  # fallback
        for i, c in enumerate(courses):
            if c.id == course_id:
                color = COURSE_COLORS[i % len(COURSE_COLORS)]
                break
        self._page_label.setStyleSheet(f"color: {color};")

        pdf_path = COURSES_DIR / course_id / "lectures" / lecture_id / self._session.pdf_filename
        self._viewer.load_pdf(pdf_path)
        self._load_notes_for_page(0)

    # -- Slide navigation ---------------------------------------------------

    def _prev_slide(self):
        self._flush_notes()
        self._viewer.prev_page()

    def _next_slide(self):
        self._flush_notes()
        self._viewer.next_page()

    def _on_page_changed(self, page: int):
        total = self._viewer.page_count
        self._page_label.setText(f"Slide {page + 1} of {total}")
        self._prev_btn.setVisible(page > 0)
        self._next_btn.setVisible(page < total - 1)
        if not self._editor.hasFocus():
            self._viewer.setFocus()
        self._load_notes_for_page(page)

    # -- Per-slide notes ----------------------------------------------------

    def _slide_key(self, page: int) -> str:
        """1-indexed string key matching the session JSON schema."""
        return str(page + 1)

    def _load_notes_for_page(self, page: int):
        if not self._session:
            return
        key = self._slide_key(page)
        slide_data = self._session.slides.get(key)
        self._editor.set_notes(slide_data.raw_notes if slide_data else "")

    def _flush_notes(self):
        """Save current editor text into the session and persist to disk."""
        if not self._session:
            return
        key = self._slide_key(self._viewer.current_page)
        text = self._editor.get_notes()
        if key not in self._session.slides:
            if not text:
                return  # don't create empty slide entries
            self._session.slides[key] = SlideData()
        self._session.slides[key].raw_notes = text
        storage.save_session(self._course_id, self._session)

    def _save_current_notes(self, text: str):
        """Called by the editor's debounced notes_changed signal."""
        if not self._session:
            return
        key = self._slide_key(self._viewer.current_page)
        if key not in self._session.slides:
            if not text:
                return
            self._session.slides[key] = SlideData()
        self._session.slides[key].raw_notes = text
        storage.save_session(self._course_id, self._session)
