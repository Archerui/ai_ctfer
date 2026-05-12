from __future__ import annotations

import shutil
from pathlib import Path


EXCLUDED_NAMES = {
    ".ai-ctfer",
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    "target",
}


def should_exclude(path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in path.parts)


def copy_challenge_files(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        if should_exclude(Path(item.name)):
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=copy_ignore, symlinks=False)
        elif item.is_file():
            shutil.copy2(item, target)


def copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in EXCLUDED_NAMES}


def render_file_tree(root: Path, max_entries: int = 120) -> str:
    entries: list[str] = []
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if should_exclude(rel):
            continue
        suffix = "/" if path.is_dir() else ""
        entries.append(f"{rel}{suffix}")
        if len(entries) >= max_entries:
            entries.append(f"... truncated after {max_entries} entries")
            break
    return "\n".join(entries) if entries else "(no files)"
