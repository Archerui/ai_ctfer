from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .executor import DEFAULT_IMAGE_NAME
from .notebook import NOTEBOOK_FILENAME


@dataclass
class CleanResult:
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def clean_ai_ctfer(
    *,
    workdir: Path,
    runs: bool = False,
    image: bool = False,
    docker_cache: bool = False,
    all_targets: bool = False,
) -> CleanResult:
    if all_targets or not any([runs, image, docker_cache]):
        runs = image = docker_cache = True

    result = CleanResult()

    if runs:
        workdir = workdir.resolve()
        runs_dir = workdir / ".ai-ctfer"
        if runs_dir.exists():
            shutil.rmtree(runs_dir)
            result.messages.append(f"removed {runs_dir}")
        else:
            result.messages.append(f"not found: {runs_dir}")
        notes_path = workdir / NOTEBOOK_FILENAME
        if notes_path.exists():
            notes_path.unlink()
            result.messages.append(f"removed {notes_path}")
        else:
            result.messages.append(f"not found: {notes_path}")

    if image:
        run_docker_cleanup(["docker", "rmi", DEFAULT_IMAGE_NAME], result)

    if docker_cache:
        run_docker_cleanup(["docker", "builder", "prune", "-f"], result)

    return result


def run_docker_cleanup(command: list[str], result: CleanResult) -> None:
    if not shutil.which("docker"):
        result.errors.append("docker command not found")
        return
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode == 0:
        result.messages.append(output or " ".join(command))
    else:
        result.errors.append(output or f"{' '.join(command)} failed")
