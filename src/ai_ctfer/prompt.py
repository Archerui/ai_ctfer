from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from .actions import action_schema_hint, planning_action_schema_hint
from .config import Language
from .i18n import (
    adjudicator_instruction,
    adjudicator_system,
    language_instruction,
    planning_goal,
    planning_mode_instruction,
    planning_user_intro,
    repair_system,
    solve_user_intro,
)
from .schema import Category, Challenge


PROMPT_PACKAGE = "ai_ctfer.prompts"
SKILLS_PACKAGE = "ai_ctfer.prompts.skills"


@dataclass
class PromptBuilder:
    recent_history_items: int = 6

    def build_messages(
        self,
        *,
        challenge: Challenge,
        file_tree: str,
        history: list[dict[str, Any]],
        last_observation: str,
        remaining_steps: int,
        flag_candidates: list[dict[str, Any]] | None = None,
        language: Language = "en",
    ) -> list[dict[str, str]]:
        system = "\n\n".join(
            [
                read_prompt("system.md"),
                read_skill("general.md"),
                read_skill(skill_for_category(challenge.category)),
                language_instruction(language),
            ]
        )
        user = {
            "challenge": challenge.as_prompt_dict(),
            "file_tree": file_tree,
            "recent_history": history[-self.recent_history_items :],
            "last_observation": last_observation,
            "flag_candidates": flag_candidates or [],
            "flag_submission_policy": flag_submission_policy(language),
            "remaining_steps": remaining_steps,
            "allowed_actions": action_schema_hint(),
        }
        return [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": solve_user_intro(language)
                + json.dumps(user, ensure_ascii=False, indent=2),
            },
        ]

    def build_planning_messages(
        self,
        *,
        challenge: Challenge,
        file_tree: str,
        history: list[dict[str, Any]],
        last_observation: str,
        remaining_planning_steps: int,
        flag_candidates: list[dict[str, Any]] | None = None,
        language: Language = "en",
    ) -> list[dict[str, str]]:
        system = "\n\n".join(
            [
                read_prompt("system.md"),
                read_skill("general.md"),
                read_skill(skill_for_category(challenge.category)),
                language_instruction(language),
                planning_mode_instruction(language),
            ]
        )
        user = {
            "challenge": challenge.as_prompt_dict(),
            "file_tree": file_tree,
            "planning_history": history[-self.recent_history_items :],
            "last_observation": last_observation,
            "flag_candidates": flag_candidates or [],
            "flag_submission_policy": flag_submission_policy(language),
            "remaining_planning_steps": remaining_planning_steps,
            "allowed_actions": planning_action_schema_hint(),
            "planning_goal": planning_goal(language),
        }
        return [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": planning_user_intro(language)
                + json.dumps(user, ensure_ascii=False, indent=2),
            },
        ]


def build_candidate_adjudication_messages(
    *,
    challenge: Challenge,
    candidates: list[dict[str, Any]],
    history: list[dict[str, Any]],
    last_observation: str,
    language: Language = "en",
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": adjudicator_system(language) + "\n\n" + language_instruction(language),
        },
        {
            "role": "user",
            "content": (
                f"{action_schema_hint()}\n\n"
                + json.dumps(
                    {
                        "challenge": challenge.as_prompt_dict(),
                        "flag_candidates": candidates,
                        "recent_history": history[-8:],
                        "last_observation": last_observation,
                        "flag_submission_policy": flag_submission_policy(language),
                        "instruction": adjudicator_instruction(language),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            ),
        },
    ]


def build_repair_messages(
    invalid_response: str,
    error: str,
    schema_hint: str | None = None,
    language: Language = "en",
) -> list[dict[str, str]]:
    schema_hint = schema_hint or action_schema_hint()
    return [
        {
            "role": "system",
            "content": repair_system(language) + "\n\n" + language_instruction(language),
        },
        {
            "role": "user",
            "content": (
                f"{schema_hint}\n\n"
                f"Invalid response:\n{invalid_response}\n\n"
                f"Parser error:\n{error}"
            ),
        },
    ]


def skill_for_category(category: Category) -> str:
    mapping = {
        Category.PWN: "pwn.md",
        Category.REV: "rev.md",
        Category.CRYPTO: "crypto.md",
        Category.WEB: "web.md",
        Category.FORENSICS: "forensics.md",
        Category.MISC: "misc.md",
        Category.UNKNOWN: "unknown.md",
    }
    return mapping[category]


def flag_submission_policy(language: Language) -> str:
    if language == "zh":
        return (
            "不要因为字符串长得像 flag 就提交。submit_flag 必须基于独立证据：目标输出、"
            "验证脚本、重新加密/轮函数校验、oracle 接受、或命令唯一最终输出。"
            "如果只是解密脚本打印了一个看似 flag 的候选，请先运行校验命令；"
            "如果候选缺少证据，继续调查而不是提交。"
        )
    return (
        "Do not submit a string just because it matches the flag format. "
        "submit_flag requires independent evidence: target output, a verifier "
        "script, re-encryption/round-function check, oracle acceptance, or a "
        "command whose sole final output is the flag. If a decrypt script only "
        "prints a flag-looking candidate, run a verification command first; if "
        "evidence is missing, keep investigating instead of submitting."
    )


def read_prompt(name: str) -> str:
    return resources.files(PROMPT_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def read_skill(name: str) -> str:
    return resources.files(SKILLS_PACKAGE).joinpath(name).read_text(encoding="utf-8")
