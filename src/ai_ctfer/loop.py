from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from .actions import (
    FinishAction,
    RunCommandAction,
    SetPlanAction,
    SubmitFlagAction,
    parse_action,
    planning_action_schema_hint,
)
from .candidates import (
    FINAL_ACCEPT_CONFIDENCE,
    FlagCandidate,
    FlagCandidateStore,
    candidate_is_finalizable,
)
from .config import Language
from .environment import detect_environment_issue
from .executor import DockerExecutor
from .files import copy_challenge_files, render_file_tree
from .flag import matches_flag
from .i18n import plan_markdown, t
from .llm import LLMClient
from .logger import RunLogger
from .notebook import Notebook
from .prompt import (
    PromptBuilder,
    build_candidate_adjudication_messages,
    build_candidate_validation_messages,
    build_repair_messages,
)
from .schema import Challenge
from .validation import CandidateValidationResult, parse_candidate_validation

DEFAULT_PLANNING_STEPS = 50
MAX_EXACT_COMMAND_REPEATS = 2
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_VISIBLE_TEXT_RE = re.compile(r"[\w\u3400-\u9fff]", re.UNICODE)


@dataclass
class SolveResult:
    status: str
    run_dir: Path
    flag: str | None = None
    reason: str | None = None


@dataclass
class PlanResult:
    summary: str
    chosen_strategy: str
    steps: list[str]
    alternatives: list[str]
    rationale: str = ""
    fallback: bool = False

    def to_markdown(self, language: Language = "en") -> str:
        return plan_markdown(
            language,
            summary=self.summary,
            chosen_strategy=self.chosen_strategy,
            steps=self.steps,
            alternatives=self.alternatives,
            rationale=self.rationale,
            fallback=self.fallback,
        )


