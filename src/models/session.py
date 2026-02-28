"""Data classes for courses and lecture sessions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug (lowercase, hyphens, no specials)."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-") or "untitled"


@dataclass
class Course:
    id: str
    name: str
    created_at: str
    order: int = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "created_at": self.created_at, "order": self.order}

    @classmethod
    def from_dict(cls, data: dict) -> Course:
        return cls(id=data["id"], name=data["name"], created_at=data["created_at"], order=data.get("order", 0))


@dataclass
class Group:
    id: str
    name: str
    created_at: str
    order: int = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "created_at": self.created_at, "order": self.order}

    @classmethod
    def from_dict(cls, data: dict) -> Group:
        return cls(id=data["id"], name=data["name"], created_at=data["created_at"], order=data.get("order", 0))


@dataclass
class FollowupMessage:
    role: str  # "user" | "assistant"
    text: str

    def to_dict(self) -> dict:
        return {"role": self.role, "text": self.text}

    @classmethod
    def from_dict(cls, data: dict) -> FollowupMessage:
        return cls(role=data["role"], text=data["text"])


@dataclass
class ReviewItem:
    note_type: str
    original: str
    response: str
    followups: list[FollowupMessage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "note_type": self.note_type,
            "original": self.original,
            "response": self.response,
            "followups": [f.to_dict() for f in self.followups],
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReviewItem:
        return cls(
            note_type=data["note_type"],
            original=data["original"],
            response=data["response"],
            followups=[FollowupMessage.from_dict(f) for f in data.get("followups", [])],
        )


@dataclass
class SlideData:
    raw_notes: str = ""
    review: list[ReviewItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "raw_notes": self.raw_notes,
            "review": [r.to_dict() for r in self.review],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SlideData:
        return cls(
            raw_notes=data.get("raw_notes", ""),
            review=[ReviewItem.from_dict(r) for r in data.get("review", [])],
        )


@dataclass
class Session:
    id: str
    title: str
    pdf_filename: str
    created_at: str
    updated_at: str
    slides: dict[str, SlideData] = field(default_factory=dict)
    order: int = 0
    finalized: bool = False
    finalized_notes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "pdf_filename": self.pdf_filename,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "slides": {k: v.to_dict() for k, v in self.slides.items()},
            "order": self.order,
        }
        if self.finalized:
            d["finalized"] = True
            d["finalized_notes"] = self.finalized_notes
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        slides = {}
        for k, v in data.get("slides", {}).items():
            slides[k] = SlideData.from_dict(v)
        return cls(
            id=data["id"],
            title=data["title"],
            pdf_filename=data.get("pdf_filename", "slides.pdf"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            slides=slides,
            order=data.get("order", 0),
            finalized=data.get("finalized", False),
            finalized_notes=data.get("finalized_notes", {}),
        )
