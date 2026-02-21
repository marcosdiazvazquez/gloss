import json
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


def _read_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write_config(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_api_key() -> str:
    """Read the Anthropic API key from config.json. Returns '' if not set."""
    return _read_config().get("api_key", "")


def save_api_key(key: str) -> None:
    """Persist the Anthropic API key to config.json."""
    data = _read_config()
    data["api_key"] = key
    _write_config(data)


DEFAULT_MODEL = "claude-sonnet-4-20250514"

AVAILABLE_MODELS = [
    ("claude-opus-4-6", "Opus 4.6", "Most capable, higher cost"),
    ("claude-sonnet-4-20250514", "Sonnet 4", "Fast and cost-effective"),
    ("claude-haiku-4-20250414", "Haiku 4", "Fastest, lowest cost"),
]


def load_model() -> str:
    """Read the selected model from config.json. Returns default if not set."""
    return _read_config().get("model", DEFAULT_MODEL)


def save_model(model_id: str) -> None:
    """Persist the selected model to config.json."""
    data = _read_config()
    data["model"] = model_id
    _write_config(data)
