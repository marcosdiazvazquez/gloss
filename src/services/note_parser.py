"""Parse markup-annotated notes into structured blocks."""

from __future__ import annotations

from dataclasses import dataclass

SYMBOL_MAP = {
    "-": "general",
    "?": "question",
    "~": "uncertain",
    "!": "important",
}


@dataclass
class ParsedNote:
    note_type: str  # "general", "question", "uncertain", "important"
    text: str       # note text with leading symbol stripped


def parse_notes(raw_notes: str) -> list[ParsedNote]:
    """Parse raw note text into structured blocks.

    Rules:
    - A line starting with a symbol (-?~!) begins a new block
    - Continuation lines (no symbol) append to the current block
    - Empty lines separate blocks (reset current block)
    """
    if not raw_notes or not raw_notes.strip():
        return []

    notes: list[ParsedNote] = []
    current_type: str | None = None
    current_lines: list[str] = []

    for line in raw_notes.split("\n"):
        stripped = line.strip()

        # Empty line — flush current block
        if not stripped:
            if current_type and current_lines:
                notes.append(ParsedNote(
                    note_type=current_type,
                    text="\n".join(current_lines).strip(),
                ))
                current_type = None
                current_lines = []
            continue

        # Check if line starts with a symbol
        first_char = stripped[0]
        if first_char in SYMBOL_MAP:
            # Flush previous block
            if current_type and current_lines:
                notes.append(ParsedNote(
                    note_type=current_type,
                    text="\n".join(current_lines).strip(),
                ))
            # Start new block — strip symbol and optional space
            current_type = SYMBOL_MAP[first_char]
            rest = stripped[1:]
            if rest.startswith(" "):
                rest = rest[1:]
            current_lines = [rest] if rest else []
        elif current_type:
            # Continuation line
            current_lines.append(stripped)

    # Flush final block
    if current_type and current_lines:
        notes.append(ParsedNote(
            note_type=current_type,
            text="\n".join(current_lines).strip(),
        ))

    return notes
