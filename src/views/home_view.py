"""Home view — course and lecture manager."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QInputDialog,
    QFileDialog,
    QMessageBox,
    QMenu,
    QSizePolicy,
)
from PySide6.QtCore import Signal, Qt

import src.utils.config as cfg
from src.models import storage
from src.models.session import Session

COURSE_COLORS = [
    "#f38ba8",  # Red
    "#fab387",  # Peach
    "#f9e2af",  # Yellow
    "#a6e3a1",  # Green
    "#94e2d5",  # Teal
    "#89b4fa",  # Blue
    "#cba6f7",  # Mauve
    "#f5c2e7",  # Pink
]


class _LectureRow(QWidget):
    """A single clickable lecture entry."""

    clicked = Signal()
    rename_requested = Signal()
    delete_requested = Signal()

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 4, 12, 4)

        title = QLabel(session.title)
        title.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(title)

        layout.addStretch()

        try:
            dt = datetime.fromisoformat(session.created_at)
            date_str = dt.strftime("%b %d")
        except (ValueError, TypeError):
            date_str = ""
        date_label = QLabel(date_str)
        base = cfg.font_size
        date_label.setStyleSheet(f"color: #585b70; font-size: {max(base - 2, 8)}pt;")
        layout.addWidget(date_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; }"
            "QMenu::item:selected { background-color: #45475a; }"
        )
        rename_action = menu.addAction("Rename lecture")
        delete_action = menu.addAction("Delete lecture")
        action = menu.exec(self.mapToGlobal(pos))
        if action == rename_action:
            self.rename_requested.emit()
        elif action == delete_action:
            self.delete_requested.emit()


class _CourseSection(QWidget):
    """A course header with its lecture list."""

    lecture_clicked = Signal(str, str)  # course_id, lecture_id
    refresh_needed = Signal()

    def __init__(self, course_id: str, course_name: str, lectures: list[Session], color: str, parent=None):
        super().__init__(parent)
        self._course_id = course_id
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(2)

        # Header row: course name + "+ lecture" button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(course_name)
        base = cfg.font_size
        name_label.setStyleSheet(f"font-weight: bold; color: {color}; font-size: {base + 4}pt;")
        header.addWidget(name_label)

        header.addStretch()

        add_btn = QPushButton("+ lecture")
        add_btn.setStyleSheet(
            "QPushButton { padding: 3px 10px; color: #585b70; background: transparent; }"
            "QPushButton:hover { color: #cdd6f4; }"
        )
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_lecture)
        header.addWidget(add_btn)

        layout.addLayout(header)

        # Lecture rows
        if not lectures:
            hint = QLabel("No lectures yet")
            hint.setStyleSheet("color: #585b70;")
            hint.setContentsMargins(28, 4, 0, 4)
            layout.addWidget(hint)
        else:
            for session in lectures:
                row = _LectureRow(session, self)
                sid = session.id
                row.clicked.connect(lambda s=sid: self.lecture_clicked.emit(self._course_id, s))
                row.rename_requested.connect(lambda s=sid: self._rename_lecture(s))
                row.delete_requested.connect(lambda s=sid: self._delete_lecture(s))
                layout.addWidget(row)

    def _add_lecture(self):
        title, ok = QInputDialog.getText(self, "New Lecture", "Lecture title:")
        if not ok or not title.strip():
            return
        pdf_path, _ = QFileDialog.getOpenFileName(
            self, "Select lecture PDF", "", "PDF Files (*.pdf)"
        )
        if not pdf_path:
            return
        storage.create_lecture(self._course_id, title.strip(), pdf_path)
        self.refresh_needed.emit()

    def _rename_lecture(self, lecture_id: str):
        new_title, ok = QInputDialog.getText(self, "Rename Lecture", "New title:")
        if ok and new_title.strip():
            storage.rename_lecture(self._course_id, lecture_id, new_title.strip())
            self.refresh_needed.emit()

    def _delete_lecture(self, lecture_id: str):
        reply = QMessageBox.question(
            self,
            "Delete lecture",
            "Delete this lecture and all its notes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            storage.delete_lecture(self._course_id, lecture_id)
            self.refresh_needed.emit()

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; }"
            "QMenu::item:selected { background-color: #45475a; }"
        )
        rename_action = menu.addAction("Rename course")
        delete_action = menu.addAction("Delete course")
        action = menu.exec(self.mapToGlobal(pos))
        if action == rename_action:
            new_name, ok = QInputDialog.getText(self, "Rename Course", "New name:")
            if ok and new_name.strip():
                storage.rename_course(self._course_id, new_name.strip())
                self.refresh_needed.emit()
        elif action == delete_action:
            reply = QMessageBox.question(
                self,
                "Delete course",
                "Delete this course and all its lectures?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                storage.delete_course(self._course_id)
                self.refresh_needed.emit()


class HomeView(QWidget):
    """Course and lecture manager — main landing screen."""

    lecture_opened = Signal(str, str)  # course_id, lecture_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area wrapping the content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        self._container = QWidget()
        scroll.setWidget(self._container)

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(32, 32, 32, 32)
        self._layout.setSpacing(8)

    def refresh(self):
        # Clear existing widgets
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Title
        title = QLabel("gloss")
        base = cfg.font_size
        title.setStyleSheet(f"font-weight: bold; font-size: {base * 3}pt;")
        self._layout.addWidget(title)
        self._layout.addSpacing(16)

        # Course sections
        courses = storage.list_courses()
        for i, course in enumerate(courses):
            color = COURSE_COLORS[i % len(COURSE_COLORS)]
            lectures = storage.list_lectures(course.id)
            section = _CourseSection(course.id, course.name, lectures, color, self._container)
            section.lecture_clicked.connect(self.lecture_opened.emit)
            section.refresh_needed.connect(self.refresh)
            self._layout.addWidget(section)

        # "+ New Course" button
        add_course_btn = QPushButton("+ New Course")
        add_course_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; color: #585b70; background: transparent; }"
            "QPushButton:hover { color: #cdd6f4; }"
        )
        add_course_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_course_btn.clicked.connect(self._add_course)
        self._layout.addWidget(add_course_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._layout.addStretch()

    def _add_course(self):
        name, ok = QInputDialog.getText(self, "New Course", "Course name:")
        if ok and name.strip():
            storage.create_course(name.strip())
            self.refresh()
