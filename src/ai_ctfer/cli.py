from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from .artifacts import load_trace_events, summarize_run_duration, write_success_artifacts
from .clean import clean_ai_ctfer
from .config import AppConfig, config_path, load_config, normalize_language, save_config
from .executor import DockerExecutor
from .i18n import display_language, phase_name, t
from .llm import StaticLLMClient, create_llm_client
from .loop import AgentLoop
from .model_interface import model_names_help, provider_api_key_statuses
from .schema import SAMPLE_CHALLENGE_YAML, load_challenge
from .smoke import SMOKE_FLAG, SMOKE_HEX, write_smoke_challenge


app = typer.Typer(
    no_args_is_help=True,
    help="Single-challenge CTF solving agent.",
)
console = Console()


@app.command("language")
def set_language(
    value: Annotated[
        str | None,
        typer.Argument(help="Language to use: zh/cn/中文 or en/english."),
    ] = None,
) -> None:
    """Show or persist the CLI/agent output language."""
    config = load_config()
    if value is None:
        console.print(t(config.language, "current_language", language=display_language(config.language)))
        console.print(f"{t(config.language, 'config_path')} {config_path()}")
        return

    try:
        language = normalize_language(value)
    except ValueError:
        console.print(f"[red]{t(config.language, 'language_value_error')}[/red]")
        raise typer.Exit(code=1) from None

    path = save_config(AppConfig(language=language))
    console.print(t(language, "language_set", language=display_language(language)))
    console.print(f"{t(language, 'config_path')} {path}")


