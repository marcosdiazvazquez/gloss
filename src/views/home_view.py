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
    QMenu,
    QSizePolicy,
    QApplication,
    QDialog,
    QLineEdit,
    QCheckBox,
)
from PySide6.QtCore import Signal, Qt, QMimeData, QPoint, QEvent, QUrl, QTimer
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor, QDesktopServices

import src.utils.config as cfg
from src.models import storage
from src.models.session import Group, Session
from src.utils.config import (
    load_api_key, save_api_key, load_model, save_model, AVAILABLE_MODELS,
    load_openai_api_key, save_openai_api_key, load_openai_model, save_openai_model,
    AVAILABLE_OPENAI_MODELS, load_provider, save_provider,
    load_gemini_api_key, save_gemini_api_key, load_gemini_model, save_gemini_model,
    AVAILABLE_GEMINI_MODELS,
)

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


_CONFIRM_DLG_QSS = (
    "QDialog { background-color: #1e1e2e; border: 1px solid #45475a; border-radius: 8px; }"
)

_CONFIRM_BTN = (
    "QPushButton {{ background-color: #313244; color: {color}; border: 1px solid {color};"
    "  border-radius: 4px; padding: 6px 16px; font-size: 13pt; }}"
    "QPushButton:hover {{ background-color: #45475a; }}"
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


def _confirm(parent, title: str, text: str) -> bool:
    """Show a themed Yes/No confirmation dialog. Returns True if Yes."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(340)
    dlg.setStyleSheet(_CONFIRM_DLG_QSS)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 20, 24, 16)
    layout.setSpacing(16)

    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setStyleSheet("color: #cdd6f4; font-size: 13pt;")
    layout.addWidget(label)

    btn_row = QHBoxLayout()
    btn_row.addStretch()

    no_btn = QPushButton("No")
    no_btn.setStyleSheet(_CONFIRM_BTN.format(color="#f38ba8"))
    no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    no_btn.clicked.connect(dlg.reject)
    btn_row.addWidget(no_btn)

    yes_btn = QPushButton("Yes")
    yes_btn.setStyleSheet(_CONFIRM_BTN.format(color="#a6e3a1"))
    yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    yes_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(yes_btn)

    btn_row.addStretch()

    layout.addLayout(btn_row)
    return dlg.exec() == QDialog.DialogCode.Accepted


def _warning(parent, title: str, text: str) -> None:
    """Show a themed warning dialog."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(340)
    dlg.setStyleSheet(_CONFIRM_DLG_QSS)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 20, 24, 16)
    layout.setSpacing(16)

    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setStyleSheet("color: #cdd6f4; font-size: 13pt;")
    layout.addWidget(label)

    btn_row = QHBoxLayout()
    btn_row.addStretch()

    ok_btn = QPushButton("Ok")
    ok_btn.setStyleSheet(_CONFIRM_BTN.format(color="#89b4fa"))
    ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(ok_btn)

    btn_row.addStretch()

    layout.addLayout(btn_row)
    dlg.exec()


def _encode_lecture_mime(lecture_id: str, group_id: str = "") -> bytes:
    """Encode lecture_id and source group_id into drag mime data."""
    return f"{lecture_id}:{group_id}".encode()


def _decode_lecture_mime(data: bytes) -> tuple[str, str]:
    """Decode mime data into (lecture_id, group_id). group_id is '' for ungrouped."""
    text = data.decode()
    if ":" in text:
        lid, gid = text.split(":", 1)
        return lid, gid
    return text, ""


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

    def __init__(self, session: Session, color: str = "#89b4fa", group_id: str = "", parent=None):
        super().__init__(parent)
        self.lecture_id = session.id
        self._color = color
        self._group_id = group_id
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
        mime.setData("application/x-gloss-lecture", _encode_lecture_mime(self.lecture_id, self._group_id))
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


