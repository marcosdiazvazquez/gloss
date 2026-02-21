"""Filesystem CRUD for courses, groups, and lecture sessions."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from src.models.session import Course, Group, Session, SlideData, slugify
from src.utils.config import COURSES_DIR


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# -- Path helpers --------------------------------------------------------------


def lecture_dir_path(course_id: str, lecture_id: str, group_id: str | None = None) -> Path:
    """Single source of truth for resolving a lecture's directory."""
    if group_id:
        return COURSES_DIR / course_id / "groups" / group_id / "lectures" / lecture_id
    return COURSES_DIR / course_id / "lectures" / lecture_id


def _lectures_dir(course_id: str, group_id: str | None = None) -> Path:
    """Return the lectures/ directory for ungrouped or grouped lectures."""
    if group_id:
        return COURSES_DIR / course_id / "groups" / group_id / "lectures"
    return COURSES_DIR / course_id / "lectures"


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


# -- Groups -------------------------------------------------------------------


def create_group(course_id: str, name: str) -> Group:
    group_id = slugify(name)
    groups_dir = COURSES_DIR / course_id / "groups"
    groups_dir.mkdir(exist_ok=True)
    group_dir = groups_dir / group_id
    counter = 2
    while group_dir.exists():
        group_id = f"{slugify(name)}-{counter}"
        group_dir = groups_dir / group_id
        counter += 1

    group_dir.mkdir(parents=True)
    (group_dir / "lectures").mkdir()

    now = datetime.now().isoformat(timespec="seconds")
    existing = list_groups(course_id)
    order = max((g.order for g in existing), default=-1) + 1
    group = Group(id=group_id, name=name, created_at=now, order=order)
    _write_json(group_dir / "group.json", group.to_dict())
    return group


def list_groups(course_id: str) -> list[Group]:
    groups_dir = COURSES_DIR / course_id / "groups"
    if not groups_dir.exists():
        return []
    groups = []
    for d in groups_dir.iterdir():
        gj = d / "group.json"
        if d.is_dir() and gj.exists():
            groups.append(Group.from_dict(_read_json(gj)))
    groups.sort(key=lambda g: (g.order, g.created_at))
    return groups


def rename_group(course_id: str, group_id: str, new_name: str) -> None:
    gj = COURSES_DIR / course_id / "groups" / group_id / "group.json"
    if gj.exists():
        data = _read_json(gj)
        data["name"] = new_name
        _write_json(gj, data)


def reorder_groups(course_id: str, ordered_ids: list[str]) -> None:
    for i, gid in enumerate(ordered_ids):
        gj = COURSES_DIR / course_id / "groups" / gid / "group.json"
        if gj.exists():
            data = _read_json(gj)
            data["order"] = i
            _write_json(gj, data)


def delete_group(course_id: str, group_id: str) -> None:
    group_dir = COURSES_DIR / course_id / "groups" / group_id
    if group_dir.exists():
        shutil.rmtree(group_dir)


# -- Lectures ------------------------------------------------------------------


def create_lecture(course_id: str, title: str, pdf_path: str, group_id: str | None = None) -> Session:
    lecture_id = slugify(title)
    lectures_dir = _lectures_dir(course_id, group_id)
    lectures_dir.mkdir(parents=True, exist_ok=True)
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
    existing = list_lectures(course_id, group_id=group_id)
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


def list_lectures(course_id: str, group_id: str | None = None) -> list[Session]:
    lectures_dir = _lectures_dir(course_id, group_id)
    if not lectures_dir.exists():
        return []
    sessions = []
    for d in lectures_dir.iterdir():
        sj = d / "session.json"
        if d.is_dir() and sj.exists():
            sessions.append(Session.from_dict(_read_json(sj)))
    sessions.sort(key=lambda s: (s.order, s.created_at))
    return sessions


def reorder_lectures(course_id: str, ordered_ids: list[str], group_id: str | None = None) -> None:
    for i, lid in enumerate(ordered_ids):
        sj = lecture_dir_path(course_id, lid, group_id) / "session.json"
        if sj.exists():
            data = _read_json(sj)
            data["order"] = i
            _write_json(sj, data)


def rename_lecture(course_id: str, lecture_id: str, new_title: str, group_id: str | None = None) -> None:
    sj = lecture_dir_path(course_id, lecture_id, group_id) / "session.json"
    if sj.exists():
        data = _read_json(sj)
        data["title"] = new_title
        _write_json(sj, data)


def delete_lecture(course_id: str, lecture_id: str, group_id: str | None = None) -> None:
    ld = lecture_dir_path(course_id, lecture_id, group_id)
    if ld.exists():
        shutil.rmtree(ld)


def load_session(course_id: str, lecture_id: str, group_id: str | None = None) -> Session:
    path = lecture_dir_path(course_id, lecture_id, group_id) / "session.json"
    return Session.from_dict(_read_json(path))


def save_session(course_id: str, session: Session, group_id: str | None = None) -> None:
    session.updated_at = datetime.now().isoformat(timespec="seconds")
    path = lecture_dir_path(course_id, session.id, group_id) / "session.json"
    _write_json(path, session.to_dict())


def move_lecture(course_id: str, lecture_id: str, from_group_id: str | None, to_group_id: str | None) -> None:
    """Move a lecture directory between ungrouped and grouped (or group to group)."""
    src = lecture_dir_path(course_id, lecture_id, from_group_id)
    if not src.exists():
        return
    dst_parent = _lectures_dir(course_id, to_group_id)
    dst_parent.mkdir(parents=True, exist_ok=True)
    dst = dst_parent / lecture_id
    shutil.move(str(src), str(dst))
