from __future__ import annotations

import re


DEFAULT_FLAG_PATTERNS = [
    r"flag\{[^}\r\n]{1,512}\}",
    r"FLAG\{[^}\r\n]{1,512}\}",
    r"CTF\{[^}\r\n]{1,512}\}",
    r"[A-Za-z0-9_]+CTF\{[^}\r\n]{1,512}\}",
    r"[A-Za-z0-9_]{2,32}\{[^}\r\n]{1,512}\}",
]

PLACEHOLDER_INNERS = {
    "...",
    "example",
    "placeholder",
    "redacted",
    "your_flag",
    "your_flag_here",
}


def is_placeholder_flag(value: str) -> bool:
    inner_match = re.fullmatch(r"[A-Za-z0-9_]{2,32}\{([^}\r\n]+)\}", value, re.IGNORECASE)
    if not inner_match:
        return False
    inner = inner_match.group(1).strip().lower()
    return inner in PLACEHOLDER_INNERS or inner.startswith("...")


def find_flags(text: str, flag_regex: str | None = None) -> list[str]:
    patterns = [flag_regex] if flag_regex else []
    patterns.extend(DEFAULT_FLAG_PATTERNS)

    seen: set[str] = set()
    found: list[str] = []
    for pattern in patterns:
        if not pattern:
            continue
        for match in re.finditer(pattern, text):
            value = match.group(0)
            if is_placeholder_flag(value):
                continue
            if value not in seen:
                seen.add(value)
                found.append(value)
    return found


def matches_flag(flag: str, flag_regex: str | None = None) -> bool:
    if is_placeholder_flag(flag):
        return False
    if flag_regex:
        return bool(re.search(flag_regex, flag))
    return bool(find_flags(flag))
