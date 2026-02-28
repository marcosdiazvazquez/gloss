"""Review card widget — displays a single note with Claude's response."""

from __future__ import annotations

import markdown as md_lib

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Signal, Qt

from src.models.session import FollowupMessage

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

# Qt's rich-text engine supports a CSS subset — keep rules it understands
_RESPONSE_CSS = """
<style>
p           { margin: 0 0 6px 0; }
ul, ol      { margin: 4px 0 6px 0; padding-left: 18px; }
li          { margin: 2px 0; }
code        { background-color: #313244; color: #cdd6f4; }
strong      { font-weight: bold; }
em          { font-style: italic; }
h1,h2,h3   { color: #cba6f7; margin: 8px 0 4px 0; }
</style>
"""

def _to_html(text: str) -> str:
    body = md_lib.markdown(text, extensions=["fenced_code", "nl2br"])
    return _RESPONSE_CSS + body


def _make_sep() -> QFrame:
    """Return a subtle horizontal rule styled for the dark theme."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFrameShadow(QFrame.Shadow.Plain)
    sep.setStyleSheet("color: #313244; border: none; background-color: #313244; max-height: 1px;")
    sep.setFixedHeight(1)
    return sep


_MIN_INPUT_H = 36   # ≈ one text line
_MAX_INPUT_H = 200  # cap so the input doesn't swallow the whole card


class _FollowupInput(QTextEdit):
    """Auto-expanding text input. Grows taller as the user types; submits on Enter."""

    submitted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._want_h: int = _MIN_INPUT_H
        self.document().documentLayout().documentSizeChanged.connect(
            self._on_doc_size_changed
        )

    # -- Dynamic height -------------------------------------------------

    def _on_doc_size_changed(self, new_size):
        # Measure border+padding from live geometry so we never have to
        # hard-code what the stylesheet contributes.
        overhead = self.height() - self.viewport().height()
        if overhead <= 0:
            overhead = 10  # fallback before first show: 1px border×2 + 4px padding×2
        h = max(_MIN_INPUT_H, min(_MAX_INPUT_H, int(new_size.height()) + overhead))
        if h != self._want_h:
            self._want_h = h
            self.updateGeometry()

    def sizeHint(self):
        sh = super().sizeHint()
        return sh.__class__(sh.width(), self._want_h)

    def minimumSizeHint(self):
        sh = super().minimumSizeHint()
        return sh.__class__(sh.width(), self._want_h)

    # -- Key handling ---------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)  # Shift+Enter → newline
            else:
                self.submitted.emit()
        else:
            super().keyPressEvent(event)


class ReviewCard(QWidget):
    """Single note + Claude response card with regenerate and follow-up support."""

    regenerate_requested = Signal()
    followup_submitted = Signal(str)  # question text

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

        # -- Separator between note and response (always visible) --
        layout.addWidget(_make_sep())

        # -- Response area --
        self._response = QLabel()
        self._response.setWordWrap(True)
        self._response.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._response.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._response.setContentsMargins(34, 0, 0, 0)
        layout.addWidget(self._response)

        # -- Button row: Regenerate + Follow up --
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

        self._followup_btn = QPushButton("Follow up")
        self._followup_btn.setStyleSheet(
            "QPushButton { padding: 2px 10px; color: #585b70; border: 1px solid #45475a; border-radius: 4px; }"
            "QPushButton:hover { color: #cdd6f4; border-color: #89b4fa; }"
        )
        self._followup_btn.clicked.connect(self._toggle_followup)
        self._followup_btn.hide()
        btn_row.addWidget(self._followup_btn)

        layout.addLayout(btn_row)

        # -- Follow-up area (hidden until activated) --
        self._followup_area = QWidget()
        self._followup_area.hide()
        fu_layout = QVBoxLayout(self._followup_area)
        fu_layout.setContentsMargins(34, 4, 0, 0)
        fu_layout.setSpacing(8)

        fu_layout.addWidget(_make_sep())

        self._thread_layout = QVBoxLayout()
        self._thread_layout.setSpacing(8)
        fu_layout.addLayout(self._thread_layout)

        input_row = QHBoxLayout()

        self._followup_input = _FollowupInput()
        self._followup_input.setPlaceholderText("Ask a follow-up question...")
        self._followup_input.setStyleSheet(
            "QTextEdit { background-color: #313244; border: 1px solid #45475a; "
            "border-radius: 4px; padding: 4px 8px; color: #cdd6f4; }"
            "QTextEdit:focus { border-color: #89b4fa; }"
        )
        self._followup_input.submitted.connect(self._submit_followup)
        input_row.addWidget(self._followup_input, 1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; color: #89b4fa; border: 1px solid #45475a; border-radius: 4px; }"
            "QPushButton:hover { background-color: #313244; }"
            "QPushButton:disabled { color: #45475a; border-color: #313244; }"
        )
        self._send_btn.clicked.connect(self._submit_followup)
        input_row.addWidget(self._send_btn)

        fu_layout.addLayout(input_row)

        self._followup_error = QLabel()
        self._followup_error.setStyleSheet("color: #f38ba8;")
        self._followup_error.setWordWrap(True)
        self._followup_error.hide()
        fu_layout.addWidget(self._followup_error)

        layout.addWidget(self._followup_area)

        self.setStyleSheet(
            "ReviewCard { background-color: #181825; border-radius: 8px; }"
        )

    def set_loading(self):
        self._response.setStyleSheet("color: #585b70;")
        self._response.setText("Reviewing...")
        self._regen_btn.hide()
        self._followup_btn.hide()

    def set_response(self, text: str):
        self._response.setStyleSheet("color: #cdd6f4;")
        self._response.setText(_to_html(text))
        self._regen_btn.show()
        self._followup_btn.show()

    def set_error(self, message: str):
        self._response.setStyleSheet("color: #f38ba8;")
        self._response.setText(f"Error: {message}")
        self._regen_btn.show()
        self._regen_btn.setText("Retry")

    def _toggle_followup(self):
        visible = self._followup_area.isVisible()
        self._followup_area.setVisible(not visible)
        if not visible:
            self._followup_input.setFocus()

    def _submit_followup(self):
        text = self._followup_input.toPlainText().strip()  # toPlainText works on QTextEdit
        if not text:
            return
        self._followup_input.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._send_btn.setText("Sending...")
        self._followup_error.hide()
        self.followup_submitted.emit(text)

    def load_followups(self, followups: list[FollowupMessage]):
        """Restore cached follow-up history on card init."""
        if not followups:
            return
        self._followup_area.show()
        i = 0
        while i < len(followups):
            user_msg = followups[i]
            asst_msg = followups[i + 1] if i + 1 < len(followups) else None
            if user_msg.role == "user":
                question = user_msg.text
                answer = asst_msg.text if asst_msg and asst_msg.role == "assistant" else ""
                self._append_exchange(question, answer)
            i += 2

    def add_followup_response(self, question: str, answer: str):
        """Append a new completed exchange and re-enable the input."""
        self._append_exchange(question, answer)
        self._followup_input.clear()
        self._followup_input.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._send_btn.setText("Send")

    def set_followup_error(self, msg: str):
        self._followup_error.setText(f"Error: {msg}")
        self._followup_error.show()
        self._followup_input.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._send_btn.setText("Send")

    def _append_exchange(self, question: str, answer: str):
        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(4)

        q_label = QLabel(f"You: {question}")
        q_label.setWordWrap(True)
        q_label.setStyleSheet("color: #585b70;")
        q_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c_layout.addWidget(q_label)

        a_label = QLabel()
        a_label.setWordWrap(True)
        a_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        a_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        a_label.setText(_to_html(answer))
        c_layout.addWidget(a_label)

        self._thread_layout.addWidget(container)
