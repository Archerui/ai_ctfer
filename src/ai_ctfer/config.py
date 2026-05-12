from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


Language = Literal["en", "zh"]

DEFAULT_LANGUAGE: Language = "en"

_LANGUAGE_ALIASES: dict[str, Language] = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "英语": "en",
    "英文": "en",
    "zh": "zh",
    "zh-cn": "zh",
    "cn": "zh",
    "chinese": "zh",
    "中文": "zh",
    "汉语": "zh",
    "简体中文": "zh",
}


@dataclass
class AppConfig:
    language: Language = DEFAULT_LANGUAGE


def config_dir() -> Path:
    if override := os.environ.get("AI_CTFER_CONFIG_DIR"):
        return Path(override).expanduser()
    if xdg_config := os.environ.get("XDG_CONFIG_HOME"):
        return Path(xdg_config).expanduser() / "ai-ctfer"
    return Path.home() / ".config" / "ai-ctfer"


def config_path() -> Path:
    return config_dir() / "config.yml"


def normalize_language(value: str) -> Language:
    normalized = value.strip().lower().replace("_", "-")
    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]
    raise ValueError("language must be Chinese/中文 or English/英语")


def load_config(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        return AppConfig()
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return AppConfig()
        language = normalize_language(str(raw.get("language", DEFAULT_LANGUAGE)))
        return AppConfig(language=language)
    except Exception:
        return AppConfig()


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(
            {"language": config.language},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return target
