from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .schema import Remote


NETWORK_COMMANDS = {
    "curl",
    "wget",
    "nc",
    "ncat",
    "netcat",
    "telnet",
    "ssh",
    "ftp",
    "socat",
    "nmap",
}

SAFE_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


@dataclass
class GuardResult:
    allowed: bool
    targets: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_remote_guard(command: str, remote: Remote) -> GuardResult:
    targets = sorted(extract_network_targets(command))
    if not targets:
        return GuardResult(allowed=True)

    allowed_hosts = set(SAFE_LOCAL_HOSTS)
    if remote.host:
        allowed_hosts.add(remote.host.lower())

    outside = [target for target in targets if target.lower() not in allowed_hosts]
    if outside:
        if remote.configured:
            target_description = remote.host or remote.raw or "configured remote"
            warning = (
                "Network warning: command appears to target host(s) outside "
                f"challenge.yml remote={target_description}: {', '.join(outside)}"
            )
        else:
            warning = (
                "Network warning: no remote target is configured, but the command "
                f"appears to contact: {', '.join(outside)}"
            )
        return GuardResult(allowed=True, targets=targets, warnings=[warning])

    return GuardResult(allowed=True, targets=targets)


def extract_network_targets(command: str) -> set[str]:
    targets: set[str] = set()

    for match in re.finditer(r"https?://[^\s'\"<>]+", command):
        parsed = urlparse(match.group(0))
        if parsed.hostname:
            targets.add(parsed.hostname.lower())

    tokens = re.findall(r"[^\s'\"`]+", command)
    for index, token in enumerate(tokens):
        base = token.split("/")[-1]
        if base not in NETWORK_COMMANDS:
            continue
        for candidate in tokens[index + 1 :]:
            if candidate.startswith("-"):
                continue
            host = clean_host_token(candidate)
            if host:
                targets.add(host.lower())
                break

    return targets


def clean_host_token(token: str) -> str | None:
    token = token.strip().strip(",;")
    if "://" in token:
        parsed = urlparse(token)
        return parsed.hostname
    if "@" in token:
        token = token.rsplit("@", 1)[-1]
    token = token.split(":", 1)[0]
    token = token.split("/", 1)[0]
    if token.isdigit():
        return None
    if re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", token):
        return token
    if re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", token):
        return token
    if token in SAFE_LOCAL_HOSTS:
        return token
    return None
