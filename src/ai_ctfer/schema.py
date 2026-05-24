from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .model_interface import (
    default_model_provider,
    get_api_model,
    get_default_temperature,
    get_reasoning_effort,
    model_sample_comment_lines,
    normalize_model_name,
)


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

    name: str = Field(default_factory=default_model_provider)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_model_name(cls, value: Any) -> str:
        return normalize_model_name(value)

    @property
    def provider(self) -> str:
        return self.name

    @property
    def api_model(self) -> str:
        return get_api_model(self.name)

    @property
    def reasoning_effort(self) -> str | None:
        return get_reasoning_effort(self.name)

    @property
    def temperature(self) -> float | None:
        return get_default_temperature(self.name)


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

    raw = load_challenge_yaml(schema_file.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{schema_file} must contain a YAML mapping")

    challenge = Challenge.model_validate(raw)
    if not challenge.name:
        challenge.name = workdir.resolve().name
    return challenge


DESCRIPTION_BLOCK_RE = re.compile(r"^description:\s*[|>][-+]?(?:\s+#.*)?\s*$")
TOP_LEVEL_SCHEMA_KEYS = {
    "name",
    "category",
    "description",
    "flag_format",
    "flag_regex",
    "remote",
    "hints",
    "limits",
    "model",
}


def load_challenge_yaml(text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as original_error:
        repaired = repair_unindented_description_block(text)
        if repaired == text:
            raise original_error
        try:
            return yaml.safe_load(repaired)
        except yaml.YAMLError:
            raise original_error


def repair_unindented_description_block(text: str) -> str:
    lines = text.splitlines()
    repaired: list[str] = []
    in_description = False

    for line in lines:
        if not in_description:
            repaired.append(line)
            if DESCRIPTION_BLOCK_RE.match(line):
                in_description = True
            continue

        if is_top_level_schema_key(line):
            in_description = False
            repaired.append(line)
            continue

        repaired.append(indent_description_content_line(line))

    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(repaired) + trailing_newline


def is_top_level_schema_key(line: str) -> bool:
    if not line or line[0].isspace() or line.startswith("#"):
        return False
    key, separator, _rest = line.partition(":")
    return bool(separator) and key in TOP_LEVEL_SCHEMA_KEYS


def indent_description_content_line(line: str) -> str:
    if not line:
        return line
    if line.startswith("\t"):
        return "  " + line.lstrip("\t")
    leading_spaces = len(line) - len(line.lstrip(" "))
    if leading_spaces >= 2:
        return line
    return " " * (2 - leading_spaces) + line


def build_sample_challenge_yaml() -> str:
    return f"""name: example-challenge
# category options: pwn, rev, crypto, web, forensics, misc, unknown
category: unknown
# Paste everything from the challenge page here: statement, flag format,
# nc/http endpoints, hints, and any notes. Standard YAML wants indented lines
# below; ai-ctfer also repairs accidentally unindented pasted description lines.
description: |-
  Paste the full challenge statement here.
  Example:
  nc example.com 31337
  Flag format: flag{{...}}

limits:
  max_steps: 50
  command_timeout_sec: 600
  max_output_chars: 50000

model:
{model_sample_comment_lines()}
  name: {default_model_provider()}
"""


SAMPLE_CHALLENGE_YAML = build_sample_challenge_yaml()