class AgentLoop:
    def __init__(
        self,
        *,
        challenge: Challenge,
        challenge_dir: Path,
        llm: LLMClient,
        executor: DockerExecutor,
        logger: RunLogger | None = None,
        planning_steps: int = DEFAULT_PLANNING_STEPS,
        on_plan: Callable[[PlanResult], None] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        language: Language = "en",
    ) -> None:
        self.challenge = challenge
        self.challenge_dir = challenge_dir.resolve()
        self.llm = llm
        self.executor = executor
        self.logger = logger or RunLogger.create(self.challenge_dir)
        self.prompt_builder = PromptBuilder()
        self.candidates = FlagCandidateStore(self.challenge.flag_regex, category=self.challenge.category)
        self.planning_steps = planning_steps
        self.on_plan = on_plan
        self.on_event = on_event
        self.language = language
        self.command_counts: dict[str, int] = {}
        self.repeated_command_skips = 0
        self.validated_candidate_revisions: set[tuple[str, int]] = set()
        self.notebook = Notebook.load(self.challenge_dir, self.challenge, self.language)
        self.environment_issue_reason: str | None = None

    def _emit(self, event: str, **payload: Any) -> None:
        if self.on_event:
            self.on_event(event, payload)

    def run(self) -> SolveResult:
        self.notebook.start_run(self.logger.run_dir.name)
        copy_challenge_files(self.challenge_dir, self.logger.work_dir)
        self._emit("run_started", run_dir=self.logger.run_dir, work_dir=self.logger.work_dir)
        self.logger.log(
            "run_started",
            challenge=self.challenge.as_prompt_dict(),
            source_dir=self.challenge_dir,
            work_dir=self.logger.work_dir,
        )

        history: list[dict[str, Any]] = []
        last_observation = _message(
            self.language,
            en="No commands have been run yet.",
            zh="尚未运行任何命令。",
        )
        planning_result, last_observation = self._run_planning_phase(
            history=history,
            last_observation=last_observation,
        )
        if self.environment_issue_reason:
            return self._environment_issue(self.environment_issue_reason)
        if planning_result:
            self.logger.write_plan(planning_result.to_markdown(self.language))
            self.logger.log("plan_set", plan=planning_result)
            self.notebook.record_plan(planning_result)
            if self.on_plan:
                self.on_plan(planning_result)
            history.append(
                {
                    "phase": "planning",
                    "action": "set_plan",
                    "summary": planning_result.summary,
                    "chosen_strategy": planning_result.chosen_strategy,
                    "steps": planning_result.steps,
                    "alternatives": planning_result.alternatives,
                }
            )

        if accepted := self.candidates.accepted_candidate():
            return self._candidate_success(
                accepted,
                _message(
                    self.language,
                    en="Accepted high-confidence flag candidate during planning.",
                    zh="规划阶段已接受高置信度 flag 候选。",
                ),
            )

        for step in range(1, self.challenge.limits.max_steps + 1):
            remaining_steps = self.challenge.limits.max_steps - step + 1
            self._emit("llm_wait", phase="solve", step=step, remaining_steps=remaining_steps)
            messages = self.prompt_builder.build_messages(
                challenge=self.challenge,
                file_tree=render_file_tree(self.logger.work_dir),
                history=history,
                last_observation=last_observation,
                remaining_steps=remaining_steps,
                flag_candidates=self.candidates.prompt_items(),
                notebook=self.notebook.prompt_text(),
                language=self.language,
            )
            response = self.llm.complete(
                messages,
                model=self.challenge.model.api_model,
                temperature=self.challenge.model.temperature,
                reasoning_effort=self.challenge.model.reasoning_effort,
            )
            self.logger.log("llm_response", step=step, response=response)

            try:
                action = parse_action(response)
            except (ValueError, ValidationError) as exc:
                repaired = self._repair_action(response, str(exc))
                if repaired is None:
                    reason = _message(
                        self.language,
                        en=f"Could not parse model action at step {step}: {exc}",
                        zh=f"第 {step} 步无法解析模型 action：{exc}",
                    )
                    self.logger.log("parse_failed", step=step, reason=reason)
                    self.logger.write_summary("error", reason, language=self.language)
                    self.notebook.record_finish("error", reason)
                    return SolveResult("error", self.logger.run_dir, reason=reason)
                action = repaired
            else:
                action = self._repair_language_if_needed(response, action)
                if action is None:
                    reason = _message(
                        self.language,
                        en=f"Model action at step {step} did not satisfy the configured language.",
                        zh=f"第 {step} 步的模型 action 不符合当前语言设置。",
                    )
                    self.logger.log("language_validation_failed", step=step, reason=reason)
                    self.logger.write_summary("error", reason, language=self.language)
                    self.notebook.record_finish("error", reason)
                    return SolveResult("error", self.logger.run_dir, reason=reason)

            if isinstance(action, RunCommandAction):
                if repeated := self._repeated_command_observation(action.command):
                    self.repeated_command_skips += 1
                    last_observation = repeated
                    history.append(
                        {
                            "step": step,
                            "action": "run_command_skipped",
                            "command": action.command,
                            "reason": "repeated_command",
                            "rationale": action.rationale,
                        }
                    )
                    self.logger.log(
                        "command_skipped",
                        step=step,
                        action=action.model_dump(),
                        reason="repeated_command",
                    )
                    self._emit("command_skipped", phase="solve", step=step)
                    continue
                self._record_command(action.command)
                self._emit(
                    "command_start",
                    phase="solve",
                    step=step,
                    command=action.command,
                    rationale=action.rationale,
                    timeout_sec=self.challenge.limits.command_timeout_sec,
                )
                result = self.executor.run(
                    action.command,
                    self.logger.work_dir,
                    self.challenge.remote,
                    self.challenge.limits.command_timeout_sec,
                    self.challenge.limits.max_output_chars,
                )
                observation = result.observation()
                last_observation = observation
                environment_issue = self._detect_environment_issue(result)
                candidates = self._collect_command_candidates(
                    step=step,
                    command=action.command,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
                history.append(
                    {
                        "step": step,
                        "action": "run_command",
                        "command": action.command,
                        "exit_code": result.exit_code,
                        "timed_out": result.timed_out,
                        "rationale": action.rationale,
                        "candidate_count": len(candidates),
                        "observation_excerpt": _observation_excerpt(observation),
                    }
                )
                self.logger.log(
                    "command_result",
                    step=step,
                    action=action.model_dump(),
                    result=result,
                    detected_flags=[candidate.value for candidate in candidates],
                    flag_candidates=[candidate.prompt_dict() for candidate in candidates],
                )
                self._emit(
                    "command_done",
                    phase="solve",
                    step=step,
                    command=action.command,
                    exit_code=result.exit_code,
                    timed_out=result.timed_out,
                    duration_sec=result.duration_sec,
                    candidate_count=len(candidates),
                )
                self.notebook.record_command(
                    phase="solve",
                    step=step,
                    command=action.command,
                    rationale=action.rationale,
                    result=result,
                    candidate_values=[candidate.value for candidate in candidates],
                    environment_issue=environment_issue,
                )
                if environment_issue:
                    return self._environment_issue(environment_issue)
                if candidates:
                    last_observation += "\n\n" + t(self.language, "flag_candidates") + "\n" + self._candidate_summary()
                if accepted := self.candidates.accepted_candidate():
                    return self._candidate_success(
                        accepted,
                        _message(
                            self.language,
                            en=f"Accepted high-confidence flag candidate after command at step {step}.",
                            zh=f"第 {step} 步命令后已接受高置信度 flag 候选。",
                        ),
                    )
                if validated := self._try_validate_candidates(
                    candidates=candidates,
                    history=history,
                    last_observation=last_observation,
                ):
                    return self._candidate_success(
                        validated,
                        _message(
                            self.language,
                            en=f"Validator accepted flag candidate after command at step {step}.",
                            zh=f"第 {step} 步命令后，候选校验 agent 已接受该 flag。",
                        ),
                    )
                continue

            if isinstance(action, SubmitFlagAction):
                self._emit("flag_submitted", phase="solve", step=step, flag=action.flag)
                self.logger.log("flag_submitted", step=step, action=action.model_dump())
                candidate = self.candidates.add(
                    action.flag,
                    source="submit_flag",
                    step=step,
                    context=action.rationale,
                )
                self.notebook.record_submit(step=step, flag=action.flag, rationale=action.rationale)
                if candidate and candidate.changed_in_last_update:
                    self.logger.log_candidate(candidate)
                    self.logger.log(
                        "flag_candidate",
                        step=step,
                        candidate=candidate,
                    )
                if candidate:
                    validation_history = history + [
                        {
                            "step": step,
                            "action": "submit_flag",
                            "candidate": candidate.prompt_dict(),
                            "rationale": action.rationale,
                        }
                    ]
                    if validated := self._try_validate_candidates(
                        candidates=[candidate],
                        history=validation_history,
                        last_observation=last_observation,
                        allow_submit_only=True,
                    ):
                        return self._candidate_success(
                            validated,
                            _message(
                                self.language,
                                en=f"Validator accepted model-submitted flag candidate at step {step}.",
                                zh=f"第 {step} 步，候选校验 agent 已接受模型提交的 flag。",
                            ),
                        )
                if candidate and candidate.status == "accepted" and candidate_is_finalizable(candidate):
                    return self._candidate_success(
                        candidate,
                        _message(
                            self.language,
                            en=f"Accepted model-submitted flag candidate at step {step}.",
                            zh=f"第 {step} 步已接受模型提交的 flag 候选。",
                        ),
                    )
                last_observation = (
                    _message(
                        self.language,
                        en=(
                            "The submitted flag has been recorded as a candidate, but it is "
                            "not accepted from model submission alone. Provide independent "
                            "evidence: target output, a verification script, re-encryption "
                            "check, oracle acceptance, or a sole final command output."
                        ),
                        zh=(
                            "提交的 flag 已记录为候选，但不能仅凭模型提交就接受。"
                            "请继续提供独立证据：目标输出、验证脚本、重新加密校验、"
                            "oracle 接受结果，或单独的最终命令输出。"
                        ),
                    )
                )
                history.append(
                    {
                        "step": step,
                        "action": "submit_flag",
                        "accepted": False,
                        "candidate": candidate.prompt_dict() if candidate else None,
                        "rationale": action.rationale,
                    }
                )
                continue

            if isinstance(action, SetPlanAction):
                plan = plan_from_action(action)
                self.logger.write_plan(plan.to_markdown(self.language))
                self.logger.log("plan_updated_during_solve", step=step, plan=plan)
                last_observation = (
                    _message(
                        self.language,
                        en=(
                            "Plan was updated during solve. Continue by executing the "
                            "highest-priority concrete step."
                        ),
                        zh="解题过程中计划已更新。继续执行优先级最高的具体步骤。",
                    )
                )
                history.append(
                    {
                        "step": step,
                        "action": "set_plan",
                        "summary": plan.summary,
                        "chosen_strategy": plan.chosen_strategy,
                    }
                )
                continue

            if isinstance(action, FinishAction):
                if resolution := self._try_resolve_candidates(
                    history=history,
                    last_observation=last_observation,
                    reason=_message(
                        self.language,
                        en=f"Model tried to finish with candidates available at step {step}.",
                        zh=f"第 {step} 步模型尝试结束，但当前仍有候选 flag 可判定。",
                    ),
                ):
                    return resolution
                reason = action.rationale or action.status
                self.logger.log("finished", step=step, action=action.model_dump())
                self.logger.write_summary(action.status, reason, language=self.language)
                self.notebook.record_finish(action.status, reason)
                return SolveResult(action.status, self.logger.run_dir, reason=reason)

        if resolution := self._try_resolve_candidates(
            history=history,
            last_observation=last_observation,
            reason=_message(
                self.language,
                en="Reached max steps with unresolved flag candidates.",
                zh="达到最大步数时仍有未确认的 flag 候选。",
            ),
        ):
            return resolution
        reason = _message(
            self.language,
            en=f"Reached max_steps={self.challenge.limits.max_steps} without a flag.",
            zh=f"达到 max_steps={self.challenge.limits.max_steps} 后仍未找到 flag。",
        )
        self.logger.log("max_steps_reached", reason=reason)
        self.logger.write_summary("max_steps", reason, language=self.language)
        self.notebook.record_finish("max_steps", reason)
        return SolveResult("max_steps", self.logger.run_dir, reason=reason)

    def _run_planning_phase(
        self,
        *,
        history: list[dict[str, Any]],
        last_observation: str,
    ) -> tuple[PlanResult | None, str]:
        if self.planning_steps <= 0:
            return None, last_observation

        planning_history: list[dict[str, Any]] = []
        for planning_step in range(1, self.planning_steps + 1):
            self._emit(
                "llm_wait",
                phase="planning",
                step=planning_step,
                remaining_steps=self.planning_steps - planning_step + 1,
            )
            messages = self.prompt_builder.build_planning_messages(
                challenge=self.challenge,
                file_tree=render_file_tree(self.logger.work_dir),
                history=planning_history,
                last_observation=last_observation,
                remaining_planning_steps=self.planning_steps - planning_step + 1,
                flag_candidates=self.candidates.prompt_items(),
                notebook=self.notebook.prompt_text(),
                language=self.language,
            )
            response = self.llm.complete(
                messages,
                model=self.challenge.model.api_model,
                temperature=self.challenge.model.temperature,
                reasoning_effort=self.challenge.model.reasoning_effort,
            )
            self.logger.log("planning_llm_response", planning_step=planning_step, response=response)
            try:
                action = parse_action(response)
            except (ValueError, ValidationError) as exc:
                repaired = self._repair_action(
                    response,
                    str(exc),
                    schema_hint=planning_action_schema_hint(),
                )
                if repaired is None:
                    self.logger.log(
                        "planning_parse_failed",
                        planning_step=planning_step,
                        error=str(exc),
                    )
                    continue
                action = repaired
            else:
                action = self._repair_language_if_needed(
                    response,
                    action,
                    schema_hint=planning_action_schema_hint(),
                )
                if action is None:
                    self.logger.log(
                        "planning_language_validation_failed",
                        planning_step=planning_step,
                    )
                    continue

            if isinstance(action, RunCommandAction):
                if repeated := self._repeated_command_observation(action.command):
                    self.repeated_command_skips += 1
                    last_observation = repeated
                    record = {
                        "phase": "planning",
                        "planning_step": planning_step,
                        "action": "run_command_skipped",
                        "command": action.command,
                        "reason": "repeated_command",
                        "rationale": action.rationale,
                    }
                    planning_history.append(record)
                    history.append(record)
                    self.logger.log(
                        "planning_command_skipped",
                        planning_step=planning_step,
                        action=action.model_dump(),
                        reason="repeated_command",
                    )
                    self._emit("command_skipped", phase="planning", step=planning_step)
                    if self.repeated_command_skips >= 3:
                        return self._fallback_plan(
                            planning_history,
                            _message(
                                self.language,
                                en="Planning stopped early because the model repeated the same command.",
                                zh="模型反复请求同一命令，规划阶段已提前收敛。",
                            ),
                        ), last_observation
                    continue
                self._record_command(action.command)
                self._emit(
                    "command_start",
                    phase="planning",
                    step=planning_step,
                    command=action.command,
                    rationale=action.rationale,
                    timeout_sec=self.challenge.limits.command_timeout_sec,
                )
                result = self.executor.run(
                    action.command,
                    self.logger.work_dir,
                    self.challenge.remote,
                    self.challenge.limits.command_timeout_sec,
                    self.challenge.limits.max_output_chars,
                )
                last_observation = result.observation()
                environment_issue = self._detect_environment_issue(result)
                candidates = self._collect_command_candidates(
                    step=-planning_step,
                    command=action.command,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
                record = {
                    "phase": "planning",
                    "planning_step": planning_step,
                    "action": "run_command",
                    "command": action.command,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "rationale": action.rationale,
                    "candidate_count": len(candidates),
                    "observation_excerpt": _observation_excerpt(last_observation),
                }
                planning_history.append(record)
                history.append(record)
                self.logger.log(
                    "planning_command_result",
                    planning_step=planning_step,
                    action=action.model_dump(),
                    result=result,
                    detected_flags=[candidate.value for candidate in candidates],
                    flag_candidates=[candidate.prompt_dict() for candidate in candidates],
                )
                self._emit(
                    "command_done",
                    phase="planning",
                    step=planning_step,
                    command=action.command,
                    exit_code=result.exit_code,
                    timed_out=result.timed_out,
                    duration_sec=result.duration_sec,
                    candidate_count=len(candidates),
                )
                self.notebook.record_command(
                    phase="planning",
                    step=planning_step,
                    command=action.command,
                    rationale=action.rationale,
                    result=result,
                    candidate_values=[candidate.value for candidate in candidates],
                    environment_issue=environment_issue,
                )
                if environment_issue:
                    self.environment_issue_reason = environment_issue
                    return None, last_observation
                if candidates:
                    last_observation += "\n\n" + t(self.language, "flag_candidates") + "\n" + self._candidate_summary()
                if self.candidates.accepted_candidate():
                    return (
                        self._planning_found_candidate_plan(),
                        last_observation,
                    )
                if self._try_validate_candidates(
                    candidates=candidates,
                    history=history,
                    last_observation=last_observation,
                ):
                    return (
                        self._planning_found_candidate_plan(),
                        last_observation,
                    )
                continue

            if isinstance(action, SetPlanAction):
                self._emit("plan_ready", phase="planning", step=planning_step)
                return plan_from_action(action), last_observation

            if isinstance(action, SubmitFlagAction):
                self._emit("flag_submitted", phase="planning", step=planning_step, flag=action.flag)
                candidate = self.candidates.add(
                    action.flag,
                    source="submit_flag",
                    step=-planning_step,
                    context=action.rationale,
                )
                self.notebook.record_submit(step=-planning_step, flag=action.flag, rationale=action.rationale)
                if candidate:
                    if candidate.changed_in_last_update:
                        self.logger.log_candidate(candidate)
                        self.logger.log(
                            "flag_candidate",
                            planning_step=planning_step,
                            candidate=candidate,
                        )
                    if candidate.status == "accepted" and candidate_is_finalizable(candidate):
                        return (
                            self._planning_submitted_candidate_plan(action.rationale),
                            last_observation,
                        )
                    if (
                        candidate.source == "submit_flag"
                        and candidate.seen_count >= 3
                        and not candidate_is_finalizable(candidate)
                    ):
                        return self._fallback_plan(
                            planning_history,
                            _message(
                                self.language,
                                en=(
                                    "Planning stopped early because the model repeatedly "
                                    "submitted an unsupported flag candidate."
                                ),
                                zh="模型反复提交缺少证据的 flag 候选，规划阶段已提前收敛。",
                            ),
                        ), last_observation
                planning_history.append(
                    {
                        "phase": "planning",
                        "planning_step": planning_step,
                        "action": "submit_flag",
                        "candidate": candidate.prompt_dict() if candidate else None,
                    }
                )
                continue

            if isinstance(action, FinishAction):
                return self._fallback_plan(planning_history, action.rationale), last_observation

        return self._fallback_plan(
            planning_history,
            _message(
                self.language,
                en="Planning step budget exhausted.",
                zh="规划步骤预算已耗尽。",
            ),
        ), last_observation

    def _fallback_plan(self, planning_history: list[dict[str, Any]], rationale: str) -> PlanResult:
        inspected = [item.get("command", "") for item in planning_history if item.get("command")]
        if self.language == "zh":
            alternatives = [
                "本地附件初步分析",
                "如果题目提供远程信息，则探测远程协议",
                "基于题目类别和元数据编写专项解题脚本",
            ]
        else:
            alternatives = [
                "Local artifact triage",
                "Remote protocol probing if a remote is declared",
                "Category-specific solve script based on challenge metadata",
            ]
        if self.challenge.category.value != "unknown":
            alternatives.insert(
                0,
                _message(
                    self.language,
                    en=f"{self.challenge.category.value} playbook",
                    zh=f"{self.challenge.category.value} 类题目 playbook",
                ),
            )
        if self.language == "zh":
            steps = [
                "使用规划历史里最强的线索，选择第一个具体解题路径。",
                "把重复的手工操作整理成 /work/solve.py 或 /work/exploit.py。",
                "将每个有希望的输出交给 flag 候选系统检查。",
                "同一假设连续两次失败后及时切换方向。",
            ]
            summary = "利用规划观察结果，从最有希望的类别专项路径开始。"
        else:
            steps = [
                "Use the strongest clue from planning history to choose the first concrete solve path.",
                "Turn repeated manual work into /work/solve.py or /work/exploit.py.",
                "Check every promising output against the flag candidate system.",
                "Pivot after two failed attempts on the same hypothesis.",
            ]
            summary = "Use planning observations to start the most promising category-specific path."
        if inspected:
            summary = _message(
                self.language,
                en=f"Planning inspected {len(inspected)} command result(s); start from the best-supported hypothesis.",
                zh=f"规划阶段已检查 {len(inspected)} 个命令结果；从证据最充分的假设开始。",
            )
        return PlanResult(
            summary=summary,
            chosen_strategy=_message(
                self.language,
                en="Proceed with evidence-driven solve loop using the current observations.",
                zh="基于当前观察结果，进入证据驱动的自动解题循环。",
            ),
            steps=steps,
            alternatives=alternatives,
            rationale=rationale,
            fallback=True,
        )

    def _record_command(self, command: str) -> None:
        fingerprint = _command_fingerprint(command)
        self.command_counts[fingerprint] = self.command_counts.get(fingerprint, 0) + 1

    def _repeated_command_observation(self, command: str) -> str | None:
        fingerprint = _command_fingerprint(command)
        count = self.command_counts.get(fingerprint, 0)
        if count < MAX_EXACT_COMMAND_REPEATS:
            return None
        return _message(
            self.language,
            en=(
                "This exact command has already been run twice. Do not repeat it; "
                "use the existing observations, inspect a different file/range, "
                "write a verifier, or pivot to another hypothesis."
            ),
            zh=(
                "这条完全相同的命令已经运行过两次。不要重复执行；请使用已有观察结果，"
                "改查不同文件或不同范围，编写验证脚本，或切换到其他假设。"
            ),
        )

    def _planning_found_candidate_plan(self) -> PlanResult:
        return PlanResult(
            summary=_message(
                self.language,
                en="Planning found a high-confidence flag candidate.",
                zh="规划阶段找到了高置信度 flag 候选。",
            ),
            chosen_strategy=_message(
                self.language,
                en="Accept the verified candidate and finish.",
                zh="接受已验证的候选并结束。",
            ),
            steps=[
                _message(
                    self.language,
                    en="Record the candidate as the final flag.",
                    zh="将该候选记录为最终 flag。",
                )
            ],
            alternatives=[
                _message(
                    self.language,
                    en="Continue deeper analysis if the candidate is later rejected.",
                    zh="如果候选后续被拒绝，再继续深入分析。",
                )
            ],
            rationale=_message(
                self.language,
                en="A command run during planning produced strong flag evidence.",
                zh="规划阶段运行的命令产生了强 flag 证据。",
            ),
        )

    def _planning_submitted_candidate_plan(self, rationale: str) -> PlanResult:
        return PlanResult(
            summary=_message(
                self.language,
                en="Planning received a high-confidence submitted flag candidate.",
                zh="规划阶段收到了高置信度提交型 flag 候选。",
            ),
            chosen_strategy=_message(
                self.language,
                en="Accept the submitted candidate and finish.",
                zh="接受提交的候选并结束。",
            ),
            steps=[
                _message(
                    self.language,
                    en="Record the candidate as the final flag.",
                    zh="将该候选记录为最终 flag。",
                )
            ],
            alternatives=[
                _message(
                    self.language,
                    en="Continue if the candidate is later rejected.",
                    zh="如果候选后续被拒绝，再继续分析。",
                )
            ],
            rationale=rationale,
        )

    def _repair_action(
        self,
        response: str,
        error: str,
        schema_hint: str | None = None,
    ) -> RunCommandAction | SubmitFlagAction | FinishAction | SetPlanAction | None:
        repair_response = self.llm.complete(
            build_repair_messages(
                response,
                error,
                schema_hint=schema_hint,
                language=self.language,
            ),
            model=self.challenge.model.api_model,
            reasoning_effort=self.challenge.model.reasoning_effort,
            temperature=0.0,
        )
        self.logger.log("repair_response", response=repair_response)
        try:
            action = parse_action(repair_response)
        except (ValueError, ValidationError):
            return None
        if language_error := self._action_language_error(action):
            self.logger.log(
                "repair_language_validation_failed",
                error=language_error,
                response=repair_response,
            )
            return None
        return action

    def _repair_language_if_needed(
        self,
        response: str,
        action: RunCommandAction | SubmitFlagAction | FinishAction | SetPlanAction,
        schema_hint: str | None = None,
    ) -> RunCommandAction | SubmitFlagAction | FinishAction | SetPlanAction | None:
        language_error = self._action_language_error(action)
        if not language_error:
            return action
        self.logger.log("language_validation_failed", error=language_error, response=response)
        return self._repair_action(response, language_error, schema_hint=schema_hint)

    def _action_language_error(
        self,
        action: RunCommandAction | SubmitFlagAction | FinishAction | SetPlanAction,
    ) -> str | None:
        fields = _natural_language_fields(action)
        if not fields:
            return None
        if self.language == "en":
            if any(_CJK_RE.search(field) for field in fields):
                return (
                    "Language mismatch: every natural-language field must be English. "
                    "Keep commands, code, paths, and flag values unchanged."
                )
            return None

        offenders: list[str] = []
        for field in fields:
            if _CJK_RE.search(field):
                continue
            if _VISIBLE_TEXT_RE.search(field):
                offenders.append(field)
        if offenders:
            return (
                "语言不一致：所有自然语言字段必须使用简体中文。"
                "命令、代码、路径和 flag 值保持原样。"
            )
        return None

    def _collect_command_candidates(
        self,
        *,
        step: int,
        command: str,
        stdout: str,
        stderr: str,
    ) -> list[FlagCandidate]:
        candidates: list[FlagCandidate] = []
        candidates.extend(
            self.candidates.add_from_text(
                stdout,
                source="stdout",
                step=step,
                command=command,
            )
        )
        candidates.extend(
            self.candidates.add_from_text(
                stderr,
                source="stderr",
                step=step,
                command=command,
            )
        )
        seen: set[str] = set()
        unique: list[FlagCandidate] = []
        for candidate in candidates:
            if candidate.normalized_value in seen:
                continue
            seen.add(candidate.normalized_value)
            unique.append(candidate)
            self.logger.log_candidate(candidate)
            self.logger.log("flag_candidate", step=step, candidate=candidate)
        return unique

    def _candidate_summary(self) -> str:
        lines = []
        for candidate in self.candidates.visible():
            lines.append(
                "- "
                f"{candidate.value} "
                f"(confidence={candidate.confidence}, status={candidate.status}, "
                f"source={candidate.source}, seen={candidate.seen_count})"
            )
        return "\n".join(lines)

    def _try_validate_candidates(
        self,
        *,
        candidates: list[FlagCandidate],
        history: list[dict[str, Any]],
        last_observation: str,
        allow_submit_only: bool = False,
    ) -> FlagCandidate | None:
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                candidate.confidence,
                candidate.seen_count,
                candidate.first_seen_step,
            ),
            reverse=True,
        )
        for candidate in ordered:
            revision_key = (candidate.normalized_value, candidate.revision)
            if revision_key in self.validated_candidate_revisions:
                continue
            if not allow_submit_only and not any(source != "submit_flag" for source in candidate.sources):
                continue
            self.validated_candidate_revisions.add(revision_key)
            validation = self._validate_candidate(
                candidate=candidate,
                history=history,
                last_observation=last_observation,
            )
            if validation is None:
                continue
            if validation.verdict == "trusted" and validation.confidence >= 75:
                accepted = self.candidates.mark_accepted(
                    candidate.value,
                    _message(
                        self.language,
                        en=f"accepted by candidate validator: {validation.rationale}",
                        zh=f"由候选校验 agent 接受：{validation.rationale}",
                    ),
                )
                if accepted:
                    self.logger.log_candidate(accepted, event="candidate_validated")
                    return accepted
            if validation.verdict == "decoy" and validation.confidence >= 85:
                rejected = self.candidates.mark_rejected(
                    candidate.value,
                    _message(
                        self.language,
                        en=f"rejected by candidate validator: {validation.rationale}",
                        zh=f"由候选校验 agent 拒绝：{validation.rationale}",
                    ),
                )
                if rejected:
                    self.logger.log_candidate(rejected, event="candidate_rejected")
        return None

    def _validate_candidate(
        self,
        *,
        candidate: FlagCandidate,
        history: list[dict[str, Any]],
        last_observation: str,
    ) -> CandidateValidationResult | None:
        response = self.llm.complete(
            build_candidate_validation_messages(
                challenge=self.challenge,
                candidate=candidate.prompt_dict(),
                candidates=self.candidates.prompt_items(),
                history=history,
                last_observation=last_observation,
                language=self.language,
            ),
            model=self.challenge.model.api_model,
            reasoning_effort=self.challenge.model.reasoning_effort,
            temperature=0.0,
        )
        self.logger.log(
            "candidate_validation_response",
            candidate=candidate.prompt_dict(),
            response=response,
        )
        try:
            validation = parse_candidate_validation(response)
        except (ValueError, ValidationError) as exc:
            self.logger.log(
                "candidate_validation_failed",
                candidate=candidate.prompt_dict(),
                error=str(exc),
            )
            return None
        self.logger.log(
            "candidate_validation_result",
            candidate=candidate.prompt_dict(),
            validation=validation.model_dump(),
        )
        self.notebook.record_candidate_validation(
            flag=candidate.value,
            verdict=validation.verdict,
            confidence=validation.confidence,
            rationale=validation.rationale,
        )
        return validation

    def _try_resolve_candidates(
        self,
        *,
        history: list[dict[str, Any]],
        last_observation: str,
        reason: str,
    ) -> SolveResult | None:
        if accepted := self.candidates.accepted_candidate():
            return self._candidate_success(accepted, reason)

        best = self.candidates.best_candidate()
        if not best:
            return None

        ordered = sorted(
            self.candidates.visible(),
            key=lambda candidate: candidate.confidence,
            reverse=True,
        )
        second_score = ordered[1].confidence if len(ordered) > 1 else -1
        if (
            best.confidence >= FINAL_ACCEPT_CONFIDENCE
            and best.confidence - second_score >= 10
            and candidate_is_finalizable(best)
        ):
            self.candidates.mark_accepted(
                best.value,
                _message(
                    self.language,
                    en="accepted as strongest candidate at final resolution",
                    zh="在最终判定中作为最强候选被接受",
                ),
            )
            self.logger.log_candidate(best, event="candidate_accepted")
            return self._candidate_success(best, reason)

        response = self.llm.complete(
            build_candidate_adjudication_messages(
                challenge=self.challenge,
                candidates=self.candidates.prompt_items(),
                history=history,
                last_observation=last_observation,
                language=self.language,
            ),
            model=self.challenge.model.api_model,
            reasoning_effort=self.challenge.model.reasoning_effort,
            temperature=0.0,
        )
        self.logger.log("candidate_adjudication_response", response=response)
        try:
            action = parse_action(response)
        except (ValueError, ValidationError) as exc:
            self.logger.log("candidate_adjudication_failed", error=str(exc))
            return None
        action = self._repair_language_if_needed(response, action)
        if action is None:
            self.logger.log("candidate_adjudication_language_failed")
            return None

        if isinstance(action, SubmitFlagAction):
            normalized = action.flag.strip().strip("`'\"")
            if (
                self.candidates.has_candidate(normalized)
                and matches_flag(normalized, self.challenge.flag_regex)
            ):
                target = next(
                    (
                        item
                        for item in self.candidates.visible()
                        if item.normalized_value == normalized
                    ),
                    None,
                )
                if target is None or not candidate_is_finalizable(target):
                    self.logger.log(
                        "candidate_adjudication_rejected",
                        submitted=action.flag,
                        reason=_message(
                            self.language,
                            en="candidate lacks independent finalizable evidence",
                            zh="候选缺少可最终确认的独立证据",
                        ),
                    )
                    return None
                candidate = self.candidates.mark_accepted(
                    normalized,
                    _message(
                        self.language,
                        en="accepted by final candidate adjudication",
                        zh="由最终候选裁判接受",
                    ),
                )
                if candidate:
                    self.logger.log_candidate(candidate, event="candidate_accepted")
                    return self._candidate_success(candidate, reason)
            self.logger.log(
                "candidate_adjudication_rejected",
                submitted=action.flag,
                reason=_message(
                    self.language,
                    en="adjudicator submitted a value outside the candidate set or invalid pattern",
                    zh="裁判提交了候选集合之外的值，或该值不符合 flag 模式",
                ),
            )
        return None

    def _candidate_success(self, candidate: FlagCandidate, details: str) -> SolveResult:
        self.logger.log_candidate(candidate, event="candidate_accepted")
        return self._success(candidate.value, details)

    def _detect_environment_issue(self, result: Any) -> str | None:
        issue = detect_environment_issue(result, self.challenge)
        if issue is None:
            return None
        target_text = f" ({issue.target})" if issue.target else ""
        return _message(
            self.language,
            en=(
                f"Possible challenge environment problem{target_text}: {issue.reason}. "
                "Check or restart the remote environment, update challenge.yml with the "
                "new address if it changed, then run solve again. Notebook targets from "
                "older runs are not authoritative."
            ),
            zh=(
                f"题目环境可能异常{target_text}：{issue.reason}。请检查或重启远程环境；"
                "如果地址变化，请先更新 challenge.yml 后再重新运行 solve。旧笔记里的"
                "历史地址不会作为当前目标。"
            ),
        )

    def _environment_issue(self, reason: str) -> SolveResult:
        self.logger.log("environment_issue", reason=reason)
        self.logger.write_summary("environment_error", reason, language=self.language)
        self.notebook.record_finish("environment_error", reason)
        return SolveResult("environment_error", self.logger.run_dir, reason=reason)

    def _success(self, flag: str, details: str) -> SolveResult:
        self.logger.write_final_flag(flag)
        candidate_text = ""
        if self.candidates.visible():
            rendered = "\n".join(
                f"- `{candidate.value}` confidence={candidate.confidence} "
                f"status={candidate.status} source={candidate.source} "
                f"seen={candidate.seen_count}"
                for candidate in self.candidates.visible()
            )
            candidate_text = f"\n\n## {t(self.language, 'summary_flag_candidates_heading')}\n\n{rendered}"
        self.logger.write_summary(
            "success",
            f"{details}\n\nFlag: `{flag}`{candidate_text}",
            language=self.language,
        )
        self.logger.log("success", flag=flag, details=details)
        self.notebook.record_finish("success", f"{details}\nFlag: {flag}")
        return SolveResult("success", self.logger.run_dir, flag=flag, reason=details)


