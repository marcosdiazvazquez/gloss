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
    QApplication,
)
from PySide6.QtCore import Signal, Qt, QMimeData, QPoint, QEvent, QUrl
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor, QDesktopServices

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

_MENU_QSS = (
    "QMenu {"
    "  background-color: #313244;"
    "  color: #cdd6f4;"
    "  border: 1px solid #45475a;"
    "  border-radius: 8px;"
    "  padding: 6px 0px;"
    "}"
    "QMenu::item {"
    "  padding: 8px 24px;"
    "  margin: 2px 6px;"
    "  border-radius: 4px;"
    "}"
    "QMenu::item:selected {"
    "  background-color: #45475a;"
    "}"
)

_DROP_INDICATOR_QSS = "background-color: #89b4fa; border-radius: 1px;"

MAX_NAME_LENGTH = 36

_DIALOG_QSS = (
    "QInputDialog { font-size: 11pt; }"
    "QLabel { font-size: 13pt; }"
    "QLineEdit { font-size: 14pt; }"
    "QPushButton { font-size: 13pt; padding: 4px 12px; }"
)


def _get_text(parent, title: str, label: str, text: str = "") -> tuple[str, bool]:
    """Show a QInputDialog with a smaller font size."""
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setTextValue(text)
    dialog.setStyleSheet(_DIALOG_QSS)
    dialog.setMinimumWidth(400)
    dialog.resize(400, dialog.minimumSizeHint().height())
    ok = dialog.exec()
    return dialog.textValue(), ok == QInputDialog.DialogCode.Accepted


