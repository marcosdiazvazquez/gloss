"""Review card widget — displays a single note with Claude's response."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PySide6.QtCore import Signal, Qt

# Catppuccin Mocha colors matching notes_editor.py
TYPE_COLORS = {
    "general": "#a6e3a1",   # green
    "question": "#89b4fa",  # blue
    "uncertain": "#fab387", # orange
    "important": "#f38ba8", # red
}

TYPE_SYMBOLS = {
    "general": "-",
    "question": "?",
    "uncertain": "~",
    "important": "!",
}


class ReviewCard(QWidget):
    """Single note + Claude response card with regenerate support."""

    regenerate_requested = Signal()

    def __init__(self, note_type: str, original_text: str, parent=None):
        super().__init__(parent)
        self._note_type = note_type
        self._original_text = original_text
        self._init_ui()
        self.set_loading()

    def _init_ui(self):
        color = TYPE_COLORS.get(self._note_type, "#cdd6f4")
        symbol = TYPE_SYMBOLS.get(self._note_type, "-")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # -- Badge + original note --
        header = QHBoxLayout()
        header.setSpacing(10)

        badge = QLabel(symbol)
        badge.setFixedWidth(24)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 18pt; "
            f"background-color: #313244; border-radius: 4px; padding: 2px;"
        )
        header.addWidget(badge)

        note_label = QLabel(self._original_text)
        note_label.setWordWrap(True)
        note_label.setStyleSheet(f"color: {color};")
        note_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header.addWidget(note_label, 1)

        layout.addLayout(header)

        # -- Response area --
        self._response_label = QLabel()
        self._response_label.setWordWrap(True)
        self._response_label.setStyleSheet(
            "color: #cdd6f4; padding-left: 34px;"
        )
        self._response_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._response_label)

        # -- Regenerate button (hidden until response loaded) --
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(34, 0, 0, 0)
        btn_row.addStretch()
        self._regen_btn = QPushButton("Regenerate")
        self._regen_btn.setStyleSheet(
            "QPushButton { padding: 2px 10px; color: #585b70; border: 1px solid #45475a; border-radius: 4px; }"
            "QPushButton:hover { color: #cdd6f4; border-color: #89b4fa; }"
        )
        self._regen_btn.clicked.connect(self.regenerate_requested.emit)
        self._regen_btn.hide()
        btn_row.addWidget(self._regen_btn)
        layout.addLayout(btn_row)

        self.setStyleSheet(
            "ReviewCard { background-color: #181825; border-radius: 8px; }"
        )

    def set_loading(self):
        self._response_label.setStyleSheet(
            "color: #585b70; padding-left: 34px;"
        )
        self._response_label.setText("Reviewing...")
        self._regen_btn.hide()

    def set_response(self, text: str):
        self._response_label.setStyleSheet(
            "color: #cdd6f4; padding-left: 34px;"
        )
        self._response_label.setText(text)
        self._regen_btn.show()

    def set_error(self, message: str):
        self._response_label.setStyleSheet(
            "color: #f38ba8; padding-left: 34px;"
        )
        self._response_label.setText(f"Error: {message}")
        self._regen_btn.show()
        self._regen_btn.setText("Retry")
