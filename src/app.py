import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from PySide6.QtGui import QFontDatabase, QIcon, QShortcut, QKeySequence
from PySide6.QtCore import Qt

import src.utils.config as cfg
from src.utils.config import FONTS_DIR, STYLES_DIR, COURSES_DIR, ASSETS_DIR
from src.views.home_view import HomeView
from src.views.lecture_view import LectureView
from src.views.review_view import ReviewView


DEFAULT_FONT_SIZE = 26


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("gloss")
        self.setMinimumSize(1024, 768)
        self._font_size = DEFAULT_FONT_SIZE

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._home = HomeView()
        self._lecture = LectureView()
        self._review = ReviewView()

        self._stack.addWidget(self._home)
        self._stack.addWidget(self._lecture)
        self._stack.addWidget(self._review)

        # Navigation signals
        self._home.lecture_opened.connect(self._open_lecture)
        self._lecture.back_requested.connect(self.show_home)
        self._lecture.review_requested.connect(self._open_review)
        self._review.back_requested.connect(self._back_to_lecture)

        # Escape → Home from any view
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.show_home)

        # Zoom shortcuts (Ctrl maps to Cmd on macOS)
        QShortcut(QKeySequence("Ctrl+="), self, self._zoom_in)
        QShortcut(QKeySequence("Ctrl++"), self, self._zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, self._zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self, self._zoom_reset)

        self.show_home()

    def _zoom_in(self):
        self._set_zoom(self._font_size + 1)

    def _zoom_out(self):
        self._set_zoom(self._font_size - 1)

    def _zoom_reset(self):
        self._set_zoom(DEFAULT_FONT_SIZE)

    def _set_zoom(self, size: int):
        size = max(DEFAULT_FONT_SIZE - 3, min(DEFAULT_FONT_SIZE + 3, size))
        if size == self._font_size:
            return
        self._font_size = size
        _apply_theme(QApplication.instance(), size)
        if self._stack.currentWidget() == self._home:
            self._home.refresh()

    def show_home(self):
        self._home.refresh()
        self._stack.setCurrentWidget(self._home)

    def _open_lecture(self, course_id: str, lecture_id: str):
        self._lecture.load(course_id, lecture_id)
        self._stack.setCurrentWidget(self._lecture)

    def _open_review(self, course_id: str, lecture_id: str):
        self._review.load(course_id, lecture_id)
        self._stack.setCurrentWidget(self._review)

    def _back_to_lecture(self):
        self._stack.setCurrentWidget(self._lecture)

_base_qss = ""


def _register_fonts():
    """Register bundled font files with Qt."""
    font_dir = FONTS_DIR / "JetBrainsMono"
    if font_dir.exists():
        for font_file in font_dir.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font_file))


def _apply_theme(app: QApplication, font_size: int):
    """Apply stylesheet with dynamic font size. Controls font via QSS so it
    isn't overridden by subsequent stylesheet application."""
    global _base_qss
    if not _base_qss:
        qss_path = STYLES_DIR / "theme.qss"
        if qss_path.exists():
            _base_qss = qss_path.read_text()
    cfg.font_size = font_size
    font_qss = f'* {{ font-family: "JetBrains Mono"; font-size: {font_size}pt; }}\n'
    app.setStyleSheet(font_qss + _base_qss)


def _set_dock_name(name: str):
    """Set the macOS dock name (no-op on other platforms)."""
    if sys.platform != "darwin":
        return
    try:
        from ctypes import cdll, c_char_p, util
        lib = cdll.LoadLibrary(util.find_library("objc"))
        objc_getClass = lib.objc_getClass
        objc_getClass.restype = c_char_p.__class__  # id
        sel_registerName = lib.sel_registerName
        sel_registerName.restype = c_char_p.__class__
        objc_msgSend = lib.objc_msgSend
        NSProcessInfo = objc_getClass(b"NSProcessInfo")
        processInfo = objc_msgSend(NSProcessInfo, sel_registerName(b"processInfo"))
        selector = sel_registerName(b"setProcessName:")
        from ctypes import c_void_p
        from Foundation import NSString
        ns_name = NSString.stringWithString_(name)
        objc_msgSend(processInfo, selector, c_void_p(ns_name.__c_void_p__()))
    except Exception:
        pass


def _load_icon(app: QApplication):
    icon_path = ASSETS_DIR / "icons" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))


def create_app() -> QApplication:
    app = QApplication([])
    app.setApplicationName("gloss")
    app.setApplicationDisplayName("gloss")
    _set_dock_name("gloss")
    _register_fonts()
    _apply_theme(app, DEFAULT_FONT_SIZE)
    _load_icon(app)
    COURSES_DIR.mkdir(parents=True, exist_ok=True)
    window = MainWindow()
    window.show()
    app._window = window
    return app