class _GroupSection(QWidget):
    """A collapsible group of lectures within a course."""

    lecture_clicked = Signal(str, str, str)  # course_id, lecture_id, group_id
    refresh_needed = Signal()

    def __init__(self, course_id: str, group: Group, lectures: list[Session], color: str, parent=None):
        super().__init__(parent)
        self._course_id = course_id
        self._group = group
        self._color = color
        self._collapsed = False
        self._lectures_by_id = {s.id: s for s in lectures}
        self._lecture_ids = [s.id for s in lectures]
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

        self._body_layout = QVBoxLayout(self)
        self._body_layout.setContentsMargins(12, 0, 0, 4)
        self._body_layout.setSpacing(2)

        # Header row: collapse indicator + group name + "+ lecture" button
        self._header = QWidget()
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self._collapse_btn = QPushButton("v")
        self._collapse_btn.setFixedWidth(24)
        self._collapse_btn.setStyleSheet(
            f"QPushButton {{ color: #585b70; background: transparent; padding: 0; }}"
            f"QPushButton:hover {{ color: {color}; }}"
        )
        self._collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self._collapse_btn)

        base = cfg.font_size
        name_label = QLabel(group.name)
        name_label.setStyleSheet(f"font-weight: bold; color: {color}; font-size: {base + 1}pt; opacity: 0.85;")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_label.setMinimumWidth(0)
        header_layout.addWidget(name_label)

        self._body_layout.addWidget(self._header)

        # Drop indicator
        self._drop_indicator = _DropIndicator(self)

        # Lecture rows
        self._rows: list[_LectureRow] = []
        if not lectures:
            self._empty_hint = QLabel("No lectures")
            self._empty_hint.setStyleSheet("color: #45475a; font-style: italic;")
            self._empty_hint.setContentsMargins(28, 2, 0, 2)
            self._body_layout.addWidget(self._empty_hint)
        else:
            self._empty_hint = None
            for session in lectures:
                self._add_lecture_row(session)

        # Drag state for group header
        self._drag_start: QPoint | None = None

    @property
    def group_id(self) -> str:
        return self._group.id

    def _add_lecture_row(self, session: Session):
        row = _LectureRow(session, self._color, group_id=self._group.id, parent=self)
        sid = session.id
        gid = self._group.id
        row.clicked.connect(lambda s=sid, g=gid: self.lecture_clicked.emit(self._course_id, s, g))
        row.rename_requested.connect(lambda s=sid: self._rename_lecture(s))
        row.delete_requested.connect(lambda s=sid: self._delete_lecture(s))
        self._body_layout.addWidget(row)
        self._rows.append(row)

    # -- Collapse ----------------------------------------------------------------

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self._collapse_btn.setText(">" if self._collapsed else "v")
        for row in self._rows:
            row.setVisible(not self._collapsed)
        if self._empty_hint:
            self._empty_hint.setVisible(not self._collapsed)

    # -- Group header drag -------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
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
        mime.setData("application/x-gloss-group", self._group.id.encode())
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

    # -- Lecture drop target (within group) --------------------------------------

    def _drop_index(self, pos: QPoint) -> int:
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
        lecture_id, source_group = _decode_lecture_mime(
            bytes(event.mimeData().data("application/x-gloss-lecture"))
        )
        if source_group != self._group.id:
            # Cross-group move: move lecture into this group
            storage.move_lecture(
                self._course_id, lecture_id,
                from_group_id=source_group or None,
                to_group_id=self._group.id,
            )
            event.acceptProposedAction()
            self.refresh_needed.emit()
            return
        # Same group reorder
        if lecture_id not in self._lecture_ids:
            return
        idx = self._drop_index(event.position().toPoint())
        ids = [lid for lid in self._lecture_ids if lid != lecture_id]
        ids.insert(idx, lecture_id)
        storage.reorder_lectures(self._course_id, ids, group_id=self._group.id)
        event.acceptProposedAction()
        self.refresh_needed.emit()

    # -- Lecture CRUD ------------------------------------------------------------

    def _add_lecture(self):
        prefill = ""
        while True:
            title, ok = _get_text(self, "New Lecture", "Lecture title:", text=prefill)
            if not ok or not title.strip():
                return
            if len(title.strip()) > MAX_NAME_LENGTH:
                _warning(self, "Title too long", f"Title must be {MAX_NAME_LENGTH} characters or fewer.")
                prefill = title
                continue
            break
        pdf_path, _ = QFileDialog.getOpenFileName(
            self, "Select lecture PDF", "", "PDF Files (*.pdf)"
        )
        if not pdf_path:
            return
        storage.create_lecture(self._course_id, title.strip(), pdf_path, group_id=self._group.id)
        self.refresh_needed.emit()

    def _rename_lecture(self, lecture_id: str):
        existing = self._lectures_by_id[lecture_id].title if lecture_id in self._lectures_by_id else ""
        prefill = existing
        while True:
            new_title, ok = _get_text(self, "Rename Lecture", "New title:", text=prefill)
            if not ok or not new_title.strip():
                return
            if len(new_title.strip()) > MAX_NAME_LENGTH:
                _warning(self, "Title too long", f"Title must be {MAX_NAME_LENGTH} characters or fewer.")
                prefill = new_title
                continue
            break
        storage.rename_lecture(self._course_id, lecture_id, new_title.strip(), group_id=self._group.id)
        self.refresh_needed.emit()

    def _delete_lecture(self, lecture_id: str):
        if _confirm(self, "Delete lecture", "Delete this lecture and all its notes?"):
            storage.delete_lecture(self._course_id, lecture_id, group_id=self._group.id)
            self.refresh_needed.emit()

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_QSS)
        add_lecture_action = menu.addAction("Add lecture")
        menu.addSeparator()
        rename_action = menu.addAction("Rename group")
        delete_action = menu.addAction("Delete group")
        action = menu.exec(self.mapToGlobal(pos))
        if action == add_lecture_action:
            self._add_lecture()
        elif action == rename_action:
            prefill = self._group.name
            while True:
                new_name, ok = _get_text(self, "Rename Group", "New name:", text=prefill)
                if not ok or not new_name.strip():
                    break
                if len(new_name.strip()) > MAX_NAME_LENGTH:
                    _warning(self, "Name too long", f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
                    prefill = new_name
                    continue
                storage.rename_group(self._course_id, self._group.id, new_name.strip())
                self.refresh_needed.emit()
                break
        elif action == delete_action:
            if _confirm(self, "Delete group", "Delete this group and all its lectures?"):
                storage.delete_group(self._course_id, self._group.id)
                self.refresh_needed.emit()


class _CourseSection(QWidget):
    """A course header with its lecture list and groups."""

    lecture_clicked = Signal(str, str, str)  # course_id, lecture_id, group_id
    refresh_needed = Signal()

    def __init__(
        self,
        course_id: str,
        course_name: str,
        lectures: list[Session],
        groups_data: list[tuple[Group, list[Session]]],
        color: str,
        parent=None,
    ):
        super().__init__(parent)
        self._course_id = course_id
        self._course_name = course_name
        self._color = color
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

        # Header row: course name + "+ group" + "+ lecture" buttons
        self._header = QWidget()
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(course_name)
        base = cfg.font_size
        name_label.setStyleSheet(f"font-weight: bold; color: {color}; font-size: {base + 4}pt;")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_label.setMinimumWidth(0)
        header_layout.addWidget(name_label)

        add_group_btn = QPushButton("+ group")
        add_group_btn.setStyleSheet(
            "QPushButton { padding: 3px 10px; color: #585b70; background: transparent; }"
            f"QPushButton:hover {{ color: {color}; }}"
        )
        add_group_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_group_btn.clicked.connect(self._add_group)
        header_layout.addWidget(add_group_btn)

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

        # Ungrouped lecture rows
        self._rows: list[_LectureRow] = []
        if not lectures and not groups_data:
            hint = QLabel("No lectures yet")
            hint.setStyleSheet("color: #6c7086; font-style: italic;")
            hint.setContentsMargins(28, 4, 0, 4)
            self._body_layout.addWidget(hint)
        else:
            for session in lectures:
                row = _LectureRow(session, color, group_id="", parent=self)
                sid = session.id
                row.clicked.connect(lambda s=sid: self.lecture_clicked.emit(self._course_id, s, ""))
                row.rename_requested.connect(lambda s=sid: self._rename_lecture(s))
                row.delete_requested.connect(lambda s=sid: self._delete_lecture(s))
                self._body_layout.addWidget(row)
                self._rows.append(row)

        # Group sections
        self._group_sections: list[_GroupSection] = []
        for group, group_lectures in groups_data:
            gs = _GroupSection(course_id, group, group_lectures, color, self)
            gs.lecture_clicked.connect(self.lecture_clicked.emit)
            gs.refresh_needed.connect(self.refresh_needed.emit)
            self._body_layout.addWidget(gs)
            self._group_sections.append(gs)

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

    # -- Drop target ---------------------------------------------------------

    def _drop_index(self, pos: QPoint) -> int:
        """Return the insertion index for an ungrouped lecture drop."""
        for i, row in enumerate(self._rows):
            row_rect = row.geometry()
            if pos.y() < row_rect.center().y():
                return i
        return len(self._rows)

    def _group_drop_index(self, pos: QPoint) -> int:
        """Return the insertion index for a group drop."""
        for i, gs in enumerate(self._group_sections):
            gs_rect = gs.geometry()
            if pos.y() < gs_rect.center().y():
                return i
        return len(self._group_sections)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-gloss-lecture") or mime.hasFormat("application/x-gloss-group"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-gloss-lecture"):
            event.acceptProposedAction()
            idx = self._drop_index(event.position().toPoint())
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
        elif mime.hasFormat("application/x-gloss-group"):
            event.acceptProposedAction()
            idx = self._group_drop_index(event.position().toPoint())
            if self._group_sections:
                if idx < len(self._group_sections):
                    ref = self._group_sections[idx]
                    y = ref.geometry().top() - 2
                else:
                    ref = self._group_sections[-1]
                    y = ref.geometry().bottom() + 1
            elif self._rows:
                ref = self._rows[-1]
                y = ref.geometry().bottom() + 4
            else:
                y = self._header.geometry().bottom() + 4
            self._drop_indicator.setGeometry(28, y, self.width() - 40, 3)
            self._drop_indicator.show()

    def dragLeaveEvent(self, event):
        self._drop_indicator.hide()

    def dropEvent(self, event):
        self._drop_indicator.hide()
        mime = event.mimeData()

        if mime.hasFormat("application/x-gloss-lecture"):
            lecture_id, source_group = _decode_lecture_mime(
                bytes(mime.data("application/x-gloss-lecture"))
            )
            if source_group:
                # Moving from a group to ungrouped
                storage.move_lecture(
                    self._course_id, lecture_id,
                    from_group_id=source_group,
                    to_group_id=None,
                )
                event.acceptProposedAction()
                self.refresh_needed.emit()
                return
            # Same-area reorder (ungrouped)
            if lecture_id not in self._lecture_ids:
                return
            idx = self._drop_index(event.position().toPoint())
            ids = [lid for lid in self._lecture_ids if lid != lecture_id]
            ids.insert(idx, lecture_id)
            storage.reorder_lectures(self._course_id, ids)
            event.acceptProposedAction()
            self.refresh_needed.emit()

        elif mime.hasFormat("application/x-gloss-group"):
            group_id = bytes(mime.data("application/x-gloss-group")).decode()
            current_ids = [gs.group_id for gs in self._group_sections]
            if group_id not in current_ids:
                return
            idx = self._group_drop_index(event.position().toPoint())
            ids = [gid for gid in current_ids if gid != group_id]
            ids.insert(idx, group_id)
            storage.reorder_groups(self._course_id, ids)
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
                _warning(self, "Title too long", f"Title must be {MAX_NAME_LENGTH} characters or fewer.")
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
                _warning(self, "Title too long", f"Title must be {MAX_NAME_LENGTH} characters or fewer.")
                prefill = new_title
                continue
            break
        storage.rename_lecture(self._course_id, lecture_id, new_title.strip())
        self.refresh_needed.emit()

    def _delete_lecture(self, lecture_id: str):
        if _confirm(self, "Delete lecture", "Delete this lecture and all its notes?"):
            storage.delete_lecture(self._course_id, lecture_id)
            self.refresh_needed.emit()

    # -- Group CRUD ----------------------------------------------------------

    def _add_group(self):
        prefill = ""
        while True:
            name, ok = _get_text(self, "New Group", "Group name:", text=prefill)
            if not ok or not name.strip():
                return
            if len(name.strip()) > MAX_NAME_LENGTH:
                _warning(self, "Name too long", f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
                prefill = name
                continue
            break
        storage.create_group(self._course_id, name.strip())
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
                    _warning(self, "Name too long", f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
                    prefill = new_name
                    continue
                storage.rename_course(self._course_id, new_name.strip())
                self.refresh_needed.emit()
                break
        elif action == delete_action:
            if _confirm(self, "Delete course", "Delete this course and all its lectures?"):
                storage.delete_course(self._course_id)
                self.refresh_needed.emit()


_SETTINGS_QSS = """
    _SettingsDialog { background-color: #1e1e2e; }
    QLabel { font-size: 11pt; }
    QLineEdit { font-size: 11pt; }
    QCheckBox { font-size: 10pt; }
"""

_INPUT_QSS = (
    "QLineEdit { background-color: #313244; border: 1px solid #45475a; "
    "border-radius: 4px; padding: 6px; color: #cdd6f4; font-size: 11pt; }"
    "QLineEdit:focus { border-color: #89b4fa; }"
)

_MODEL_BTN_OFF = (
    "QPushButton { background-color: #313244; border: 1px solid #45475a; "
    "border-radius: 4px; padding: 6px 10px; color: #a6adc8; "
    "font-size: 10pt; text-align: left; }"
    "QPushButton:hover { border-color: #585b70; }"
)

_MODEL_BTN_ON = (
    "QPushButton { background-color: #313244; border: 1px solid #fab387; "
    "border-radius: 4px; padding: 6px 10px; color: #cdd6f4; "
    "font-size: 10pt; text-align: left; }"
    "QPushButton:hover { border-color: #fab387; }"
)

_MODEL_BTN_ON_GREEN = (
    "QPushButton { background-color: #313244; border: 1px solid #a6e3a1; "
    "border-radius: 4px; padding: 6px 10px; color: #cdd6f4; "
    "font-size: 10pt; text-align: left; }"
    "QPushButton:hover { border-color: #a6e3a1; }"
)

_MODEL_BTN_ON_BLUE = (
    "QPushButton { background-color: #313244; border: 1px solid #89b4fa; "
    "border-radius: 4px; padding: 6px 10px; color: #cdd6f4; "
    "font-size: 10pt; text-align: left; }"
    "QPushButton:hover { border-color: #89b4fa; }"
)

class _ProviderHeader(QLabel):
    """Clickable section header label — avoids QPushButton sizing quirks on macOS."""

    clicked = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("font-size: 12pt; font-weight: bold;")

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class _SettingsDialog(QDialog):
    """Settings dialog — Anthropic and OpenAI provider configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedWidth(440)
        self.setStyleSheet(_SETTINGS_QSS)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Settings")
        title.setStyleSheet("font-weight: bold; color: #b4befe; font-size: 14pt;")
        layout.addWidget(title)
        layout.addSpacing(4)

        self._active_provider = load_provider()
        self._selected_anthropic_model = load_model()
        self._selected_openai_model = load_openai_model()
        self._selected_gemini_model = load_gemini_model()
        self._anthropic_model_buttons: list[tuple[str, QPushButton]] = []
        self._openai_model_buttons: list[tuple[str, QPushButton]] = []
        self._gemini_model_buttons: list[tuple[str, QPushButton]] = []

        # ── Anthropic section ──────────────────────────────────────────────
        self._anthropic_header = _ProviderHeader("Anthropic")
        self._anthropic_header.clicked.connect(lambda: self._set_provider("anthropic"))
        layout.addWidget(self._anthropic_header)

        key_label_a = QLabel("API Key")
        key_label_a.setStyleSheet("color: #a6adc8;")
        layout.addWidget(key_label_a)

        key_row_a = QHBoxLayout()
        key_row_a.setSpacing(6)
        self._anthropic_key = QLineEdit()
        self._anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._anthropic_key.setPlaceholderText("sk-ant-...")
        self._anthropic_key.setText(load_api_key())
        self._anthropic_key.setStyleSheet(_INPUT_QSS)
        key_row_a.addWidget(self._anthropic_key)
        show_a = QCheckBox("Show")
        show_a.setStyleSheet("color: #585b70;")
        show_a.toggled.connect(
            lambda on: self._anthropic_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        key_row_a.addWidget(show_a)
        layout.addLayout(key_row_a)

        model_label_a = QLabel("Model")
        model_label_a.setStyleSheet("color: #a6adc8;")
        layout.addWidget(model_label_a)

        model_group_a = QVBoxLayout()
        model_group_a.setSpacing(6)
        for model_id, display_name, description in AVAILABLE_MODELS:
            btn = QPushButton(f"{display_name}  —  {description}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, mid=model_id: self._select_anthropic_model(mid))
            self._anthropic_model_buttons.append((model_id, btn))
            model_group_a.addWidget(btn)
        layout.addLayout(model_group_a)

        layout.addSpacing(8)

        # ── OpenAI section ─────────────────────────────────────────────────
        self._openai_header = _ProviderHeader("OpenAI")
        self._openai_header.clicked.connect(lambda: self._set_provider("openai"))
        layout.addWidget(self._openai_header)

        key_label_o = QLabel("API Key")
        key_label_o.setStyleSheet("color: #a6adc8;")
        layout.addWidget(key_label_o)

        key_row_o = QHBoxLayout()
        key_row_o.setSpacing(6)
        self._openai_key = QLineEdit()
        self._openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_key.setPlaceholderText("sk-...")
        self._openai_key.setText(load_openai_api_key())
        self._openai_key.setStyleSheet(_INPUT_QSS)
        key_row_o.addWidget(self._openai_key)
        show_o = QCheckBox("Show")
        show_o.setStyleSheet("color: #585b70;")
        show_o.toggled.connect(
            lambda on: self._openai_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        key_row_o.addWidget(show_o)
        layout.addLayout(key_row_o)

        model_label_o = QLabel("Model")
        model_label_o.setStyleSheet("color: #a6adc8;")
        layout.addWidget(model_label_o)

        model_group_o = QVBoxLayout()
        model_group_o.setSpacing(6)
        for model_id, display_name, description in AVAILABLE_OPENAI_MODELS:
            btn = QPushButton(f"{display_name}  —  {description}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, mid=model_id: self._select_openai_model(mid))
            self._openai_model_buttons.append((model_id, btn))
            model_group_o.addWidget(btn)
        layout.addLayout(model_group_o)

        layout.addSpacing(8)

        # ── Gemini section ─────────────────────────────────────────────────
        self._gemini_header = _ProviderHeader("Google")
        self._gemini_header.clicked.connect(lambda: self._set_provider("gemini"))
        layout.addWidget(self._gemini_header)

        key_label_g = QLabel("API Key")
        key_label_g.setStyleSheet("color: #a6adc8;")
        layout.addWidget(key_label_g)

        key_row_g = QHBoxLayout()
        key_row_g.setSpacing(6)
        self._gemini_key = QLineEdit()
        self._gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._gemini_key.setPlaceholderText("AIza...")
        self._gemini_key.setText(load_gemini_api_key())
        self._gemini_key.setStyleSheet(_INPUT_QSS)
        key_row_g.addWidget(self._gemini_key)
        show_g = QCheckBox("Show")
        show_g.setStyleSheet("color: #585b70;")
        show_g.toggled.connect(
            lambda on: self._gemini_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        key_row_g.addWidget(show_g)
        layout.addLayout(key_row_g)

        model_label_g = QLabel("Model")
        model_label_g.setStyleSheet("color: #a6adc8;")
        layout.addWidget(model_label_g)

        model_group_g = QVBoxLayout()
        model_group_g.setSpacing(6)
        for model_id, display_name, description in AVAILABLE_GEMINI_MODELS:
            btn = QPushButton(f"{display_name}  —  {description}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, mid=model_id: self._select_gemini_model(mid))
            self._gemini_model_buttons.append((model_id, btn))
            model_group_g.addWidget(btn)
        layout.addLayout(model_group_g)

        layout.addSpacing(12)

        # ── Save / Cancel ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { padding: 4px 16px; color: #f38ba8; font-size: 11pt; }"
            "QPushButton:hover { background-color: #313244; color: #f38ba8; }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            "QPushButton { padding: 4px 16px; color: #a6e3a1; font-size: 11pt; }"
            "QPushButton:hover { background-color: #313244; }"
        )
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        # Install event filters so clicking anywhere in a section activates it
        self._anthropic_key.installEventFilter(self)
        self._openai_key.installEventFilter(self)
        self._gemini_key.installEventFilter(self)

        # Initial render
        self._refresh_ui()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fix_layout)

    def _fix_layout(self):
        self._refresh_ui()
        self.layout().activate()
        self.adjustSize()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if obj is self._anthropic_key:
                self._set_provider("anthropic")
            elif obj is self._openai_key:
                self._set_provider("openai")
            elif obj is self._gemini_key:
                self._set_provider("gemini")
        return super().eventFilter(obj, event)

    # ── Provider selection ─────────────────────────────────────────────────

    def _set_provider(self, provider: str):
        self._active_provider = provider
        self._refresh_ui()

    def _select_anthropic_model(self, model_id: str):
        self._selected_anthropic_model = model_id
        self._set_provider("anthropic")

    def _select_openai_model(self, model_id: str):
        self._selected_openai_model = model_id
        self._set_provider("openai")

    def _select_gemini_model(self, model_id: str):
        self._selected_gemini_model = model_id
        self._set_provider("gemini")

    def _refresh_ui(self):
        anthropic_active = self._active_provider == "anthropic"
        openai_active = self._active_provider == "openai"
        gemini_active = self._active_provider == "gemini"

        # Section headers
        self._anthropic_header.setStyleSheet(
            "font-size: 12pt; font-weight: bold; color: "
            + ("#fab387;" if anthropic_active else "#45475a;")
        )
        self._openai_header.setStyleSheet(
            "font-size: 12pt; font-weight: bold; color: "
            + ("#a6e3a1;" if openai_active else "#45475a;")
        )
        self._gemini_header.setStyleSheet(
            "font-size: 12pt; font-weight: bold; color: "
            + ("#89b4fa;" if gemini_active else "#45475a;")
        )

        # Model buttons — Anthropic (orange when selected)
        for mid, btn in self._anthropic_model_buttons:
            if mid == self._selected_anthropic_model and anthropic_active:
                btn.setStyleSheet(_MODEL_BTN_ON)
            else:
                btn.setStyleSheet(_MODEL_BTN_OFF)

        # Model buttons — OpenAI (green when selected)
        for mid, btn in self._openai_model_buttons:
            if mid == self._selected_openai_model and openai_active:
                btn.setStyleSheet(_MODEL_BTN_ON_GREEN)
            else:
                btn.setStyleSheet(_MODEL_BTN_OFF)

        # Model buttons — Gemini (blue when selected)
        for mid, btn in self._gemini_model_buttons:
            if mid == self._selected_gemini_model and gemini_active:
                btn.setStyleSheet(_MODEL_BTN_ON_BLUE)
            else:
                btn.setStyleSheet(_MODEL_BTN_OFF)

    def _save(self):
        save_api_key(self._anthropic_key.text().strip())
        save_model(self._selected_anthropic_model)
        save_openai_api_key(self._openai_key.text().strip())
        save_openai_model(self._selected_openai_model)
        save_gemini_api_key(self._gemini_key.text().strip())
        save_gemini_model(self._selected_gemini_model)
        save_provider(self._active_provider)
        self.accept()


class HomeView(QWidget):
    """Course and lecture manager — main landing screen."""

    lecture_opened = Signal(str, str, str)  # course_id, lecture_id, group_id

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
        bottom_bar.setFixedHeight(44)
        bottom_bar.setStyleSheet("background-color: #181825;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(16, 4, 16, 4)

        settings_btn = QPushButton("Settings")
        settings_btn.setStyleSheet(
            "QPushButton { color: #585b70; background: transparent; padding: 4px 12px; }"
            "QPushButton:hover { color: #cdd6f4; }"
        )
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._open_settings)
        bottom_layout.addWidget(settings_btn)

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
            groups_data = []
            for group in storage.list_groups(course.id):
                group_lectures = storage.list_lectures(course.id, group_id=group.id)
                groups_data.append((group, group_lectures))
            section = _CourseSection(course.id, course.name, lectures, groups_data, color, self._container)
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
                _warning(self, "Name too long", f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
                prefill = name
                continue
            break
        storage.create_course(name.strip())
        self.refresh()

    def _open_settings(self):
        _SettingsDialog(self).exec()
