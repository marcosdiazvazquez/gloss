"""Review view — slide viewer on the left, Claude's feedback on the right."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QDialog,
    QLineEdit,
    QCheckBox,
)
from PySide6.QtCore import Signal, Qt, QEvent
from PySide6.QtWidgets import QApplication

from src.models import storage
from src.models.session import Session, ReviewItem, FollowupMessage
from src.services.note_parser import parse_notes
from src.services.pdf_service import load_pdf_base64
from src.services.llm_service import ReviewWorker, FollowupWorker, LLMProvider
from src.services.claude_provider import ClaudeProvider
from src.services.openai_provider import OpenAIProvider
from src.services.gemini_provider import GeminiProvider
from src.utils.config import (
    load_api_key, save_api_key, load_model,
    load_openai_api_key, save_openai_api_key, load_openai_model,
    load_gemini_api_key, save_gemini_api_key, load_gemini_model,
    load_provider,
)
from src.widgets.review_card import ReviewCard
from src.widgets.slide_viewer import SlideViewer


class ApiKeyDialog(QDialog):
    """Simple dialog to prompt for an API key."""

    def __init__(self, parent=None, provider: str = "Anthropic", placeholder: str = "sk-ant-..."):
        super().__init__(parent)
        self.setWindowTitle("API Key Required")
        self.setFixedWidth(420)
        self.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4;")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel(f"Enter your {provider} API key to use Review Mode:")
        label.setWordWrap(True)
        layout.addWidget(label)

        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText(placeholder)
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
    """Slide viewer + per-slide LLM review panel."""

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
        self._provider_name: str = "anthropic"
        self._init_ui()
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and self.isVisible():
            # Don't steal keys while the user is typing in any text widget
            focused = QApplication.focusWidget()
            from PySide6.QtWidgets import QLineEdit, QTextEdit
            if isinstance(focused, (QLineEdit, QTextEdit)):
                return super().eventFilter(obj, event)
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_K):
                self._prev_slide()
                return True
            elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_J):
                self._next_slide()
                return True
        return super().eventFilter(obj, event)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Top navigation bar --
        nav_bar = QWidget()
        nav_bar.setFixedHeight(50)
        nav_bar.setStyleSheet("background-color: #181825;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(12, 4, 12, 4)

        self._prev_btn = QPushButton("< Prev")
        self._prev_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; color: #89b4fa; }"
            "QPushButton:hover { background-color: #313244; color: #b4befe; }"
        )
        self._prev_btn.clicked.connect(self._prev_slide)
        sp = self._prev_btn.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self._prev_btn.setSizePolicy(sp)
        nav_layout.addWidget(self._prev_btn)

        nav_layout.addStretch()

        self._page_label = QLabel("Slide 0 of 0")
        self._page_label.setStyleSheet("color: #cba6f7; font-weight: bold;")
        nav_layout.addWidget(self._page_label)

        nav_layout.addStretch()

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #585b70;")
        nav_layout.addWidget(self._status_label)

        self._next_btn = QPushButton("Next >")
        self._next_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; color: #89b4fa; }"
            "QPushButton:hover { background-color: #313244; color: #b4befe; }"
        )
        self._next_btn.clicked.connect(self._next_slide)
        sp = self._next_btn.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self._next_btn.setSizePolicy(sp)
        nav_layout.addWidget(self._next_btn)

        layout.addWidget(nav_bar)

        # -- Splitter: slide viewer (left 60%) + review panel (right 40%) --
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(8, 0, 8, 0)
        content_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        self._viewer = SlideViewer()
        self._viewer.setStyleSheet(
            "SlideViewer { background-color: #181825; border: 1px solid #313244; border-radius: 8px; }"
        )
        self._viewer.setMinimumWidth(250)

        # Right panel: scrollable review cards for the current slide
        self._right_scroll = QScrollArea()
        self._right_scroll.setWidgetResizable(True)
        self._right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._right_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #313244; border-radius: 8px; background-color: #1e1e2e; }"
            "QScrollBar:vertical { background: #181825; width: 8px; }"
            "QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._right_scroll.setMinimumWidth(250)

        self._right_content = QWidget()
        self._right_content.setStyleSheet("background-color: #1e1e2e;")
        self._right_layout = QVBoxLayout(self._right_content)
        self._right_layout.setContentsMargins(16, 16, 16, 16)
        self._right_layout.setSpacing(12)
        self._right_layout.addStretch()
        self._right_scroll.setWidget(self._right_content)

        self._splitter.addWidget(self._viewer)
        self._splitter.addWidget(self._right_scroll)
        self._splitter.setSizes([600, 400])
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet(
            "QSplitter::handle { background-color: #45475a; }"
            "QSplitter::handle:hover { background-color: #89b4fa; }"
        )

        content_layout.addWidget(self._splitter)
        layout.addWidget(content_area, 1)

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

        # -- Signals --
        self._viewer.page_changed.connect(self._on_page_changed)

    # -- Public API -----------------------------------------------------------

    def load(self, course_id: str, lecture_id: str, group_id: str | None = None, initial_page: int = 0):
        self._stop_worker()
        self._course_id = course_id
        self._lecture_id = lecture_id
        self._group_id = group_id
        self._session = storage.load_session(course_id, lecture_id, group_id=group_id)
        self._cards.clear()

        # Resolve provider and credentials
        self._provider_name = load_provider()
        if self._provider_name == "openai":
            self._api_key = load_openai_api_key()
            self._model = load_openai_model()
        elif self._provider_name == "gemini":
            self._api_key = load_gemini_api_key()
            self._model = load_gemini_model()
        else:
            self._api_key = load_api_key()
            self._model = load_model()

        if not self._api_key:
            if not self._prompt_api_key():
                self.back_requested.emit()
                return

        # Load PDF into viewer
        pdf_path = (
            storage.lecture_dir_path(course_id, lecture_id, group_id)
            / self._session.pdf_filename
        )
        self._viewer.load_pdf(pdf_path)
        if initial_page > 0:
            self._viewer.go_to_page(initial_page)

        # Also encode for LLM
        try:
            self._pdf_base64 = load_pdf_base64(pdf_path)
        except ValueError as exc:
            self._show_right_error(str(exc))
            return

        self._build_cards()

    # -- Slide navigation -----------------------------------------------------

    def _prev_slide(self):
        self._viewer.prev_page()

    def _next_slide(self):
        self._viewer.next_page()

    def _on_page_changed(self, page: int):
        total = self._viewer.page_count
        self._page_label.setText(f"Slide {page + 1} of {total}")
        self._prev_btn.setVisible(page > 0)
        self._next_btn.setVisible(page < total - 1)
        self._show_slide_cards(str(page + 1))

    # -- Card building --------------------------------------------------------

    def _build_cards(self):
        """Pre-build all ReviewCard widgets and store in _cards; show current slide."""
        self._cards.clear()

        slides_needing_review: dict[str, list] = {}

        sorted_keys = sorted(self._session.slides.keys(), key=lambda k: int(k))

        for slide_key in sorted_keys:
            slide_data = self._session.slides[slide_key]
            parsed = parse_notes(slide_data.raw_notes)
            if not parsed:
                continue

            slide_cards: list[ReviewCard] = []

            if slide_data.review:
                for i, item in enumerate(slide_data.review):
                    card = ReviewCard(item.note_type, item.original)
                    card.set_response(item.response)
                    card.load_followups(item.followups)
                    card.regenerate_requested.connect(
                        lambda sk=slide_key, c=card, n=item: self._regenerate_card(sk, c, n)
                    )
                    card.followup_submitted.connect(
                        lambda q, sk=slide_key, c=card, idx=i: self._on_followup(sk, c, idx, q)
                    )
                    slide_cards.append(card)
            else:
                for note in parsed:
                    card = ReviewCard(note.note_type, note.text)
                    slide_cards.append(card)
                slides_needing_review[slide_key] = parsed

            self._cards[slide_key] = slide_cards

        # Show cards for whichever slide is currently visible
        self._show_slide_cards(str(self._viewer.current_page + 1))

        if slides_needing_review:
            self._start_review(slides_needing_review)
        else:
            self._status_label.setText("All reviews cached")

    def _show_slide_cards(self, slide_key: str):
        """Populate the right panel with cards for the given slide."""
        # Detach all widgets without deleting (cards live in _cards dict)
        while self._right_layout.count():
            item = self._right_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        cards = self._cards.get(slide_key, [])
        if not cards:
            empty = QLabel("No notes for this slide.")
            empty.setStyleSheet("color: #585b70;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._right_layout.addWidget(empty)
        else:
            for card in cards:
                self._right_layout.addWidget(card)

        self._right_layout.addStretch()

    # -- Worker management ----------------------------------------------------

    def _start_review(self, slides_to_review: dict[str, list]):
        total = len(slides_to_review)
        self._reviewed_count = 0
        self._total_to_review = total
        self._status_label.setText(f"Reviewing 0/{total} slides...")

        provider = self._make_provider()
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

        cards = self._cards.get(slide_key, [])
        for i, card in enumerate(cards):
            if i < len(items):
                card.set_response(items[i].response)
                item = items[i]
                card.regenerate_requested.disconnect()
                card.regenerate_requested.connect(
                    lambda sk=slide_key, c=card, n=item: self._regenerate_card(sk, c, n)
                )
                card.followup_submitted.connect(
                    lambda q, sk=slide_key, c=card, idx=i: self._on_followup(sk, c, idx, q)
                )

        if self._session and slide_key in self._session.slides:
            self._session.slides[slide_key].review = items
            storage.save_session(self._course_id, self._session, group_id=self._group_id)

    def _on_slide_error(self, slide_key: str, error_msg: str):
        self._reviewed_count += 1
        self._status_label.setText(
            f"Reviewing {self._reviewed_count}/{self._total_to_review} slides..."
        )
        for card in self._cards.get(slide_key, []):
            card.set_error(error_msg)

    def _on_all_done(self):
        self._status_label.setText("Review complete")

    # -- Regenerate -----------------------------------------------------------

    def _regenerate_card(self, slide_key: str, card: ReviewCard, old_item: ReviewItem):
        card.set_loading()
        from src.services.note_parser import ParsedNote
        note = ParsedNote(note_type=old_item.note_type, text=old_item.original)
        slides = {slide_key: [note]}

        provider = self._make_provider()
        worker = ReviewWorker(provider, self._pdf_base64, slides)

        def on_done(sk, items):
            if items:
                card.set_response(items[0].response)
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
        card._regen_worker = worker
        worker.start()

    # -- Follow-up conversations -----------------------------------------------

    def _on_followup(self, slide_key: str, card, item_idx: int, question: str):
        if not self._session or slide_key not in self._session.slides:
            return
        item = self._session.slides[slide_key].review[item_idx]
        provider = self._make_provider()
        worker = FollowupWorker(
            provider, self._pdf_base64, int(slide_key),
            item.note_type, item.original, item.response,
            item.followups, question,
        )
        worker.done.connect(
            lambda ans, sk=slide_key, idx=item_idx, c=card, q=question:
                self._on_followup_done(sk, idx, c, q, ans)
        )
        worker.error.connect(lambda msg, c=card: c.set_followup_error(msg))
        card._followup_worker = worker
        worker.start()

    def _on_followup_done(
        self, slide_key: str, item_idx: int, card, question: str, answer: str
    ):
        card.add_followup_response(question, answer)
        if self._session and slide_key in self._session.slides:
            item = self._session.slides[slide_key].review[item_idx]
            item.followups.append(FollowupMessage(role="user", text=question))
            item.followups.append(FollowupMessage(role="assistant", text=answer))
            storage.save_session(self._course_id, self._session, group_id=self._group_id)

    # -- Navigation -----------------------------------------------------------

    def _go_back(self):
        self._stop_worker()
        self.back_requested.emit()

    # -- Helpers --------------------------------------------------------------

    def _make_provider(self) -> LLMProvider:
        if self._provider_name == "openai":
            return OpenAIProvider(self._api_key, self._model)
        if self._provider_name == "gemini":
            return GeminiProvider(self._api_key, self._model)
        return ClaudeProvider(self._api_key, self._model)

    def _prompt_api_key(self) -> bool:
        if self._provider_name == "openai":
            provider_label, placeholder = "OpenAI", "sk-..."
        elif self._provider_name == "gemini":
            provider_label, placeholder = "Google Gemini", "AIza..."
        else:
            provider_label, placeholder = "Anthropic", "sk-ant-..."
        dialog = ApiKeyDialog(self, provider_label, placeholder)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            key = dialog.get_key()
            if key:
                if self._provider_name == "openai":
                    save_openai_api_key(key)
                elif self._provider_name == "gemini":
                    save_gemini_api_key(key)
                else:
                    save_api_key(key)
                self._api_key = key
                return True
        return False

    def _show_right_error(self, message: str):
        while self._right_layout.count():
            item = self._right_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        label = QLabel(message)
        label.setStyleSheet("color: #f38ba8;")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_layout.addWidget(label)
        self._right_layout.addStretch()