class _DropIndicator(QWidget):
    """Thin colored line shown at the drop target position."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setStyleSheet(_DROP_INDICATOR_QSS)
        self.hide()


class _LectureRow(QWidget):
    """A single clickable lecture entry."""

    clicked = Signal()
    rename_requested = Signal()
    delete_requested = Signal()

    def __init__(self, session: Session, color: str = "#89b4fa", parent=None):
        super().__init__(parent)
        self.lecture_id = session.id
        self._color = color
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 4, 12, 4)

        self._title = QLabel(session.title)
        self._title.setStyleSheet(
            "QLabel { color: #bac2de; border-radius: 4px; padding: 2px 4px; }"
            f"QLabel:hover {{ background-color: #313244; color: {color}; }}"
        )
        self._title.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._title.setMinimumWidth(0)
        layout.addWidget(self._title)
        layout.addStretch()

        try:
            dt = datetime.fromisoformat(session.created_at)
            date_str = dt.strftime("%b %d")
        except (ValueError, TypeError):
            date_str = ""
        date_label = QLabel(date_str)
        base = cfg.font_size
        date_label.setStyleSheet(f"color: #6c7086; font-size: {max(base - 2, 8)}pt;")
        layout.addWidget(date_label)

        self._drag_start: QPoint | None = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-gloss-lecture", self.lecture_id.encode())
        drag.setMimeData(mime)
        # Semi-transparent snapshot as drag pixmap
        pixmap = self.grab()
        painter = QPainter(pixmap)
        painter.fillRect(pixmap.rect(), QColor(0, 0, 0, 80))
        painter.end()
        drag.setPixmap(pixmap)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start = None

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            # Only emit click if we didn't drag and clicked on the title
            if (event.position().toPoint() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
                if self._title.geometry().contains(event.position().toPoint()):
                    self.clicked.emit()
            self._drag_start = None
        super().mouseReleaseEvent(event)

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_QSS)
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
        self._course_name = course_name
        self._lectures_by_id = {s.id: s for s in lectures}
        self._lecture_ids = [s.id for s in lectures]
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setAcceptDrops(True)

        self.setStyleSheet(
            f"_CourseSection {{ border-left: 3px solid {color}; padding-left: 8px; }}"
        )

        self._body_layout = QVBoxLayout(self)
        self._body_layout.setContentsMargins(0, 0, 0, 12)
        self._body_layout.setSpacing(2)

        # Header row: course name + "+ lecture" button
        self._header = QWidget()
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(course_name)
        base = cfg.font_size
        name_label.setStyleSheet(f"font-weight: bold; color: {color}; font-size: {base + 4}pt;")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_label.setMinimumWidth(0)
        header_layout.addWidget(name_label)

        add_btn = QPushButton("+ lecture")
        add_btn.setStyleSheet(
            "QPushButton { padding: 3px 10px; color: #585b70; background: transparent; }"
            f"QPushButton:hover {{ color: {color}; }}"
        )
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_lecture)
        header_layout.addWidget(add_btn)

        self._body_layout.addWidget(self._header)

        # Drop indicator
        self._drop_indicator = _DropIndicator(self)

        # Lecture rows
        self._rows: list[_LectureRow] = []
        if not lectures:
            hint = QLabel("No lectures yet")
            hint.setStyleSheet("color: #6c7086; font-style: italic;")
            hint.setContentsMargins(28, 4, 0, 4)
            self._body_layout.addWidget(hint)
        else:
            for session in lectures:
                row = _LectureRow(session, color, self)
                sid = session.id
                row.clicked.connect(lambda s=sid: self.lecture_clicked.emit(self._course_id, s))
                row.rename_requested.connect(lambda s=sid: self._rename_lecture(s))
                row.delete_requested.connect(lambda s=sid: self._delete_lecture(s))
                self._body_layout.addWidget(row)
                self._rows.append(row)

        # Drag state for course header
        self._drag_start: QPoint | None = None

    @property
    def course_id(self) -> str:
        return self._course_id

    # -- Course header drag --------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Only drag from header area
            header_rect = self._header.geometry()
            if header_rect.contains(event.position().toPoint()):
                self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-gloss-course", self._course_id.encode())
        drag.setMimeData(mime)
        pixmap = self.grab()
        painter = QPainter(pixmap)
        painter.fillRect(pixmap.rect(), QColor(0, 0, 0, 80))
        painter.end()
        drag.setPixmap(pixmap)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start = None

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)

    # -- Lecture drop target -------------------------------------------------

    def _drop_index(self, pos: QPoint) -> int:
        """Return the insertion index for a lecture drop at the given position."""
        for i, row in enumerate(self._rows):
            row_rect = row.geometry()
            if pos.y() < row_rect.center().y():
                return i
        return len(self._rows)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-gloss-lecture"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat("application/x-gloss-lecture"):
            return
        event.acceptProposedAction()
        idx = self._drop_index(event.position().toPoint())
        # Position indicator
        if self._rows:
            if idx < len(self._rows):
                ref = self._rows[idx]
                y = ref.geometry().top() - 2
            else:
                ref = self._rows[-1]
                y = ref.geometry().bottom() + 1
        else:
            y = self._header.geometry().bottom() + 4
        self._drop_indicator.setGeometry(28, y, self.width() - 40, 3)
        self._drop_indicator.show()

    def dragLeaveEvent(self, event):
        self._drop_indicator.hide()

    def dropEvent(self, event):
        self._drop_indicator.hide()
        if not event.mimeData().hasFormat("application/x-gloss-lecture"):
            return
        lecture_id = bytes(event.mimeData().data("application/x-gloss-lecture")).decode()
        if lecture_id not in self._lecture_ids:
            return
        idx = self._drop_index(event.position().toPoint())
        # Build new order
        ids = [lid for lid in self._lecture_ids if lid != lecture_id]
        ids.insert(idx, lecture_id)
        storage.reorder_lectures(self._course_id, ids)
        event.acceptProposedAction()
        self.refresh_needed.emit()

    # -- Lecture CRUD --------------------------------------------------------

    def _add_lecture(self):
        prefill = ""
        while True:
            title, ok = _get_text(self,"New Lecture", "Lecture title:", text=prefill)
            if not ok or not title.strip():
                return
            if len(title.strip()) > MAX_NAME_LENGTH:
                QMessageBox.warning(self, "Title too long", f"Title must be {MAX_NAME_LENGTH} characters or fewer.")
                prefill = title
                continue
            break
        pdf_path, _ = QFileDialog.getOpenFileName(
            self, "Select lecture PDF", "", "PDF Files (*.pdf)"
        )
        if not pdf_path:
            return
        storage.create_lecture(self._course_id, title.strip(), pdf_path)
        self.refresh_needed.emit()

    def _rename_lecture(self, lecture_id: str):
        existing = self._lectures_by_id[lecture_id].title if lecture_id in self._lectures_by_id else ""
        prefill = existing
        while True:
            new_title, ok = _get_text(self,"Rename Lecture", "New title:", text=prefill)
            if not ok or not new_title.strip():
                return
            if len(new_title.strip()) > MAX_NAME_LENGTH:
                QMessageBox.warning(self, "Title too long", f"Title must be {MAX_NAME_LENGTH} characters or fewer.")
                prefill = new_title
                continue
            break
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
        menu.setStyleSheet(_MENU_QSS)
        rename_action = menu.addAction("Rename course")
        delete_action = menu.addAction("Delete course")
        action = menu.exec(self.mapToGlobal(pos))
        if action == rename_action:
            prefill = self._course_name
            while True:
                new_name, ok = _get_text(self,"Rename Course", "New name:", text=prefill)
                if not ok or not new_name.strip():
                    break
                if len(new_name.strip()) > MAX_NAME_LENGTH:
                    QMessageBox.warning(self, "Name too long", f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
                    prefill = new_name
                    continue
                storage.rename_course(self._course_id, new_name.strip())
                self.refresh_needed.emit()
                break
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
        self._sections: list[_CourseSection] = []
        self._drop_indicator = _DropIndicator()
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
        self._container.setAcceptDrops(True)
        scroll.setWidget(self._container)

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(32, 32, 32, 32)
        self._layout.setSpacing(8)

        # Bottom bar
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(36)
        bottom_bar.setStyleSheet("background-color: #181825;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(16, 4, 16, 4)
        bottom_layout.addStretch()
        github_btn = QPushButton("GitHub")
        github_btn.setStyleSheet(
            "QPushButton { color: #585b70; background: transparent; padding: 4px 12px; }"
            "QPushButton:hover { color: #89b4fa; }"
        )
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/marcosdiazvazquez/gloss"))
        )
        bottom_layout.addWidget(github_btn)
        bottom_layout.addStretch()
        outer.addWidget(bottom_bar)

    def refresh(self):
        # Clear existing widgets
        self._sections.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Title
        title = QLabel("gloss v0")
        base = cfg.font_size
        title.setStyleSheet(f"font-weight: bold; font-size: {base * 3}pt; color: #b4befe;")
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
            self._sections.append(section)

        # "+ New Course" button
        add_course_btn = QPushButton("+ New Course")
        add_course_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; color: #585b70; background: transparent; }"
            "QPushButton:hover { color: #a6e3a1; }"
        )
        add_course_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_course_btn.clicked.connect(self._add_course)
        self._layout.addWidget(add_course_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._layout.addStretch()

        # Re-parent drop indicator into the container
        self._drop_indicator.setParent(self._container)
        self._drop_indicator.hide()

        # Event filter to intercept course drops on the container
        self._container.installEventFilter(self)

    # -- Course drop target --------------------------------------------------

    def _course_drop_index(self, pos: QPoint) -> int:
        """Return the insertion index for a course drop at the given position."""
        for i, section in enumerate(self._sections):
            section_rect = section.geometry()
            if pos.y() < section_rect.center().y():
                return i
        return len(self._sections)

    def eventFilter(self, obj, event):
        if obj is not self._container:
            return super().eventFilter(obj, event)
        if not hasattr(event, "mimeData") or event.type() not in (
            QEvent.Type.DragEnter, QEvent.Type.DragMove,
            QEvent.Type.DragLeave, QEvent.Type.Drop,
        ):
            return super().eventFilter(obj, event)

        is_course = (
            event.type() != QEvent.Type.DragLeave
            and event.mimeData().hasFormat("application/x-gloss-course")
        )

        if event.type() == QEvent.Type.DragEnter:
            if is_course:
                event.acceptProposedAction()
                return True

        elif event.type() == QEvent.Type.DragMove:
            if is_course:
                event.acceptProposedAction()
                idx = self._course_drop_index(event.position().toPoint())
                if self._sections:
                    if idx < len(self._sections):
                        ref = self._sections[idx]
                        y = ref.geometry().top() - 2
                    else:
                        ref = self._sections[-1]
                        y = ref.geometry().bottom() + 1
                    self._drop_indicator.setGeometry(32, y, self._container.width() - 64, 3)
                    self._drop_indicator.show()
                return True

        elif event.type() == QEvent.Type.DragLeave:
            self._drop_indicator.hide()
            return True

        elif event.type() == QEvent.Type.Drop:
            self._drop_indicator.hide()
            if is_course:
                course_id = bytes(event.mimeData().data("application/x-gloss-course")).decode()
                idx = self._course_drop_index(event.position().toPoint())
                current_ids = [s.course_id for s in self._sections]
                if course_id in current_ids:
                    ids = [cid for cid in current_ids if cid != course_id]
                    ids.insert(idx, course_id)
                    storage.reorder_courses(ids)
                    event.acceptProposedAction()
                    self.refresh()
                return True

        return super().eventFilter(obj, event)

    # -- Course CRUD ---------------------------------------------------------

    def _add_course(self):
        prefill = ""
        while True:
            name, ok = _get_text(self,"New Course", "Course name:", text=prefill)
            if not ok or not name.strip():
                return
            if len(name.strip()) > MAX_NAME_LENGTH:
                QMessageBox.warning(self, "Name too long", f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
                prefill = name
                continue
            break
        storage.create_course(name.strip())
        self.refresh()
