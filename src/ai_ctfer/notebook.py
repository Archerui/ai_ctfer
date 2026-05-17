from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Language
from .environment import extract_targets_from_challenge, normalize_target
from .executor import CommandResult
from .schema import Challenge


NOTEBOOK_FILENAME = "ai-ctfer-notes.md"
TARGET_MARKER_PREFIX = "<!-- ai-ctfer-current-targets:"
TARGET_MARKER_SUFFIX = "-->"
MAX_NOTEBOOK_PROMPT_CHARS = 14000


@dataclass
class Notebook:
    path: Path
    challenge: Challenge
    language: Language = "en"

    @classmethod
    def load(cls, challenge_dir: Path, challenge: Challenge, language: Language) -> "Notebook":
        notebook = cls(challenge_dir / NOTEBOOK_FILENAME, challenge, language)
        notebook.ensure_loaded_and_synced()
        return notebook

    def ensure_loaded_and_synced(self) -> None:
        current_targets = extract_targets_from_challenge(self.challenge)
        if not self.path.exists():
            self.path.write_text(self._initial_content(current_targets), encoding="utf-8")
            return

        content = self.path.read_text(encoding="utf-8")
        old_targets = read_target_marker(content)
        updated = content
        if old_targets and current_targets and set(old_targets) != set(current_targets):
            replacement = current_targets[0]
            for old_target in old_targets:
                if old_target not in current_targets:
                    updated = updated.replace(old_target, replacement)
            updated = (
                updated.rstrip()
                + "\n\n"
                + self._line(
                    en=(
                        "Target sync: replaced previous target value(s) "
                        f"with current challenge target(s) {', '.join(current_targets)}."
                    ),
                    zh=(
                        "地址同步：已将旧目标值更新为当前题面目标 "
                        f"{', '.join(current_targets)}。"
                    ),
                )
                + "\n"
            )
        updated = write_target_marker(updated, current_targets)
        if updated != content:
            self.path.write_text(updated, encoding="utf-8")

    def start_run(self, run_id: str) -> None:
        targets = extract_targets_from_challenge(self.challenge)
        self.append(
            "\n"
            + self._line(en=f"## Run {run_id}", zh=f"## 运行 {run_id}")
            + "\n"
            + self._line(en=f"- Started: {timestamp()}", zh=f"- 开始时间：{timestamp()}")
            + "\n"
            + self._line(
                en=f"- Current targets from challenge.yml: {', '.join(targets) if targets else '(none)'}",
                zh=f"- 当前 challenge.yml 中的目标地址：{', '.join(targets) if targets else '（无）'}",
            )
            + "\n"
        )

    def prompt_text(self) -> str:
        if not self.path.exists():
            return ""
        content = self.path.read_text(encoding="utf-8").strip()
        if len(content) <= MAX_NOTEBOOK_PROMPT_CHARS:
            return content
        return (
            content[:3000].rstrip()
            + "\n\n...[notebook middle truncated]...\n\n"
            + content[-(MAX_NOTEBOOK_PROMPT_CHARS - 3040) :].lstrip()
        )

    def record_plan(self, plan: Any) -> None:
        self.append(
            "\n"
            + self._line(en="### Plan", zh="### 计划")
            + "\n"
            + self._line(en=f"- Summary: {plan.summary}", zh=f"- 摘要：{plan.summary}")
            + "\n"
            + self._line(
                en=f"- Chosen strategy: {plan.chosen_strategy}",
                zh=f"- 选定策略：{plan.chosen_strategy}",
            )
            + "\n"
        )

    def record_command(
        self,
        *,
        phase: str,
        step: int,
        command: str,
        rationale: str,
        result: CommandResult,
        candidate_values: list[str],
        environment_issue: str | None = None,
    ) -> None:
        lines = [
            "",
            self._line(en=f"### {phase} command {step}", zh=f"### {phase} 命令 {step}"),
            self._line(en=f"- Intent: {rationale}", zh=f"- 意图：{rationale}"),
            self._line(en=f"- Command: `{shorten_inline(command, 420)}`", zh=f"- 命令：`{shorten_inline(command, 420)}`"),
            self._line(
                en=(
                    f"- Result: exit={result.exit_code}, timed_out={result.timed_out}, "
                    f"truncated={result.truncated}"
                ),
                zh=(
                    f"- 结果：退出码={result.exit_code}，超时={result.timed_out}，"
                    f"截断={result.truncated}"
                ),
            ),
        ]
        if environment_issue:
            lines.append(self._line(en=f"- Environment issue: {environment_issue}", zh=f"- 环境异常：{environment_issue}"))
        if candidate_values:
            lines.append(self._line(en=f"- Flag candidates: {', '.join(candidate_values)}", zh=f"- Flag 候选：{', '.join(candidate_values)}"))
        excerpt = command_output_excerpt(result)
        if excerpt:
            lines.extend(["", "```text", excerpt, "```"])
        self.append("\n".join(lines) + "\n")

    def record_submit(self, *, step: int, flag: str, rationale: str) -> None:
        self.append(
            "\n"
            + self._line(en=f"### Submitted candidate {step}", zh=f"### 提交候选 {step}")
            + "\n"
            + f"- `{flag}`\n"
            + self._line(en=f"- Rationale: {rationale}", zh=f"- 理由：{rationale}")
            + "\n"
        )

    def record_candidate_validation(self, *, flag: str, verdict: str, confidence: int, rationale: str) -> None:
        self.append(
            "\n"
            + self._line(en="### Candidate validation", zh="### 候选校验")
            + "\n"
            + f"- `{flag}`\n"
            + self._line(en=f"- Verdict: {verdict} ({confidence})", zh=f"- 结论：{verdict}（{confidence}）")
            + "\n"
            + self._line(en=f"- Rationale: {rationale}", zh=f"- 理由：{rationale}")
            + "\n"
        )

    def record_finish(self, status: str, reason: str) -> None:
        self.append(
            "\n"
            + self._line(en="### Run finished", zh="### 运行结束")
            + "\n"
            + self._line(en=f"- Status: {status}", zh=f"- 状态：{status}")
            + "\n"
            + self._line(en=f"- Reason: {reason}", zh=f"- 原因：{reason}")
            + "\n"
        )

    def append(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(text)

    def _initial_content(self, targets: list[str]) -> str:
        return (
            "# ai-ctfer notes\n\n"
            + target_marker(targets)
            + "\n\n"
            + self._line(
                en=(
                    "This file is maintained automatically by ai-ctfer. It records "
                    "attempts, results, candidates, and environment notes across runs."
                ),
                zh=(
                    "这个文件由 ai-ctfer 自动维护，用来跨运行记录尝试、结果、候选 "
                    "flag 和环境状态。"
                ),
            )
            + "\n"
            + self._line(
                en=(
                    "Current challenge.yml targets are authoritative. If the remote "
                    "environment is restarted and the address changes, update "
                    "challenge.yml before running solve again."
                ),
                zh=(
                    "当前 challenge.yml 中的地址始终优先。如果远程环境重启导致地址变化，"
                    "请先更新 challenge.yml，再重新运行 solve。"
                ),
            )
            + "\n"
        )

    def _line(self, *, en: str, zh: str) -> str:
        return zh if self.language == "zh" else en


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def target_marker(targets: list[str]) -> str:
    return f"{TARGET_MARKER_PREFIX} {json.dumps(targets, ensure_ascii=False)} {TARGET_MARKER_SUFFIX}"


def read_target_marker(content: str) -> list[str]:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith(TARGET_MARKER_PREFIX):
            continue
        payload = stripped[len(TARGET_MARKER_PREFIX) :].removesuffix(TARGET_MARKER_SUFFIX).strip()
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, list):
            return []
        return [normalize_target(str(item)) for item in raw if normalize_target(str(item))]
    return []


def write_target_marker(content: str, targets: list[str]) -> str:
    marker = target_marker(targets)
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith(TARGET_MARKER_PREFIX):
            lines[index] = marker
            trailing = "\n" if content.endswith("\n") else ""
            return "\n".join(lines) + trailing
    insertion = "# ai-ctfer notes\n\n" if not content.strip() else ""
    return insertion + marker + "\n\n" + content.lstrip()


def shorten_inline(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text.replace("`", "'")
    return (text[: max_chars - 3] + "...").replace("`", "'")


def command_output_excerpt(result: CommandResult, max_chars: int = 1200) -> str:
    combined = ""
    if result.stdout:
        combined += "stdout:\n" + result.stdout.strip()
    if result.stderr:
        combined += ("\n\n" if combined else "") + "stderr:\n" + result.stderr.strip()
    combined = combined.strip()
    if not combined:
        return ""
    if len(combined) <= max_chars:
        return combined
    return combined[: max_chars // 2].rstrip() + "\n...[truncated]...\n" + combined[-max_chars // 2 :].lstrip()
