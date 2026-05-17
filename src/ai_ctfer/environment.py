from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .executor import CommandResult
from .schema import Challenge


URL_RE = re.compile(r"https?://[^\s\"'<>),;]+")
NC_RE = re.compile(r"\bnc\s+([A-Za-z0-9_.-]+)\s+(\d{1,5})\b")
HOST_PORT_RE = re.compile(r"\b([A-Za-z0-9_.-]+\.[A-Za-z]{2,63}):(\d{1,5})\b")
DOMAIN_RE = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}\b")


@dataclass(frozen=True)
class EnvironmentIssue:
    reason: str
    target: str | None = None


def challenge_text_for_targets(challenge: Challenge) -> str:
    parts = [
        challenge.name or "",
        challenge.description or "",
        challenge.flag_format or "",
    ]
    remote = challenge.remote.as_prompt_value()
    if remote:
        parts.append(str(remote))
    return "\n".join(parts)


def extract_targets_from_challenge(challenge: Challenge) -> list[str]:
    return extract_targets(challenge_text_for_targets(challenge))


def extract_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in URL_RE.finditer(text):
        parsed = urlparse(match.group(0).rstrip("/"))
        if parsed.netloc:
            targets.append(parsed.netloc)
    for host, port in NC_RE.findall(text):
        targets.append(f"{host}:{port}")
        targets.append(host)
    for host, port in HOST_PORT_RE.findall(text):
        targets.append(f"{host}:{port}")
        targets.append(host)
    for match in DOMAIN_RE.finditer(text):
        targets.append(match.group(0))
    return unique_targets(targets)


def unique_targets(targets: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for target in targets:
        normalized = normalize_target(target)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def normalize_target(target: str) -> str:
    target = target.strip().strip(".,;)'\"`<>")
    if not target:
        return ""
    if target.startswith(("http://", "https://")):
        parsed = urlparse(target)
        target = parsed.netloc or parsed.path
    return target.rstrip("/")


def detect_environment_issue(result: CommandResult, challenge: Challenge) -> EnvironmentIssue | None:
    targets = extract_targets_from_challenge(challenge)
    if not targets or not command_mentions_target(result.command, targets):
        return None

    combined = f"{result.stdout}\n{result.stderr}".lower()
    target = first_mentioned_target(result.command, targets)
    if result.timed_out and command_checks_base_target(result.command, targets):
        return EnvironmentIssue("base target command timed out", target)

    network_patterns = (
        "could not resolve host",
        "failed to connect",
        "connection refused",
        "connection reset",
        "connection timed out",
        "no route to host",
        "temporary failure in name resolution",
        "ssl_connect",
        "tls handshake",
    )
    if any(pattern in combined for pattern in network_patterns):
        return EnvironmentIssue("network connection to current target failed", target)

    if command_checks_base_target(result.command, targets) and re.search(
        r"http/\S+\s+(404|410|502|503|504)\b", combined
    ):
        return EnvironmentIssue("base web target returned an unavailable HTTP status", target)

    return None


def command_mentions_target(command: str, targets: list[str]) -> bool:
    normalized_command = command.lower()
    return any(target.lower() in normalized_command for target in targets)


def first_mentioned_target(command: str, targets: list[str]) -> str | None:
    lower_command = command.lower()
    for target in targets:
        if target.lower() in lower_command:
            return target
    return targets[0] if targets else None


def command_checks_base_target(command: str, targets: list[str]) -> bool:
    urls = [match.group(0).rstrip(".,;)'\"`<>") for match in URL_RE.finditer(command)]
    current_urls = []
    for url in urls:
        parsed = urlparse(url)
        parsed_host = parsed.hostname or parsed.netloc
        parsed_netloc = parsed.netloc.lower()
        if any(
            parsed_netloc == target.lower() or parsed_host.lower() == target.lower().split(":", 1)[0]
            for target in targets
        ):
            current_urls.append(parsed)
    if current_urls:
        return all(parsed.path in {"", "/"} for parsed in current_urls)

    tokens = re.split(r"\s+", command)
    for token in tokens:
        cleaned = normalize_target(token)
        if cleaned in targets:
            return True
    return False
