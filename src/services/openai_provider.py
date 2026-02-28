"""OpenAI API implementation of LLMProvider."""

from __future__ import annotations

import base64
import io

from openai import OpenAI
from pypdf import PdfReader

from src.models.session import ReviewItem, FollowupMessage
from src.services.llm_service import LLMProvider
from src.services.note_parser import ParsedNote
from src.utils.config import OPENAI_DEFAULT_MODEL

# Models that require max_completion_tokens instead of max_tokens
_COMPLETION_TOKENS_MODELS = {"o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o3-pro"}


def _max_tokens_param(model: str, value: int) -> dict:
    """Return the correct max tokens parameter for the given model."""
    base = model.split("-")[0] + ("-".join(model.split("-")[:2]) if "-" in model else "")
    # Check if any prefix matches
    for prefix in _COMPLETION_TOKENS_MODELS:
        if model == prefix or model.startswith(prefix + "-"):
            return {"max_completion_tokens": value}
    return {"max_tokens": value}

SYSTEM_PROMPT = """\
You are a study assistant helping a student review their lecture notes.
You will receive:
1. The full lecture content as extracted text, slide by slide
2. A specific slide number the student was on
3. One or more student notes about that slide, each with a type indicator

Your role depends on the note type:
- GENERAL: Check against the slide content for accuracy. If the note contains \
a misunderstanding, gently correct it with specifics from the slide. If correct, \
briefly confirm.
- QUESTION: Answer using the slide content as primary context. Be thorough but \
concise. If the slide doesn't contain enough info, say so and provide what you can.
- UNCERTAIN: The student is unsure. Compare their understanding against the slide. \
If wrong, gently correct with specifics. If right, confirm and reinforce.
- IMPORTANT: The student flagged this as high-priority. Provide a focused summary \
of the key concepts from this slide that relate to their note.

Keep responses focused and educational. Reference the slide content specifically \
when possible. Use the full lecture text for broader context but focus on the \
specific slide referenced.

FORMAT: You will receive multiple notes separated by numbered headers. Respond to \
each note in the same order, separating your responses with a line containing only \
"---". Do NOT include the note headers or numbers in your response — just the \
responses separated by ---."""

NOTE_TYPE_LABELS = {
    "general": "GENERAL",
    "question": "QUESTION",
    "uncertain": "UNCERTAIN",
    "important": "IMPORTANT",
}


def _extract_pdf_text(pdf_base64: str) -> list[str]:
    """Return a list of page text strings (one per page) from a base64 PDF."""
    pdf_bytes = base64.b64decode(pdf_base64)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [page.extract_text() or "" for page in reader.pages]


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = ""):
        self._client = OpenAI(api_key=api_key)
        self._model = model or OPENAI_DEFAULT_MODEL
        self._page_texts: list[str] | None = None

    def review_notes(
        self,
        pdf_base64: str,
        slide_number: int,
        notes: list[ParsedNote],
    ) -> list[ReviewItem]:
        # Extract text once and cache across slides (same pdf_base64 per session)
        if self._page_texts is None:
            self._page_texts = _extract_pdf_text(pdf_base64)

        # Build full lecture context
        full_text = "\n\n".join(
            f"[Slide {i + 1}]\n{text}" if text.strip() else f"[Slide {i + 1}]\n(no extractable text)"
            for i, text in enumerate(self._page_texts)
        )

        # Build the notes section
        notes_text = []
        for i, note in enumerate(notes, 1):
            label = NOTE_TYPE_LABELS.get(note.note_type, "GENERAL")
            notes_text.append(f"Note {i} ({label}):\n{note.text}")

        user_text = (
            f"LECTURE CONTENT:\n{full_text}\n\n"
            f"The student is on SLIDE {slide_number} of this lecture.\n\n"
            + "\n\n".join(notes_text)
        )

        response = self._client.chat.completions.create(
            model=self._model,
            **_max_tokens_param(self._model, 4096),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        )

        response_text = response.choices[0].message.content or ""
        return self._parse_response(notes, response_text)

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
        if self._page_texts is None:
            self._page_texts = _extract_pdf_text(pdf_base64)

        full_text = "\n\n".join(
            f"[Slide {i + 1}]\n{text}" if text.strip() else f"[Slide {i + 1}]\n(no extractable text)"
            for i, text in enumerate(self._page_texts)
        )

        label = NOTE_TYPE_LABELS.get(note_type, "GENERAL")
        user_text = (
            f"LECTURE CONTENT:\n{full_text}\n\n"
            f"The student is on SLIDE {slide_number} of this lecture.\n\n"
            f"Note ({label}):\n{original_note}"
        )

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": initial_response},
        ]

        for msg in history:
            messages.append({"role": msg.role, "content": msg.text})
        messages.append({"role": "user", "content": question})

        response = self._client.chat.completions.create(
            model=self._model,
            **_max_tokens_param(self._model, 2048),
            messages=messages,
        )
        return response.choices[0].message.content or ""

    def _parse_response(
        self,
        notes: list[ParsedNote],
        response_text: str,
    ) -> list[ReviewItem]:
        parts = [p.strip() for p in response_text.split("\n---\n")]
        if len(parts) < len(notes):
            parts = [p.strip() for p in response_text.split("---")]

        items = []
        for i, note in enumerate(notes):
            response = parts[i] if i < len(parts) else "(No response received)"
            items.append(ReviewItem(
                note_type=note.note_type,
                original=note.text,
                response=response,
            ))
        return items
