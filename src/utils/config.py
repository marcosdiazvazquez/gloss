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


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def load_provider() -> str:
    """Return the active provider: 'anthropic' or 'openai'. Defaults to 'anthropic'."""
    return _read_config().get("provider", "anthropic")


def save_provider(provider: str) -> None:
    data = _read_config()
    data["provider"] = provider
    _write_config(data)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-20250514"

AVAILABLE_MODELS = [
    ("claude-opus-4-6", "Opus 4.6", "Most intelligent model for highly complex tasks."),
    ("claude-sonnet-4-20250514", "Sonnet 4", "High performance at speed."),
    ("claude-haiku-4-20250414", "Haiku 4", "Near-instant responsiveness."),
]


def load_api_key() -> str:
    """Read the Anthropic API key from config.json. Returns '' if not set."""
    return _read_config().get("api_key", "")


def save_api_key(key: str) -> None:
    """Persist the Anthropic API key to config.json."""
    data = _read_config()
    data["api_key"] = key
    _write_config(data)


def load_model() -> str:
    """Read the selected Anthropic model from config.json. Returns default if not set."""
    return _read_config().get("model", DEFAULT_MODEL)


def save_model(model_id: str) -> None:
    """Persist the selected Anthropic model to config.json."""
    data = _read_config()
    data["model"] = model_id
    _write_config(data)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

OPENAI_DEFAULT_MODEL = "gpt-4o"

AVAILABLE_OPENAI_MODELS = [
    ("o1", "o1", "Reasoning model designed to solve hard problems."),
    ("gpt-4o", "GPT-4o", "Fast, intelligent, flexible GPT model."),
    ("o3-mini", "o3-mini", "Fast, flexible, intelligent reasoning model."),
    ("gpt-4o-mini", "GPT-4o mini", "Affordable and intelligent small model."),
]


def load_openai_api_key() -> str:
    return _read_config().get("openai_api_key", "")


def save_openai_api_key(key: str) -> None:
    data = _read_config()
    data["openai_api_key"] = key
    _write_config(data)


def load_openai_model() -> str:
    return _read_config().get("openai_model", OPENAI_DEFAULT_MODEL)


def save_openai_model(model_id: str) -> None:
    data = _read_config()
    data["openai_model"] = model_id
    _write_config(data)


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"

AVAILABLE_GEMINI_MODELS = [
    ("gemini-2.5-pro", "Pro 2.5", "Advanced reasoning, best for complex tasks."),
    ("gemini-2.5-flash", "Flash 2.5", "Fast and capable, balanced speed and quality."),
    ("gemini-2.5-flash-lite", "Flash 2.5 Lite", "Fastest and cheapest."),
]


def load_gemini_api_key() -> str:
    return _read_config().get("gemini_api_key", "")


def save_gemini_api_key(key: str) -> None:
    data = _read_config()
    data["gemini_api_key"] = key
    _write_config(data)


def load_gemini_model() -> str:
    return _read_config().get("gemini_model", GEMINI_DEFAULT_MODEL)


def save_gemini_model(model_id: str) -> None:
    data = _read_config()
    data["gemini_model"] = model_id
    _write_config(data)
