"""Load and resolve notifier configuration."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .history import default_history_path

APP_NAME = "cursor-usage-notifier"
DEFAULT_THRESHOLD_USD = 50.0
DEFAULT_POLL_MINUTES = 15
DEFAULT_SOUND = "Glass"
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8765


def default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def default_config_path() -> Path:
    return default_data_dir() / "config.toml"


def default_state_path() -> Path:
    return default_data_dir() / "state.json"


@dataclass(frozen=True)
class Config:
    threshold_usd: float = DEFAULT_THRESHOLD_USD
    poll_minutes: int = DEFAULT_POLL_MINUTES
    sound: str = DEFAULT_SOUND
    state_path: Path = None  # type: ignore[assignment]
    history_path: Path = None  # type: ignore[assignment]
    web_host: str = DEFAULT_WEB_HOST
    web_port: int = DEFAULT_WEB_PORT
    config_path: Path = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.state_path is None:
            object.__setattr__(self, "state_path", default_state_path())
        if self.history_path is None:
            object.__setattr__(self, "history_path", default_history_path())
        if self.config_path is None:
            object.__setattr__(self, "config_path", default_config_path())


def _parse_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_config(config_path: Path | None = None) -> Config:
    """Load config from TOML file, falling back to defaults."""
    path = config_path or Path(
        os.environ.get("CURSOR_USAGE_NOTIFIER_CONFIG", default_config_path())
    )
    data: dict = {}
    if path.is_file():
        data = _parse_toml(path)

    threshold = float(data.get("threshold_usd", DEFAULT_THRESHOLD_USD))
    if threshold <= 0:
        raise ValueError("threshold_usd must be > 0")

    poll = int(data.get("poll_minutes", DEFAULT_POLL_MINUTES))
    if poll < 1:
        raise ValueError("poll_minutes must be >= 1")

    sound = str(data.get("sound", DEFAULT_SOUND))
    state_raw = data.get("state_path")
    state_path = Path(state_raw).expanduser() if state_raw else default_state_path()
    history_raw = data.get("history_path")
    history_path = (
        Path(history_raw).expanduser() if history_raw else default_history_path()
    )
    web_host = str(data.get("web_host", DEFAULT_WEB_HOST))
    web_port = int(data.get("web_port", DEFAULT_WEB_PORT))
    if web_port < 1 or web_port > 65535:
        raise ValueError("web_port must be between 1 and 65535")

    return Config(
        threshold_usd=threshold,
        poll_minutes=poll,
        sound=sound,
        state_path=state_path,
        history_path=history_path,
        web_host=web_host,
        web_port=web_port,
        config_path=path,
    )


def ensure_runtime_dirs(config: Config) -> None:
    config.state_path.parent.mkdir(parents=True, exist_ok=True)
    config.history_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
