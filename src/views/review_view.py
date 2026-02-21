"""Review view — displays Claude's feedback on student notes, grouped by slide."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QDialog,
    QLineEdit,
    QCheckBox,
)
from PySide6.QtCore import Signal, Qt

from src.models import storage
from src.models.session import Session, ReviewItem
from src.services.note_parser import parse_notes
from src.services.pdf_service import load_pdf_base64
from src.services.llm_service import ReviewWorker
from src.services.claude_provider import ClaudeProvider
from src.utils.config import load_api_key, save_api_key, load_model
from src.widgets.review_card import ReviewCard


class ApiKeyDialog(QDialog):
    """Simple dialog to prompt for the Anthropic API key."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API Key Required")
        self.setFixedWidth(420)
        self.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4;")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel("Enter your Anthropic API key to use Review Mode:")
        label.setWordWrap(True)
        layout.addWidget(label)

        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("sk-ant-...")
        self._key_input.setStyleSheet(
            "QLineEdit { background-color: #313244; border: 1px solid #45475a; "
            "border-radius: 4px; padding: 6px; color: #cdd6f4; }"
        )
        layout.addWidget(self._key_input)

        show_cb = QCheckBox("Show key")
        show_cb.setStyleSheet("color: #585b70;")
        show_cb.toggled.connect(
            lambda on: self._key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        layout.addWidget(show_cb)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { padding: 4px 16px; color: #585b70; }"
            "QPushButton:hover { color: #cdd6f4; }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            "QPushButton { padding: 4px 16px; color: #a6e3a1; }"
            "QPushButton:hover { background-color: #313244; }"
        )
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def get_key(self) -> str:
        return self._key_input.text().strip()


class ReviewView(QWidget):
    """LLM review display — shows Claude's feedback on student notes."""

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._course_id: str = ""
        self._lecture_id: str = ""
        self._group_id: str | None = None
        self._session: Session | None = None
        self._worker: ReviewWorker | None = None
        self._cards: dict[str, list[ReviewCard]] = {}  # slide_key -> [ReviewCard]
        self._pdf_base64: str = ""
        self._api_key: str = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Top bar --
        top_bar = QWidget()
        top_bar.setFixedHeight(50)
        top_bar.setStyleSheet("background-color: #181825;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 4, 16, 4)

        self._title_label = QLabel("Review")
        self._title_label.setStyleSheet("color: #cba6f7; font-weight: bold;")
        top_layout.addWidget(self._title_label)

        top_layout.addStretch()

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #585b70;")
        top_layout.addWidget(self._status_label)

        layout.addWidget(top_bar)

        # -- Scrollable content area --
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: #1e1e2e; }"
            "QScrollBar:vertical { background: #181825; width: 8px; }"
            "QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(40, 16, 40, 16)
        self._content_layout.setSpacing(12)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)

        # -- Bottom bar --
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(50)
        bottom_bar.setStyleSheet("background-color: #181825;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(40, 4, 40, 4)

        back_btn = QPushButton("Back to Slides")
        back_btn.setStyleSheet(
            "QPushButton { padding: 4px 16px; color: #89b4fa; }"
            "QPushButton:hover { background-color: #313244; color: #b4befe; }"
        )
        back_btn.clicked.connect(self._go_back)
        bottom_layout.addWidget(back_btn)

        bottom_layout.addStretch()
        layout.addWidget(bottom_bar)

    # -- Public API -----------------------------------------------------------

    def load(self, course_id: str, lecture_id: str, group_id: str | None = None):
        self._stop_worker()
        self._course_id = course_id
        self._lecture_id = lecture_id
        self._group_id = group_id
        self._session = storage.load_session(course_id, lecture_id, group_id=group_id)
        self._cards.clear()

        self._title_label.setText(f"Review: {self._session.title}")

        # Load settings
        self._api_key = load_api_key()
        self._model = load_model()
        if not self._api_key:
            if not self._prompt_api_key():
                self.back_requested.emit()
                return

        # Load PDF
        pdf_path = (
            storage.lecture_dir_path(course_id, lecture_id, group_id)
            / self._session.pdf_filename
        )
        try:
            self._pdf_base64 = load_pdf_base64(pdf_path)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self._build_cards()

    # -- Card building --------------------------------------------------------

    def _clear_content(self):
        """Remove all widgets from the content layout."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_cards(self):
        """Build ReviewCards for all annotated slides, start worker for missing reviews."""
        self._clear_content()
        self._cards.clear()

        slides_needing_review: dict[str, list] = {}
        has_any_notes = False

        # Sort slide keys numerically
        sorted_keys = sorted(
            self._session.slides.keys(),
            key=lambda k: int(k),
        )

        for slide_key in sorted_keys:
            slide_data = self._session.slides[slide_key]
            parsed = parse_notes(slide_data.raw_notes)
            if not parsed:
                continue

            has_any_notes = True

            # Slide header
            header = QLabel(f"Slide {slide_key}")
            header.setStyleSheet(
                "color: #585b70; font-weight: bold; padding-top: 8px;"
            )
            self._content_layout.addWidget(header)

            slide_cards = []
            if slide_data.review:
                # Cached responses — display immediately
                for item in slide_data.review:
                    card = ReviewCard(item.note_type, item.original)
                    card.set_response(item.response)
                    card.regenerate_requested.connect(
                        lambda sk=slide_key, c=card, n=item: self._regenerate_card(sk, c, n)
                    )
                    self._content_layout.addWidget(card)
                    slide_cards.append(card)
            else:
                # Need review — create loading cards
                for note in parsed:
                    card = ReviewCard(note.note_type, note.text)
                    self._content_layout.addWidget(card)
                    slide_cards.append(card)
                slides_needing_review[slide_key] = parsed

            self._cards[slide_key] = slide_cards

        self._content_layout.addStretch()

        if not has_any_notes:
            empty = QLabel("No annotated notes to review.\nGo back and add some notes with - ? ~ ! markers.")
            empty.setStyleSheet("color: #585b70;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._content_layout.insertWidget(0, empty)
            self._status_label.setText("")
            return

        if slides_needing_review:
            self._start_review(slides_needing_review)
        else:
            self._status_label.setText("All reviews cached")

    # -- Worker management ----------------------------------------------------

    def _start_review(self, slides_to_review: dict[str, list]):
        total = len(slides_to_review)
        self._reviewed_count = 0
        self._total_to_review = total
        self._status_label.setText(f"Reviewing 0/{total} slides...")

        provider = ClaudeProvider(self._api_key, self._model)
        self._worker = ReviewWorker(provider, self._pdf_base64, slides_to_review)
        self._worker.slide_reviewed.connect(self._on_slide_reviewed)
        self._worker.slide_error.connect(self._on_slide_error)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()
        self._worker = None

    def _on_slide_reviewed(self, slide_key: str, items: list):
        self._reviewed_count += 1
        self._status_label.setText(
            f"Reviewing {self._reviewed_count}/{self._total_to_review} slides..."
        )

        # Update cards
        cards = self._cards.get(slide_key, [])
        for i, card in enumerate(cards):
            if i < len(items):
                card.set_response(items[i].response)
                # Wire up regenerate now that we have the ReviewItem
                item = items[i]
                card.regenerate_requested.disconnect()
                card.regenerate_requested.connect(
                    lambda sk=slide_key, c=card, n=item: self._regenerate_card(sk, c, n)
                )

        # Persist to session
        if self._session and slide_key in self._session.slides:
            self._session.slides[slide_key].review = items
            storage.save_session(self._course_id, self._session, group_id=self._group_id)

    def _on_slide_error(self, slide_key: str, error_msg: str):
        self._reviewed_count += 1
        self._status_label.setText(
            f"Reviewing {self._reviewed_count}/{self._total_to_review} slides..."
        )
        cards = self._cards.get(slide_key, [])
        for card in cards:
            card.set_error(error_msg)

    def _on_all_done(self):
        self._status_label.setText("Review complete")

    # -- Regenerate -----------------------------------------------------------

    def _regenerate_card(self, slide_key: str, card: ReviewCard, old_item: ReviewItem):
        """Re-review a single slide."""
        card.set_loading()
        from src.services.note_parser import ParsedNote
        note = ParsedNote(note_type=old_item.note_type, text=old_item.original)
        slides = {slide_key: [note]}

        provider = ClaudeProvider(self._api_key, self._model)
        worker = ReviewWorker(provider, self._pdf_base64, slides)

        def on_done(sk, items):
            if items:
                card.set_response(items[0].response)
                # Update cache
                if self._session and sk in self._session.slides:
                    review_list = self._session.slides[sk].review
                    for i, r in enumerate(review_list):
                        if r.original == old_item.original and r.note_type == old_item.note_type:
                            review_list[i] = items[0]
                            break
                    storage.save_session(self._course_id, self._session, group_id=self._group_id)

        def on_error(sk, msg):
            card.set_error(msg)

        worker.slide_reviewed.connect(on_done)
        worker.slide_error.connect(on_error)
        # Store reference so it doesn't get GC'd
        card._regen_worker = worker
        worker.start()

    # -- Navigation -----------------------------------------------------------

    def _go_back(self):
        self._stop_worker()
        self.back_requested.emit()

    # -- Helpers --------------------------------------------------------------

    def _prompt_api_key(self) -> bool:
        """Show API key dialog. Returns True if key was provided."""
        dialog = ApiKeyDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            key = dialog.get_key()
            if key:
                save_api_key(key)
                self._api_key = key
                return True
        return False

    def _show_error(self, message: str):
        """Display an error message in the content area."""
        self._clear_content()
        label = QLabel(message)
        label.setStyleSheet("color: #f38ba8;")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content_layout.addWidget(label)
        self._content_layout.addStretch()