@app.command()
def doctor(
    strict: Annotated[
        bool,
        typer.Option(
            "--strict/--no-strict",
            help="Exit non-zero when a required check fails.",
        ),
    ] = False,
) -> None:
    """Check local runtime prerequisites."""
    language = load_config().language
    key_statuses = provider_api_key_statuses()
    any_llm_key_ok = any(status["ok"] for status in key_statuses)
    checks = [
        ("Python", sys.version.split()[0], True, True),
    ]
    for status in key_statuses:
        checks.append(
            (
                str(status["env"]),
                t(language, "doctor_set") if status["ok"] else t(language, "doctor_missing"),
                bool(status["ok"]),
                False,
            )
        )
    checks.extend(
        [
        (
            "LLM API key",
            _llm_key_status_from_provider_checks(key_statuses, language),
            any_llm_key_ok,
            True,
        ),
        (
            "docker command",
            shutil.which("docker") or t(language, "doctor_missing"),
            bool(shutil.which("docker")),
            True,
        ),
        ]
    )

    docker_version = t(language, "doctor_not_checked")
    docker_ok = False
    docker_daemon = t(language, "doctor_not_checked")
    docker_daemon_ok = False
    if shutil.which("docker"):
        completed = subprocess.run(
            ["docker", "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        docker_version = (completed.stdout or completed.stderr).strip()
        docker_ok = completed.returncode == 0
        info = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        docker_daemon = (info.stdout or info.stderr).strip() or t(language, "doctor_unavailable")
        docker_daemon_ok = info.returncode == 0
    checks.append(("docker --version", docker_version, docker_ok, True))
    checks.append(("docker daemon", docker_daemon, docker_daemon_ok, True))

    for package in ["openai", "pydantic", "yaml", "typer", "rich"]:
        ok = _importable(package)
        checks.append(
            (
                f"python package {package}",
                t(language, "doctor_importable") if ok else t(language, "doctor_missing"),
                ok,
                True,
            )
        )

    table = Table(title=t(language, "doctor_title"))
    table.add_column(t(language, "doctor_check"))
    table.add_column(t(language, "doctor_status"))
    table.add_column(t(language, "doctor_ok"))
    for name, status, ok, _required in checks:
        table.add_row(name, status, t(language, "doctor_yes") if ok else t(language, "doctor_no"))
    console.print(table)

    if strict and not all(ok for _, _, ok, required in checks if required):
        raise typer.Exit(code=1)


@app.command("i")
@app.command()
def init(
    workdir: Annotated[Path, typer.Argument(help="Challenge directory.")] = Path("."),
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite an existing challenge.yml."),
    ] = False,
) -> None:
    """Create a sample challenge.yml."""
    language = load_config().language
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / "challenge.yml"
    if target.exists() and not force:
        console.print(f"[yellow]{t(language, 'already_exists', path=target)}[/yellow]")
        raise typer.Exit(code=1)
    target.write_text(SAMPLE_CHALLENGE_YAML, encoding="utf-8")
    console.print(f"[green]{t(language, 'wrote')}[/green] {target}")


@app.command("s")
@app.command()
def solve(
    workdir: Annotated[Path, typer.Argument(help="Challenge directory.")] = Path("."),
    schema: Annotated[
        Path | None,
        typer.Option("--schema", help="Path to challenge.yml. Defaults to WORKDIR/challenge.yml."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help=f"Override schema model: {model_names_help()}."),
    ] = None,
    max_steps: Annotated[
        int | None,
        typer.Option("--max-steps", help="Override schema max step count."),
    ] = None,
    fake_llm_response: Annotated[
        str | None,
        typer.Option(
            "--fake-llm-response",
            help="Testing hook: use this fixed JSON response instead of DeepSeek.",
            hidden=True,
        ),
    ] = None,
) -> None:
    """Run the single-agent solver loop for one challenge."""
    language = load_config().language
    workdir = workdir.resolve()
    challenge = load_challenge(workdir, schema.resolve() if schema else None)
    if model:
        challenge.model.name = model
    if max_steps is not None:
        challenge.limits.max_steps = max_steps

    llm = StaticLLMClient(fake_llm_response) if fake_llm_response else create_llm_client(challenge.model)
    executor = DockerExecutor()
    result = AgentLoop(
        challenge=challenge,
        challenge_dir=workdir,
        llm=llm,
        executor=executor,
        on_plan=lambda plan: _print_plan(plan, language),
        on_event=lambda event, payload: _print_event(event, payload, language),
        language=language,
    ).run()

    if result.flag:
        elapsed = summarize_run_duration(load_trace_events(result.run_dir), language)
        console.print(f"[green]{t(language, 'solved')}[/green] {result.flag}")
        console.print(f"[green]{_message(language, en='Elapsed:', zh='总用时：')}[/green] {elapsed}")
        try:
            artifacts = write_success_artifacts(
                challenge_dir=workdir,
                run_dir=result.run_dir,
                challenge=challenge,
                flag=result.flag,
                language=language,
            )
        except Exception as exc:
            console.print(
                f"[yellow]{_message(language, en='Solved, but artifact generation failed:', zh='已解出，但整理 writeup/脚本失败：')}[/yellow] {exc}"
            )
        else:
            console.print(f"[green]{t(language, 'wrote')}[/green] {artifacts.writeup_path}")
            console.print(f"[green]{t(language, 'wrote')}[/green] {artifacts.solve_path}")
    else:
        console.print(f"[yellow]{t(language, 'finished_status')}[/yellow] {result.status}")
        if result.reason:
            console.print(result.reason)

    if result.status not in {"success", "done"}:
        raise typer.Exit(code=1)


@app.command("c")
@app.command()
def clean(
    workdir: Annotated[Path, typer.Argument(help="Challenge directory.")] = Path("."),
    runs: Annotated[
        bool,
        typer.Option("--runs", help="Remove WORKDIR/.ai-ctfer run artifacts."),
    ] = False,
    image: Annotated[
        bool,
        typer.Option("--image", help="Remove the ai-ctfer Docker image."),
    ] = False,
    docker_cache: Annotated[
        bool,
        typer.Option("--docker-cache", help="Prune Docker build cache."),
    ] = False,
    all_targets: Annotated[
        bool,
        typer.Option(
            "--all",
            help=(
                "Clean runs, Docker image, and Docker build cache. "
                "This is the default when no target option is passed."
            ),
        ),
    ] = False,
) -> None:
    """Clean ai-ctfer run artifacts and optional Docker resources."""
    language = load_config().language
    result = clean_ai_ctfer(
        workdir=workdir,
        runs=runs,
        image=image,
        docker_cache=docker_cache,
        all_targets=all_targets,
    )
    for message in result.messages:
        console.print(f"[green]{_message(language, en='clean:', zh='清理：')}[/green] {message}")
    for error in result.errors:
        console.print(f"[red]{_message(language, en='clean error:', zh='清理错误：')}[/red] {error}")
    if result.errors:
        raise typer.Exit(code=1)


@app.command()
def smoke(
    real_llm: Annotated[
        bool,
        typer.Option(
            "--real-llm/--fake-llm",
        help="Use the configured real LLM for the smoke test. The fake LLM path is free.",
        ),
    ] = False,
    max_steps: Annotated[
        int,
        typer.Option("--max-steps", help="Maximum agent steps for the smoke test."),
    ] = 5,
) -> None:
    """Run a tiny local challenge through the Docker agent loop."""
    language = load_config().language
    smoke_dir = Path(tempfile.mkdtemp(prefix="ai-ctfer-smoke."))
    write_smoke_challenge(smoke_dir)
    challenge = load_challenge(smoke_dir)
    challenge.limits.max_steps = max_steps

    if real_llm:
        llm = create_llm_client(challenge.model)
    else:
        command = (
            "python3 -c \"import codecs; "
            f"print(codecs.decode('{SMOKE_HEX}', 'hex').decode())\""
        )
        llm = StaticLLMClient(
            json.dumps(
                {
                    "action": "run_command",
                    "command": command,
                    "rationale": "解码 smoke 测试 flag。" if language == "zh" else "Decode the smoke-test flag.",
                }
            )
        )

    result = AgentLoop(
        challenge=challenge,
        challenge_dir=smoke_dir,
        llm=llm,
        executor=DockerExecutor(),
        language=language,
    ).run()

    if result.flag == SMOKE_FLAG:
        console.print(f"[green]{t(language, 'smoke_solved')}[/green] {result.flag}")
        return

    console.print(f"[red]{t(language, 'smoke_failed')}[/red] status={result.status}")
    if result.reason:
        console.print(result.reason)
    raise typer.Exit(code=1)


def _importable(package: str) -> bool:
    try:
        __import__(package)
        return True
    except Exception:
        return False


def _llm_key_status(deepseek_key_ok: bool, openai_key_ok: bool, language) -> str:
    if deepseek_key_ok and openai_key_ok:
        return t(language, "llm_key_both")
    if deepseek_key_ok:
        return t(language, "llm_key_deepseek")
    if openai_key_ok:
        return t(language, "llm_key_openai")
    return t(language, "llm_key_missing")


def _llm_key_status_from_provider_checks(statuses: list[dict], language) -> str:
    available = [
        f"{status['provider']} ({status['env']})"
        for status in statuses
        if status.get("ok")
    ]
    if not available:
        return t(language, "llm_key_missing")
    if language == "zh":
        return "可用：" + ", ".join(available)
    return "available: " + ", ".join(available)


def _print_plan(plan, language) -> None:
    console.rule(f"[bold cyan]{t(language, 'plan_rule')}")
    console.print(Markdown(plan.to_markdown(language)))
    console.rule(f"[bold cyan]{t(language, 'solving_rule')}")


def _print_event(event: str, payload: dict, language) -> None:
    if event == "run_started":
        console.print(f"[cyan]{t(language, 'run_started')}[/cyan]")
        return
    if event == "llm_wait":
        phase = phase_name(language, payload["phase"])
        console.print("[dim]" + t(language, "llm_wait", phase=phase) + "[/dim]")
        return
    if event == "command_start":
        phase = phase_name(language, payload["phase"])
        summary = _command_summary(payload.get("command", ""), payload.get("rationale", ""), language)
        console.print(
            f"[blue]{t(language, 'command_start_brief', phase=phase, summary=summary)}[/blue]"
        )
        return
    if event == "command_done":
        candidates = payload.get("candidate_count", 0)
        phase = phase_name(language, payload["phase"])
        if candidates:
            console.print(
                "[dim]"
                + t(language, "command_done_candidates", phase=phase, count=candidates)
                + "[/dim]"
            )
        elif payload["timed_out"]:
            console.print("[dim]" + t(language, "command_done_timeout", phase=phase) + "[/dim]")
        elif payload["exit_code"] != 0:
            console.print("[dim]" + t(language, "command_done_failed", phase=phase) + "[/dim]")
        return
    if event == "command_skipped":
        console.print(
            "[dim]"
            + t(language, "command_skipped", phase=phase_name(language, payload["phase"]))
            + "[/dim]"
        )
        return
    if event == "plan_ready":
        console.print(f"[cyan]{t(language, 'planning_complete')}[/cyan]")
        return
    if event == "flag_submitted":
        console.print(
            "[cyan]"
            + t(
                language,
                "flag_submitted",
                phase=phase_name(language, payload["phase"]),
            )
            + "[/cyan]"
        )


def _command_summary(command: str, rationale: str, language) -> str:
    if rationale.strip() and not _looks_command_like(rationale):
        return _brief_text(rationale)

    lowered = command.lower()
    if ("cat >" in lowered or "tee " in lowered) and any(
        token in lowered for token in ("python", "sage", "bash", "sh ")
    ):
        return t(language, "summary_write_and_run_script")
    if any(token in lowered for token in ("nc ", "ncat ", "curl ", "wget ", "socket", "requests", "http://", "https://")):
        return t(language, "summary_connect_remote")
    if any(token in lowered for token in ("factordb", "search_query", "google", "bing")):
        return t(language, "summary_check_external")
    if any(token in lowered for token in ("python", "sage", "solve.py", "exploit.py")):
        return t(language, "summary_run_script")
    if any(token in lowered for token in ("openssl", "hashcat", "john", "base64", "xxd", "sha", "aes", "rsa")):
        return t(language, "summary_decode_or_crypto")
    if any(token in lowered for token in ("gdb", "checksec", "readelf", "objdump", "rabin2", "ghidra", "angr")):
        return t(language, "summary_analyze_binary")
    if re.search(r"\b(ls|find|file|cat|sed|head|tail|strings|tree)\b", lowered):
        return t(language, "summary_inspect_files")
    return t(language, "summary_generic_command")


def _brief_text(text: str, max_chars: int = 90) -> str:
    collapsed = " ".join(text.strip().split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "..."


def _looks_command_like(text: str) -> bool:
    lowered = text.lower()
    if "\n" in text or "```" in text or "/work/" in lowered or "<<" in text:
        return True
    return bool(
        re.search(
            r"(^|\s|\$)(cat|python3?|sage|bash|sh|nc|ncat|curl|wget|gdb|checksec|readelf|objdump|strings|file|sed)\b",
            lowered,
        )
    )


def _message(language, *, en: str, zh: str) -> str:
    return zh if language == "zh" else en
