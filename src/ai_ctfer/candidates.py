from __future__ import annotations

import re
from dataclasses import dataclass, field

from .flag import find_flags, is_placeholder_flag, matches_flag


AUTO_ACCEPT_CONFIDENCE = 90
FINAL_ACCEPT_CONFIDENCE = 90


@dataclass
class FlagCandidate:
    value: str
    normalized_value: str
    source: str
    step: int
    confidence: int
    status: str
    sources: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    command: str | None = None
    context: str = ""
    first_seen_step: int = 0
    last_seen_step: int = 0
    seen_count: int = 1

    def __post_init__(self) -> None:
        if not self.sources:
            self.sources = [self.source]
        if not self.first_seen_step:
            self.first_seen_step = self.step
        if not self.last_seen_step:
            self.last_seen_step = self.step

    def prompt_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "source": self.source,
            "sources": self.sources,
            "confidence": self.confidence,
            "status": self.status,
            "seen_count": self.seen_count,
            "first_seen_step": self.first_seen_step,
            "last_seen_step": self.last_seen_step,
            "command": self.command,
            "context": self.context,
            "reasons": self.reasons[-5:],
        }


class FlagCandidateStore:
    def __init__(self, flag_regex: str | None = None) -> None:
        self.flag_regex = flag_regex
        self._by_normalized: dict[str, FlagCandidate] = {}
        self._all: list[FlagCandidate] = []

    @property
    def all(self) -> list[FlagCandidate]:
        return list(self._all)

    def visible(self) -> list[FlagCandidate]:
        return [c for c in self._all if c.status != "rejected"]

    def prompt_items(self) -> list[dict[str, object]]:
        return [candidate.prompt_dict() for candidate in self.visible()]

    def add_from_text(
        self,
        text: str,
        *,
        source: str,
        step: int,
        command: str | None = None,
    ) -> list[FlagCandidate]:
        added: list[FlagCandidate] = []
        for value in find_flags(text, self.flag_regex):
            context = context_for_value(text, value)
            candidate = self.add(
                value,
                source=source,
                step=step,
                command=command,
                context=context,
            )
            if candidate is not None:
                added.append(candidate)
        return added

    def add(
        self,
        value: str,
        *,
        source: str,
        step: int,
        command: str | None = None,
        context: str = "",
    ) -> FlagCandidate | None:
        normalized = normalize_flag_candidate(value)
        if not normalized or is_placeholder_flag(normalized):
            return None
        if not matches_flag(normalized, self.flag_regex):
            return None

        confidence, status, reasons = score_candidate(
            normalized,
            source=source,
            command=command,
            context=context,
            flag_regex=self.flag_regex,
        )
        existing = self._by_normalized.get(normalized)
        if existing:
            existing.seen_count += 1
            existing.last_seen_step = step
            if source not in existing.sources:
                existing.sources.append(source)
            if confidence > existing.confidence:
                existing.confidence = confidence
                existing.source = source
                existing.command = command
                existing.context = context
            existing.reasons = merge_reasons(existing.reasons, reasons)
            if status == "accepted" and candidate_is_auto_acceptable(existing):
                existing.status = "accepted"
            return existing

        candidate = FlagCandidate(
            value=normalized,
            normalized_value=normalized,
            source=source,
            sources=[source],
            step=step,
            command=command,
            context=context,
            confidence=confidence,
            status=status,
            reasons=reasons,
        )
        self._by_normalized[normalized] = candidate
        self._all.append(candidate)
        return candidate

    def accepted_candidate(self) -> FlagCandidate | None:
        accepted = [
            c
            for c in self.visible()
            if c.status == "accepted" and candidate_is_finalizable(c)
        ]
        if not accepted:
            return None
        return sorted(accepted, key=lambda c: (c.confidence, c.seen_count), reverse=True)[0]

    def best_candidate(self) -> FlagCandidate | None:
        visible = self.visible()
        if not visible:
            return None
        return sorted(
            visible,
            key=lambda c: (c.confidence, c.seen_count, -c.first_seen_step),
            reverse=True,
        )[0]

    def has_candidate(self, value: str) -> bool:
        return normalize_flag_candidate(value) in self._by_normalized

    def mark_accepted(self, value: str, reason: str) -> FlagCandidate | None:
        candidate = self._by_normalized.get(normalize_flag_candidate(value))
        if candidate is None:
            return None
        candidate.status = "accepted"
        candidate.reasons = merge_reasons(candidate.reasons, [reason])
        candidate.confidence = max(candidate.confidence, AUTO_ACCEPT_CONFIDENCE)
        return candidate

    def mark_rejected(self, value: str, reason: str) -> FlagCandidate | None:
        candidate = self._by_normalized.get(normalize_flag_candidate(value))
        if candidate is None:
            return None
        candidate.status = "rejected"
        candidate.reasons = merge_reasons(candidate.reasons, [reason])
        return candidate


