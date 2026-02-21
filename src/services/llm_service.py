"""LLM provider abstraction and background review worker."""

from __future__ import annotations

from abc import ABC, abstractmethod

from PySide6.QtCore import QThread, Signal

from src.models.session import ReviewItem
from src.services.note_parser import ParsedNote


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def review_notes(
        self,
        pdf_base64: str,
        slide_number: int,
        notes: list[ParsedNote],
    ) -> list[ReviewItem]:
        """Send a slide's notes + the full PDF to the LLM. Return ReviewItems."""
        ...


class ReviewWorker(QThread):
    """Process slides sequentially so prompt caching kicks in after slide 1."""

    slide_reviewed = Signal(str, list)   # slide_key, list[ReviewItem]
    slide_error = Signal(str, str)       # slide_key, error message
    all_done = Signal()

    def __init__(
        self,
        provider: LLMProvider,
        pdf_base64: str,
        slides_to_review: dict[str, list[ParsedNote]],
        parent=None,
    ):
        super().__init__(parent)
        self._provider = provider
        self._pdf_base64 = pdf_base64
        self._slides = slides_to_review  # {slide_key: [ParsedNote, ...]}
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        for slide_key, notes in self._slides.items():
            if self._cancelled:
                break
            try:
                items = self._provider.review_notes(
                    self._pdf_base64,
                    int(slide_key),
                    notes,
                )
                if not self._cancelled:
                    self.slide_reviewed.emit(slide_key, items)
            except Exception as exc:
                if not self._cancelled:
                    self.slide_error.emit(slide_key, str(exc))
        if not self._cancelled:
            self.all_done.emit()
