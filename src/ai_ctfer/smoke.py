from __future__ import annotations

from pathlib import Path

from .schema import SAMPLE_CHALLENGE_YAML


SMOKE_FLAG = "flag{deepseek_smoke}"
SMOKE_HEX = SMOKE_FLAG.encode().hex()


def write_smoke_challenge(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "message.hex").write_text(SMOKE_HEX + "\n", encoding="utf-8")
    (directory / "challenge.yml").write_text(
        SAMPLE_CHALLENGE_YAML.replace("example-challenge", "deepseek-smoke")
        .replace("category: unknown", "category: crypto")
        .replace(
            "Briefly describe the challenge here. Include any nc/http endpoint text from\n"
            "  the challenge page if useful.",
            "The file message.hex contains a hex-encoded flag. Decode it.",
        )
        .replace("max_steps: 50", "max_steps: 5"),
        encoding="utf-8",
    )
