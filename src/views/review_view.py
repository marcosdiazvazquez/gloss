from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt


class ReviewView(QWidget):
    """LLM review display — shows Claude's feedback on student notes."""

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._course_id: str = ""
        self._lecture_id: str = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Placeholder — will be replaced with review cards
        placeholder = QLabel("Review View")
        placeholder.setStyleSheet("color: #585b70;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(placeholder)

    def load(self, course_id: str, lecture_id: str):
        self._course_id = course_id
        self._lecture_id = lecture_id
