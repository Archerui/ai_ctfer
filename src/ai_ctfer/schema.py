from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Category(str, Enum):
    PWN = "pwn"
    REV = "rev"
    CRYPTO = "crypto"
    WEB = "web"
    FORENSICS = "forensics"
    MISC = "misc"
    UNKNOWN = "unknown"


class Protocol(str, Enum):
    TCP = "tcp"
    HTTP = "http"
    HTTPS = "https"


class Remote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: Protocol = Protocol.TCP

    @model_validator(mode="before")
    @classmethod
    def accept_one_line_remote(cls, value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, str):
            return {"raw": value.strip() or None}
        return value

    @property
    def configured(self) -> bool:
        return bool(self.raw or self.host)

    def as_prompt_value(self) -> str | dict[str, Any] | None:
        if self.raw:
            return self.raw
        if self.host:
            return self.model_dump(mode="json", exclude_none=True)
        return None


class Limits(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_steps: int = Field(default=50, ge=1, le=500)
    command_timeout_sec: int = Field(default=600, ge=1, le=3600)
    max_output_chars: int = Field(default=50000, ge=1000, le=500000)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    name: Literal["deepseek", "gpt"] = "deepseek"
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_model_name(cls, value: Any) -> str:
        normalized = str(value or "deepseek").strip().lower()
        aliases = {
            "deepseek": "deepseek",
            "deepseek-v4-pro": "deepseek",
            "deepseek-v4-flash": "deepseek",
            "gpt": "gpt",
            "openai": "gpt",
            "gpt-5.5": "gpt",
            "gpt-5.5-xhigh": "gpt",
        }
        if normalized in aliases:
            return aliases[normalized]
        raise ValueError("model.name must be either 'deepseek' or 'gpt'")

    @property
    def provider(self) -> str:
        return self.name

    @property
    def api_model(self) -> str:
        if self.name == "gpt":
            return "gpt-5.5"
        return "deepseek-v4-pro"

    @property
    def reasoning_effort(self) -> str | None:
        if self.name == "gpt":
            return "xhigh"
        return None


class Challenge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    category: Category = Category.UNKNOWN
    description: str | None = None
    flag_format: str | None = None
    flag_regex: str | None = Field(default=None, exclude=True)
    remote: Remote = Field(default_factory=Remote)
    hints: list[str] = Field(default_factory=list)
    limits: Limits = Field(default_factory=Limits)
    model: LLMConfig = Field(default_factory=LLMConfig)

    @field_validator("flag_regex")
    @classmethod
    def validate_flag_regex(cls, value: str | None) -> str | None:
        if value:
            re.compile(value)
        return value

    @property
    def display_name(self) -> str:
        return self.name or "unnamed-challenge"

    def as_prompt_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", exclude_none=True)
        remote = self.remote.as_prompt_value()
        if remote:
            data["remote"] = remote
        else:
            data.pop("remote", None)
        return data


def load_challenge(workdir: Path, schema_path: Path | None = None) -> Challenge:
    schema_file = schema_path or workdir / "challenge.yml"
    if not schema_file.exists():
        return Challenge(name=workdir.resolve().name)

    raw = yaml.safe_load(schema_file.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{schema_file} must contain a YAML mapping")

    challenge = Challenge.model_validate(raw)
    if not challenge.name:
        challenge.name = workdir.resolve().name
    return challenge


SAMPLE_CHALLENGE_YAML = """name: example-challenge
# category options: pwn, rev, crypto, web, forensics, misc, unknown
category: unknown
description: |
  Briefly describe the challenge here. Include any nc/http endpoint text from
  the challenge page if useful.
flag_format: "flag{...}"
remote: ""  # optional, e.g. "nc example.com 31337" or "https://example.com/"

hints: []

limits:
  max_steps: 50
  command_timeout_sec: 600
  max_output_chars: 50000

model:
  # name options: deepseek, gpt
  # deepseek => deepseek-v4-pro
  # gpt => gpt-5.5 with xhigh reasoning
  name: deepseek
  temperature: 0.1
"""
