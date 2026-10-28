"""Configuration loading (config.toml)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    input_driver: str = "sim"
    clock_driver: str = "offset"
    encoder_a: int = 17
    encoder_b: int = 27
    button: int = 22
    db_path: str = "~/.local/share/timetracker/timetracker.db"
    fullscreen: bool = False
    hide_cursor: bool = False
    width: int = 1280
    height: int = 720


def load_config(path: str | Path | None = None) -> Config:
    cfg = Config()
    if path is None or not Path(path).exists():
        return cfg
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    cfg.input_driver = raw.get("input", {}).get("driver", cfg.input_driver)
    cfg.clock_driver = raw.get("clock", {}).get("driver", cfg.clock_driver)
    gpio = raw.get("gpio", {})
    cfg.encoder_a = gpio.get("encoder_a", cfg.encoder_a)
    cfg.encoder_b = gpio.get("encoder_b", cfg.encoder_b)
    cfg.button = gpio.get("button", cfg.button)
    cfg.db_path = raw.get("storage", {}).get("path", cfg.db_path)
    display = raw.get("display", {})
    cfg.fullscreen = display.get("fullscreen", cfg.fullscreen)
    cfg.hide_cursor = display.get("hide_cursor", cfg.hide_cursor)
    cfg.width = display.get("width", cfg.width)
    cfg.height = display.get("height", cfg.height)
    return cfg
