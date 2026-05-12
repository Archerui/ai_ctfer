from __future__ import annotations

import shutil
import subprocess
import time
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .remote_guard import check_remote_guard
from .schema import Remote


DEFAULT_IMAGE_NAME = "ai-ctfer-sandbox:latest"


def docker_network_mode(_remote: Remote) -> str:
    return "bridge"


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool = False
    truncated: bool = False
    guard_warnings: list[str] | None = None

    def observation(self) -> str:
        status = "timed out" if self.timed_out else f"exit {self.exit_code}"
        warning_text = ""
        if self.guard_warnings:
            warning_text = "\nGuard warnings:\n" + "\n".join(self.guard_warnings)
        return (
            f"Command: {self.command}\n"
            f"Status: {status} in {self.duration_sec:.2f}s\n"
            f"Stdout:\n{self.stdout or '(empty)'}\n"
            f"Stderr:\n{self.stderr or '(empty)'}"
            f"{warning_text}"
        )


def truncate_text(text: str | bytes | None, max_chars: int) -> tuple[str, bool]:
    if text is None:
        return "", False
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if len(text) <= max_chars:
        return text, False
    marker = f"\n... truncated to {max_chars} characters ...\n"
    keep = max(0, max_chars - len(marker))
    return text[:keep] + marker, True


class DockerExecutor:
    def __init__(self, image_name: str = DEFAULT_IMAGE_NAME) -> None:
        self.image_name = image_name
        self._image_ready = False

    def ensure_available(self) -> None:
        if not shutil.which("docker"):
            raise RuntimeError("docker command not found. Install Docker Engine first.")

    def ensure_image(self) -> None:
        if self._image_ready:
            return
        self.ensure_available()
        inspect = subprocess.run(
            ["docker", "image", "inspect", self.image_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if inspect.returncode != 0:
            with resources.as_file(
                resources.files("ai_ctfer").joinpath("sandbox")
            ) as sandbox_dir:
                subprocess.run(
                    [
                        "docker",
                        "build",
                        "-t",
                        self.image_name,
                        "-f",
                        str(sandbox_dir / "Dockerfile"),
                        str(sandbox_dir),
                    ],
                    check=True,
                )
        self._image_ready = True

    def run(
        self,
        command: str,
        workdir: Path,
        remote: Remote,
        timeout_sec: int,
        max_output_chars: int,
    ) -> CommandResult:
        guard = check_remote_guard(command, remote)
        if not guard.allowed:
            return CommandResult(
                command=command,
                exit_code=126,
                stdout="",
                stderr="\n".join(guard.warnings),
                duration_sec=0.0,
                guard_warnings=guard.warnings,
            )

        self.ensure_image()
        network = docker_network_mode(remote)
        docker_command = [
            "docker",
            "run",
            "--rm",
            "--network",
            network,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--pids-limit",
            "256",
            "--security-opt",
            "no-new-privileges",
            "--cap-drop",
            "ALL",
            "-v",
            f"{workdir.resolve()}:/work:rw",
            "-w",
            "/work",
            self.image_name,
            "bash",
            "-lc",
            command,
        ]

        started = time.monotonic()
        try:
            completed = subprocess.run(
                docker_command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
                check=False,
            )
            duration = time.monotonic() - started
            stdout, stdout_truncated = truncate_text(
                completed.stdout, max_output_chars
            )
            stderr, stderr_truncated = truncate_text(
                completed.stderr, max_output_chars
            )
            return CommandResult(
                command=command,
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_sec=duration,
                truncated=stdout_truncated or stderr_truncated,
                guard_warnings=guard.warnings,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            stdout, stdout_truncated = truncate_text(exc.stdout, max_output_chars)
            stderr, stderr_truncated = truncate_text(exc.stderr, max_output_chars)
            return CommandResult(
                command=command,
                exit_code=124,
                stdout=stdout,
                stderr=stderr,
                duration_sec=duration,
                timed_out=True,
                truncated=stdout_truncated or stderr_truncated,
                guard_warnings=guard.warnings,
            )
