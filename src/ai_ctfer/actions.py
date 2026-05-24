from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class RunCommandAction(BaseModel):
    action: Literal["run_command"]
    command: str = Field(min_length=1)
    rationale: str = ""


class SubmitFlagAction(BaseModel):
    action: Literal["submit_flag"]
    flag: str = Field(min_length=1)
    rationale: str = ""


class FinishAction(BaseModel):
    action: Literal["finish"]
    status: Literal["give_up", "done", "error"] = "give_up"
    rationale: str = ""


class SetPlanAction(BaseModel):
    action: Literal["set_plan"]
    summary: str = Field(min_length=1)
    chosen_strategy: str = Field(min_length=1)
    steps: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    rationale: str = ""


AgentAction = Annotated[
    RunCommandAction | SubmitFlagAction | FinishAction | SetPlanAction,
    Field(discriminator="action"),
]

ACTION_ADAPTER = TypeAdapter(AgentAction)


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence:
        return fence.group(1)
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def iter_json_objects(text: str):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def parse_action(text: str) -> AgentAction:
    errors: list[Exception] = []
    try:
        data = json.loads(extract_json_object(text))
        return ACTION_ADAPTER.validate_python(data)
    except Exception as exc:
        errors.append(exc)

    for data in iter_json_objects(text):
        try:
            return ACTION_ADAPTER.validate_python(data)
        except Exception as exc:
            errors.append(exc)

    if errors:
        raise errors[0]
    raise ValueError("No JSON object found in model response")


def action_schema_hint() -> str:
    return (
        'Return exactly one JSON object: '
        '{"action":"run_command","command":"...","rationale":"..."}, '
        '{"action":"submit_flag","flag":"flag{...}","rationale":"..."}, '
        'or {"action":"finish","status":"give_up","rationale":"..."}.'
    )


def planning_action_schema_hint() -> str:
    return (
        'Return exactly one JSON object. During planning you may use '
        '{"action":"run_command","command":"...","rationale":"..."} to inspect '
        'the challenge, or finish planning with '
        '{"action":"set_plan","summary":"...","chosen_strategy":"...",'
        '"steps":["..."],"alternatives":["..."],"rationale":"..."}.'
    )
