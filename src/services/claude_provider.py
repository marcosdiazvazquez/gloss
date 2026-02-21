"""Anthropic Claude API implementation of LLMProvider."""

from __future__ import annotations

import anthropic

from src.models.session import ReviewItem
from src.services.llm_service import LLMProvider
from src.services.note_parser import ParsedNote

from src.utils.config import DEFAULT_MODEL

SYSTEM_PROMPT = """\
You are a study assistant helping a student review their lecture notes.
You will receive:
1. The full lecture PDF
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
when possible. You have the full lecture PDF for broader context but focus on the \
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


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = ""):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model or DEFAULT_MODEL

    def review_notes(
        self,
        pdf_base64: str,
        slide_number: int,
        notes: list[ParsedNote],
    ) -> list[ReviewItem]:
        # Build the notes section
        notes_text = []
        for i, note in enumerate(notes, 1):
            label = NOTE_TYPE_LABELS.get(note.note_type, "GENERAL")
            notes_text.append(f"Note {i} ({label}):\n{note.text}")

        user_text = (
            f"The student is on SLIDE {slide_number} of this lecture.\n\n"
            + "\n\n".join(notes_text)
        )

        message = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64,
                            },
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": user_text,
                        },
                    ],
                }
            ],
        )

        response_text = message.content[0].text
        return self._parse_response(notes, response_text)

    def _parse_response(
        self,
        notes: list[ParsedNote],
        response_text: str,
    ) -> list[ReviewItem]:
        """Split Claude's response by --- delimiters, matching to notes."""
        parts = [p.strip() for p in response_text.split("\n---\n")]

        # If splitting didn't produce enough parts, try just "---"
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