def normalize_flag_candidate(value: str) -> str:
    return value.strip().strip("`'\"")


def context_for_value(text: str, value: str, max_chars: int = 240) -> str:
    for line in text.splitlines():
        if value in line:
            return compact_context(line, max_chars)
    index = text.find(value)
    if index < 0:
        return ""
    start = max(0, index - max_chars // 2)
    end = min(len(text), index + len(value) + max_chars // 2)
    return compact_context(text[start:end], max_chars)


def compact_context(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def score_candidate(
    value: str,
    *,
    source: str,
    command: str | None,
    context: str,
    flag_regex: str | None,
) -> tuple[int, str, list[str]]:
    score = 35
    reasons: list[str] = ["matches configured/default flag pattern"]
    lower_context = context.lower()
    lower_command = (command or "").lower()

    if source in {"stdout", "stderr", "command_output"}:
        score += 15
        reasons.append(f"observed in {source}")
    if source == "submit_flag":
        score += 5
        reasons.append("explicitly submitted by model; requires independent evidence")
    if flag_regex and re.search(flag_regex, value):
        score += 10
        reasons.append("matches configured flag pattern")

    stripped_context = context.strip()
    if stripped_context == value:
        score += 40
        reasons.append("candidate is the sole command output")
    elif stripped_context.endswith(value):
        score += 10
        reasons.append("candidate is the main command output")

    if strong_validation_context(lower_context):
        score += 30
        reasons.append("near strong verification label")
    elif re.search(r"\b(flag|plaintext|decoded|decrypted|result)\b\s*[:=]", lower_context):
        score += 10
        reasons.append("near derived-output label")
    elif any(word in lower_context for word in ("found", "solved", "accepted")):
        score += 10
        reasons.append("near positive evidence word")

    if any(tool in lower_command for tool in ("rsa_factordb", "solve.py", "exploit.py")):
        score += 10
        reasons.append("produced by solve/helper script")
    if any(tool in lower_command for tool in ("grep", "strings", "ripgrep", "rg ")):
        score += 10
        reasons.append("produced by explicit flag search")

    if weak_evidence_context(lower_context, lower_command):
        score -= 45
        reasons.append("appears in metadata/source/example context")

    score = max(0, min(100, score))
    status = (
        "accepted"
        if score >= AUTO_ACCEPT_CONFIDENCE
        and source != "submit_flag"
        and candidate_context_is_auto_acceptable(
            source=source,
            command=lower_command,
            context=lower_context,
        )
        else "pending"
    )
    if status == "accepted":
        reasons.append("auto-accepted by confidence threshold and evidence policy")
    return score, status, reasons


def strong_validation_context(lower_context: str) -> bool:
    return bool(
        re.search(
            r"\b("
            r"verified|verification passed|round[- ]?trip|re[- ]?encrypt|"
            r"matches ciphertext|oracle accepted|correct flag|successfully decrypted|"
            r"valid plaintext|check passed"
            r")\b",
            lower_context,
        )
    )


def candidate_context_is_auto_acceptable(
    *,
    source: str,
    command: str,
    context: str,
) -> bool:
    if source == "submit_flag":
        return False
    if weak_evidence_context(context, command):
        return False
    if context.strip() and re.fullmatch(DEFAULT_FLAG_LIKE_CONTEXT_RE, context.strip()):
        return True
    if strong_validation_context(context):
        return True
    return False


DEFAULT_FLAG_LIKE_CONTEXT_RE = re.compile(r"[A-Za-z0-9_]{2,32}\{[^}\r\n]{1,512}\}")


def candidate_is_auto_acceptable(candidate: FlagCandidate) -> bool:
    return candidate_is_finalizable(candidate) and candidate.confidence >= AUTO_ACCEPT_CONFIDENCE


def candidate_is_finalizable(candidate: FlagCandidate) -> bool:
    if not any(source != "submit_flag" for source in candidate.sources):
        return False
    lower_context = candidate.context.lower()
    lower_command = (candidate.command or "").lower()
    return candidate_context_is_auto_acceptable(
        source=candidate.source,
        command=lower_command,
        context=lower_context,
    ) or any("sole command output" in reason for reason in candidate.reasons)


def weak_evidence_context(lower_context: str, lower_command: str) -> bool:
    weak_context_markers = (
        "flag_format",
        "format is",
        "flag regex",
        "flag_regex",
        "allowed_actions",
        "example",
        "placeholder",
        "sample",
    )
    weak_commands = ("cat ", "sed ", "head ", "tail ", "less ", "challenge.yml")
    return any(marker in lower_context for marker in weak_context_markers) or any(
        marker in lower_command for marker in weak_commands
    )


def merge_reasons(existing: list[str], new: list[str]) -> list[str]:
    merged = list(existing)
    for reason in new:
        if reason not in merged:
            merged.append(reason)
    return merged
