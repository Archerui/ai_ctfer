from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Language
from .i18n import t


class RunLogger:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.trace_path = run_dir / "trace.jsonl"
        self.candidates_path = run_dir / "flag_candidates.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(cls, challenge_dir: Path) -> "RunLogger":
        runs_dir = challenge_dir / ".ai-ctfer" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        run_dir = runs_dir / stamp
        counter = 1
        while run_dir.exists():
            counter += 1
            run_dir = runs_dir / f"{stamp}_{counter}"
        return cls(run_dir)

    @property
    def work_dir(self) -> Path:
        return self.run_dir / "work"

    def log(self, event: str, **payload: Any) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            **payload,
        }
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_jsonable(record), ensure_ascii=False) + "\n")

    def log_candidate(self, candidate: Any, event: str = "candidate_seen") -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "candidate": candidate,
        }
        with self.candidates_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_jsonable(record), ensure_ascii=False) + "\n")

    def write_final_flag(self, flag: str) -> None:
        (self.run_dir / "final_flag.txt").write_text(flag + "\n", encoding="utf-8")

    def write_summary(self, status: str, details: str, language: Language = "en") -> None:
        content = (
            f"{t(language, 'summary_heading')}\n\n"
            f"{t(language, 'summary_status')} {status}\n\n"
            f"{details}\n"
        )
        (self.run_dir / "summary.md").write_text(content, encoding="utf-8")

    def write_plan(self, content: str) -> None:
        (self.run_dir / "plan.md").write_text(content, encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value