def plan_from_action(action: SetPlanAction) -> PlanResult:
    return PlanResult(
        summary=action.summary,
        chosen_strategy=action.chosen_strategy,
        steps=action.steps,
        alternatives=action.alternatives,
        rationale=action.rationale,
    )


def _natural_language_fields(
    action: RunCommandAction | SubmitFlagAction | FinishAction | SetPlanAction,
) -> list[str]:
    fields: list[str] = []
    if isinstance(action, SetPlanAction):
        fields.extend([action.summary, action.chosen_strategy, action.rationale])
        fields.extend(action.steps)
        fields.extend(action.alternatives)
    elif isinstance(action, (RunCommandAction, SubmitFlagAction, FinishAction)):
        fields.append(action.rationale)
    return [field.strip() for field in fields if field and field.strip()]


def _message(language: Language, *, en: str, zh: str) -> str:
    return zh if language == "zh" else en


def _observation_excerpt(observation: str, max_chars: int = 1600) -> str:
    observation = observation.strip()
    if len(observation) <= max_chars:
        return observation
    head = observation[: max_chars // 2].rstrip()
    tail = observation[-max_chars // 2 :].lstrip()
    return f"{head}\n...[truncated]...\n{tail}"


def _command_fingerprint(command: str) -> str:
    return " ".join(command.split())
