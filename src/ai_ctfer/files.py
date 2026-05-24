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
    "ai-ctfer-notes.md",
}

RESTORABLE_WORK_FILENAMES = {
    "solve.py",
    "solve.sage",
    "exploit.py",
    "helper.py",
    "verify.py",
    "check.py",
    "pow.py",
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


def restore_previous_work_files(challenge_dir: Path, current_run_dir: Path, work_dir: Path) -> list[Path]:
    runs_dir = challenge_dir.resolve() / ".ai-ctfer" / "runs"
    current_run_dir = current_run_dir.resolve()
    work_dir = work_dir.resolve()
    if not runs_dir.exists():
        return []

    restored: list[Path] = []
    missing = set(RESTORABLE_WORK_FILENAMES)
    for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), reverse=True):
        if run_dir.resolve() == current_run_dir:
            continue
        previous_work = run_dir / "work"
        if not previous_work.exists():
            continue
        for name in sorted(missing):
            source = previous_work / name
            target = work_dir / name
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)
                restored.append(target)
                missing.discard(name)
        if not missing:
            break
    return restored


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
