"""Filesystem CRUD for courses and lecture sessions."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from src.models.session import Course, Session, SlideData, slugify
from src.utils.config import COURSES_DIR


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# -- Courses ------------------------------------------------------------------


def create_course(name: str) -> Course:
    course_id = slugify(name)
    course_dir = COURSES_DIR / course_id
    # Deduplicate if slug already exists
    counter = 2
    while course_dir.exists():
        course_id = f"{slugify(name)}-{counter}"
        course_dir = COURSES_DIR / course_id
        counter += 1

    course_dir.mkdir(parents=True)
    (course_dir / "lectures").mkdir()

    now = datetime.now().isoformat(timespec="seconds")
    existing = list_courses()
    order = max((c.order for c in existing), default=-1) + 1
    course = Course(id=course_id, name=name, created_at=now, order=order)
    _write_json(course_dir / "course.json", course.to_dict())
    return course


def list_courses() -> list[Course]:
    if not COURSES_DIR.exists():
        return []
    courses = []
    for d in COURSES_DIR.iterdir():
        cj = d / "course.json"
        if d.is_dir() and cj.exists():
            courses.append(Course.from_dict(_read_json(cj)))
    courses.sort(key=lambda c: (c.order, c.created_at))
    return courses


def rename_course(course_id: str, new_name: str) -> None:
    course_dir = COURSES_DIR / course_id
    cj = course_dir / "course.json"
    if cj.exists():
        data = _read_json(cj)
        data["name"] = new_name
        _write_json(cj, data)


def reorder_courses(ordered_ids: list[str]) -> None:
    for i, cid in enumerate(ordered_ids):
        cj = COURSES_DIR / cid / "course.json"
        if cj.exists():
            data = _read_json(cj)
            data["order"] = i
            _write_json(cj, data)


def delete_course(course_id: str) -> None:
    course_dir = COURSES_DIR / course_id
    if course_dir.exists():
        shutil.rmtree(course_dir)


# -- Lectures ------------------------------------------------------------------


def create_lecture(course_id: str, title: str, pdf_path: str) -> Session:
    lecture_id = slugify(title)
    lectures_dir = COURSES_DIR / course_id / "lectures"
    lecture_dir = lectures_dir / lecture_id
    # Deduplicate
    counter = 2
    while lecture_dir.exists():
        lecture_id = f"{slugify(title)}-{counter}"
        lecture_dir = lectures_dir / lecture_id
        counter += 1

    lecture_dir.mkdir(parents=True)
    shutil.copy2(pdf_path, lecture_dir / "slides.pdf")

    now = datetime.now().isoformat(timespec="seconds")
    existing = list_lectures(course_id)
    order = max((s.order for s in existing), default=-1) + 1
    session = Session(
        id=lecture_id,
        title=title,
        pdf_filename="slides.pdf",
        created_at=now,
        updated_at=now,
        order=order,
    )
    _write_json(lecture_dir / "session.json", session.to_dict())
    return session


def list_lectures(course_id: str) -> list[Session]:
    lectures_dir = COURSES_DIR / course_id / "lectures"
    if not lectures_dir.exists():
        return []
    sessions = []
    for d in lectures_dir.iterdir():
        sj = d / "session.json"
        if d.is_dir() and sj.exists():
            sessions.append(Session.from_dict(_read_json(sj)))
    sessions.sort(key=lambda s: (s.order, s.created_at))
    return sessions


def reorder_lectures(course_id: str, ordered_ids: list[str]) -> None:
    for i, lid in enumerate(ordered_ids):
        sj = COURSES_DIR / course_id / "lectures" / lid / "session.json"
        if sj.exists():
            data = _read_json(sj)
            data["order"] = i
            _write_json(sj, data)


def rename_lecture(course_id: str, lecture_id: str, new_title: str) -> None:
    sj = COURSES_DIR / course_id / "lectures" / lecture_id / "session.json"
    if sj.exists():
        data = _read_json(sj)
        data["title"] = new_title
        _write_json(sj, data)


def delete_lecture(course_id: str, lecture_id: str) -> None:
    lecture_dir = COURSES_DIR / course_id / "lectures" / lecture_id
    if lecture_dir.exists():
        shutil.rmtree(lecture_dir)


def load_session(course_id: str, lecture_id: str) -> Session:
    path = COURSES_DIR / course_id / "lectures" / lecture_id / "session.json"
    return Session.from_dict(_read_json(path))


def save_session(course_id: str, session: Session) -> None:
    session.updated_at = datetime.now().isoformat(timespec="seconds")
    path = COURSES_DIR / course_id / "lectures" / session.id / "session.json"
    _write_json(path, session.to_dict())
