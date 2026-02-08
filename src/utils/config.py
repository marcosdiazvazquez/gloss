from pathlib import Path

from platformdirs import user_data_dir

APP_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = APP_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
STYLES_DIR = ASSETS_DIR / "styles"

DATA_DIR = Path(user_data_dir("gloss", ensure_exists=True))
COURSES_DIR = DATA_DIR / "courses"
CONFIG_FILE = DATA_DIR / "config.json"

# Current font size in pt — updated by app._apply_theme() on zoom
font_size = 21
