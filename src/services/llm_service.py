"""LLM provider abstraction and background review worker."""

from __future__ import annotations

from abc import ABC, abstractmethod

from PySide6.QtCore import QThread, Signal

from src.models.session import ReviewItem, FollowupMessage
from src.services.note_parser import ParsedNote

_BILLING_KEYWORDS = (
    "billing",
    "credit balance",
    "insufficient_quota",
    "you exceeded your current quota",
    "payment required",
    "resource_exhausted",
    "quota exceeded",
)


def _friendly_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if any(kw in msg for kw in _BILLING_KEYWORDS):
        return (
            "Your API credits are exhausted. Please top up your account balance "
            "and try again.\n\n"
            f"Details: {exc}"
        )
    return str(exc)


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

    @abstractmethod
    def follow_up(
        self,
        pdf_base64: str,
        slide_number: int,
        note_type: str,
        original_note: str,
        initial_response: str,
        history: list[FollowupMessage],
        question: str,
    ) -> str:
        """Continue a conversation about a specific note. Return the response text."""
        ...


class FollowupWorker(QThread):
    """Send a single follow-up question to the LLM in the background."""

    done = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        provider: LLMProvider,
        pdf_base64: str,
        slide_number: int,
        note_type: str,
        original_note: str,
        initial_response: str,
        history: list[FollowupMessage],
        question: str,
        parent=None,
    ):
        super().__init__(parent)
        self._provider = provider
        self._pdf_base64 = pdf_base64
        self._slide_number = slide_number
        self._note_type = note_type
        self._original_note = original_note
        self._initial_response = initial_response
        self._history = history
        self._question = question

    def run(self):
        try:
            result = self._provider.follow_up(
                self._pdf_base64,
                self._slide_number,
                self._note_type,
                self._original_note,
                self._initial_response,
                self._history,
                self._question,
            )
            self.done.emit(result)
        except Exception as exc:
            self.error.emit(_friendly_error(exc))


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
                    self.slide_error.emit(slide_key, _friendly_error(exc))
        if not self._cancelled:
            self.all_done.emit()
