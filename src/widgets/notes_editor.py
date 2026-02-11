"""Notes editor with markup syntax highlighting and ghost placeholders."""

from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
import re

# Catppuccin Mocha colors for markup symbols
SYMBOL_COLORS = {
    "-": QColor("#a6e3a1"),  # green — general note
    "?": QColor("#89b4fa"),  # blue — question
    "~": QColor("#fab387"),  # orange — uncertain
    "!": QColor("#f38ba8"),  # red — important
}

GHOST_COLOR = QColor("#585b70")

PLACEHOLDER_TEXT = (
    "  - your notes here\n"
    "  ? questions you have\n"
    "  ~ things you're unsure about\n"
    "  ! important stuff"
)

INLINE_HINT = "  - note  |  ? question  |  ~ unsure  |  ! important"


class _NoteHighlighter(QSyntaxHighlighter):
    """Colors the leading markup symbol on each line."""

    _pattern = re.compile(r"^(\s*)([-?~!])(\s?)")

    def highlightBlock(self, text: str):
        m = self._pattern.match(text)
        if not m:
            return
        sym = m.group(2)
        color = SYMBOL_COLORS.get(sym)
        if not color:
            return
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        fmt.setFontWeight(QFont.Weight.Bold)
        start = m.start(2)
        length = m.end(2) - start
        self.setFormat(start, length, fmt)


class NotesEditor(QPlainTextEdit):
    """Per-slide note editor with ghost placeholder and inline hints."""

    notes_changed = Signal(str)  # emitted on every text change (raw text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("")  # we paint our own
        self._highlighter = _NoteHighlighter(self.document())

        # Auto-save debounce
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(lambda: self.notes_changed.emit(self.toPlainText()))

        # Extra line spacing
        fmt = QTextBlockFormat()
        fmt.setLineHeight(160, 1)  # 1 = ProportionalHeight (160%)
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()
        self.setTextCursor(cursor)

        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(lambda: self.viewport().update())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            return  # ignore Tab — no tab characters in notes
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            fmt = cursor.blockFormat()
            block = cursor.block()
            has_text = block.text().strip() != ""

            if has_text and cursor.atBlockEnd():
                # After a note: insert blank separator + new line
                cursor.insertBlock(fmt)
                cursor.insertBlock(fmt)
            else:
                cursor.insertBlock(fmt)

            self.setTextCursor(cursor)
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.viewport().update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.viewport().update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.viewport().update()

    def _on_text_changed(self):
        self._save_timer.start()
        self.viewport().update()  # repaint to toggle placeholder/hint visibility

    # -- Ghost placeholder & inline hint ------------------------------------

    def paintEvent(self, event):
        super().paintEvent(event)

        if not self.hasFocus():
            return

        if self.toPlainText():
            # If there's text, check if current line is empty for inline hint
            cursor = self.textCursor()
            block = cursor.block()
            if block.text().strip() == "" and cursor.atBlockEnd():
                self._paint_inline_hint(block)
        else:
            # No text at all — show full ghost placeholder
            self._paint_placeholder()

    def _paint_placeholder(self):
        painter = QPainter(self.viewport())
        painter.setPen(GHOST_COLOR)
        painter.setFont(self.font())

        # Use the first block's geometry so ghost text aligns with real text
        block = self.document().firstBlock()
        rect = self.blockBoundingGeometry(block).translated(self.contentOffset())
        doc_margin = self.document().documentMargin()
        fm = painter.fontMetrics()
        x = int(rect.left() + doc_margin)
        y = int(rect.top())

        for line in PLACEHOLDER_TEXT.split("\n"):
            painter.drawText(x, y + fm.ascent(), line)
            y += fm.lineSpacing()
        painter.end()

    def _paint_inline_hint(self, block):
        rect = self.blockBoundingGeometry(block).translated(self.contentOffset())
        if rect.height() <= 0:
            return
        painter = QPainter(self.viewport())
        painter.setPen(GHOST_COLOR)
        painter.setFont(self.font())
        fm = painter.fontMetrics()
        x = int(rect.left() + self.document().documentMargin())
        y = int(rect.top() + fm.ascent())
        painter.drawText(x, y, INLINE_HINT)
        painter.end()

    # -- Public API ---------------------------------------------------------

    def set_notes(self, text: str):
        """Set editor content without triggering the save signal."""
        self._save_timer.stop()
        self.blockSignals(True)
        self.setPlainText(text)
        self._apply_line_spacing()
        self.blockSignals(False)
        self.viewport().update()

    def _apply_line_spacing(self):
        fmt = QTextBlockFormat()
        fmt.setLineHeight(160, 1)  # 1 = ProportionalHeight (160%)
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def get_notes(self) -> str:
        return self.toPlainText()
