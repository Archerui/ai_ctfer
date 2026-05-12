from __future__ import annotations

from .config import Language


def display_language(language: Language, *, output_language: Language | None = None) -> str:
    output_language = output_language or language
    if output_language == "zh":
        return "中文" if language == "zh" else "英语"
    return "Chinese" if language == "zh" else "English"


def t(output_language: Language, key: str, **kwargs: object) -> str:
    messages = _MESSAGES[output_language]
    template = messages.get(key, _MESSAGES["en"].get(key, key))
    return template.format(**kwargs)


def phase_name(language: Language, phase: str) -> str:
    names = {
        "en": {"planning": "planning", "solve": "solve"},
        "zh": {"planning": "规划", "solve": "解题"},
    }
    return names[language].get(phase, phase)


def language_instruction(language: Language) -> str:
    if language == "zh":
        return (
            "语言规则：JSON 字段名、action 名、命令、文件路径、代码、协议字面量、"
            "flag 值和观察到的原始输出不要翻译。除此之外，你写出的所有自然语言"
            "内容必须使用简体中文，包括 rationale、summary、chosen_strategy、"
            "steps、alternatives 和 finish.rationale。"
        )
    return (
        "Language policy: keep JSON keys, action names, commands, file paths, "
        "code, protocol literals, flag values, and observed raw output exactly as "
        "they are. All other natural-language text you write must be English, "
        "including rationale, summary, chosen_strategy, steps, alternatives, and "
        "finish.rationale."
    )


def planning_mode_instruction(language: Language) -> str:
    if language == "zh":
        return (
            "规划模式：在执行最终解题策略前，先探索多个可能方向。你可以运行命令"
            "检查文件、识别服务、验证低成本假设、确认工具是否可用。除非已经找到"
            "高置信度 flag，否则不要在规划阶段只深挖单一路径；在 set_plan 前至少"
            "运行两个简短且信息量高的探索命令。规划最后必须用 set_plan action "
            "给出可行性最高的策略和具体下一步。set_plan 后系统会自动开始执行，"
            "不需要用户确认。"
        )
    return (
        "Planning mode: before executing the final solve strategy, explore several "
        "plausible angles. You may run commands to inspect files, identify services, "
        "test cheap hypotheses, and check tool availability. Do not spend the "
        "planning phase on one deep path unless it clearly dominates. Run at least "
        "two short exploratory commands before set_plan unless you have already "
        "found a high-confidence flag. End planning with a set_plan action that "
        "names the most feasible strategy and concrete next steps. After set_plan, "
        "execution starts automatically; the user will not confirm."
    )


def solve_user_intro(language: Language) -> str:
    if language == "zh":
        return "解决这个单题授权 CTF challenge。根据下面状态，严格只返回一个 JSON action。\n\n"
    return (
        "Solve this single authorized CTF challenge. Use the current state below "
        "and return exactly one JSON action.\n\n"
    )


def planning_user_intro(language: Language) -> str:
    if language == "zh":
        return (
            "为这个单题授权 CTF challenge 制定计划。你可以先运行探索命令，然后返回 "
            "set_plan。严格只返回一个 JSON action。\n\n"
        )
    return (
        "Plan this single authorized CTF challenge. You may run exploratory "
        "commands, then return set_plan. Return exactly one JSON action.\n\n"
    )


def planning_goal(language: Language) -> str:
    if language == "zh":
        return (
            "收集足够证据来比较多个解题方向，然后选择可行性最高的计划。规划阶段"
            "优先运行简短、信息量高的命令。先尝试多个角度，再做选择。"
        )
    return (
        "Gather enough evidence to compare multiple solution angles, then choose "
        "the highest-feasibility plan. Prefer short, information-rich commands "
        "during planning. Try multiple angles before choosing."
    )


def adjudicator_system(language: Language) -> str:
    if language == "zh":
        return (
            "你是单题 CTF challenge 的最终 flag 裁判。只能从给定候选里选择。优先选择"
            "来自目标输出、解密脚本、辅助脚本或明确成功标签的候选。拒绝示例、占位符、"
            "flag 格式描述、模型猜测、以及未经校验的解密结果。严格只返回一个 JSON action，"
            "不要输出解释性 prose。"
        )
    return (
        "You are the final flag adjudicator for a single CTF challenge. Choose "
        "only from the provided candidates. Prefer candidates that came from "
        "target output, decrypt scripts, helper scripts, or explicit success "
        "labels. Reject examples, placeholders, flag format descriptions, and "
        "guesses. Also reject unverified decrypt-script outputs unless they have "
        "round-trip, re-encryption, oracle, or sole-final-output evidence. Return "
        "exactly one JSON action and no prose."
    )


def adjudicator_instruction(language: Language) -> str:
    if language == "zh":
        return (
            "只有当某个候选有独立可验证证据时，才返回 submit_flag，并使用完全一致的值。"
            "如果候选只是模型提交或未经校验的解密输出，返回 status 为 give_up 的 finish。"
        )
    return (
        "Only return submit_flag with the exact value when a candidate has "
        "independent verifiable evidence. If candidates are model-only or "
        "unverified decrypt outputs, return finish with status give_up."
    )


def repair_system(language: Language) -> str:
    if language == "zh":
        return "你负责修复格式错误的 agent action。严格只返回一个有效 JSON object，不要输出 prose。"
    return "You repair malformed agent actions. Return exactly one valid JSON object and no prose."


def plan_markdown(
    language: Language,
    *,
    summary: str,
    chosen_strategy: str,
    steps: list[str],
    alternatives: list[str],
    rationale: str,
    fallback: bool,
) -> str:
    labels = _PLAN_LABELS[language]
    lines = [labels["title"], "", f"{labels['summary']} {summary}", ""]
    lines.extend([labels["chosen_strategy"], chosen_strategy, ""])
    if steps:
        lines.append(labels["steps"])
        lines.extend(f"{index}. {step}" for index, step in enumerate(steps, 1))
        lines.append("")
    if alternatives:
        lines.append(labels["alternatives"])
        lines.extend(f"- {alternative}" for alternative in alternatives)
        lines.append("")
    if rationale:
        lines.extend([labels["rationale"], rationale, ""])
    if fallback:
        lines.append(labels["fallback_note"])
    return "\n".join(lines).rstrip() + "\n"


_PLAN_LABELS = {
    "en": {
        "title": "# ai-ctfer plan",
        "summary": "Summary:",
        "chosen_strategy": "Chosen strategy:",
        "steps": "Steps:",
        "alternatives": "Alternatives considered:",
        "rationale": "Rationale:",
        "fallback_note": "Note: this fallback plan was synthesized after planning steps were exhausted.",
    },
    "zh": {
        "title": "# ai-ctfer 计划",
        "summary": "摘要：",
        "chosen_strategy": "选定策略：",
        "steps": "步骤：",
        "alternatives": "已考虑的其他方向：",
        "rationale": "理由：",
        "fallback_note": "说明：规划步骤耗尽后，系统自动综合了这个备用计划。",
    },
}


_MESSAGES = {
    "en": {
        "already_exists": "{path} already exists; use --force to overwrite.",
        "challenge_directory": "Challenge directory:",
        "command_done_candidates": "{phase}: found {count} flag candidate(s).",
        "command_done_failed": "{phase}: operation did not complete successfully; adjusting.",
        "command_done_timeout": "{phase}: operation timed out; adjusting.",
        "command_skipped": "{phase}: skipped a repeated command and will pivot.",
        "command_start_brief": "{phase}: {summary}",
        "config_path": "Config file:",
        "current_language": "Current language: {language}",
        "doctor_check": "Check",
        "doctor_importable": "importable",
        "doctor_missing": "missing",
        "doctor_no": "no",
        "doctor_not_checked": "not checked",
        "doctor_ok": "OK",
        "doctor_set": "set",
        "doctor_status": "Status",
        "doctor_title": "ai-ctfer doctor",
        "doctor_unavailable": "unavailable",
        "doctor_yes": "yes",
        "exit_status": "exit {code}",
        "finished_status": "Finished with status:",
        "flag_candidates": "Flag candidates:",
        "flag_submitted": "{phase}: submitting a candidate flag.",
        "language_set": "Language set to {language}.",
        "language_value_error": "Unsupported language. Use Chinese/中文 or English/英语.",
        "llm_wait": "{phase}: thinking about the next move...",
        "llm_key_both": "DeepSeek and OpenAI available",
        "llm_key_deepseek": "DeepSeek available",
        "llm_key_missing": "missing",
        "llm_key_openai": "OpenAI available",
        "run_started": "Planning started...",
        "plan_rule": "Plan",
        "planning": "Planning...",
        "planning_complete": "Planning complete.",
        "run_directory": "Run directory:",
        "solved": "Solved:",
        "solving_rule": "Solving",
        "smoke_failed": "Smoke failed:",
        "smoke_solved": "Smoke solved:",
        "summary_flag_candidates_heading": "Flag candidates",
        "summary_heading": "# ai-ctfer run summary",
        "summary_status": "Status:",
        "timeout": "timeout",
        "summary_analyze_binary": "analyzing binary artifacts",
        "summary_check_external": "checking external references",
        "summary_connect_remote": "probing a remote service",
        "summary_decode_or_crypto": "running crypto or decoding analysis",
        "summary_inspect_files": "inspecting challenge files",
        "summary_run_script": "running an analysis script",
        "summary_write_and_run_script": "writing and running a solve script",
        "summary_generic_command": "running a focused check",
        "wrote": "Wrote",
    },
    "zh": {
        "already_exists": "{path} 已存在；使用 --force 覆盖。",
        "challenge_directory": "题目目录：",
        "command_done_candidates": "{phase}中：发现 {count} 个 flag 候选。",
        "command_done_failed": "{phase}中：这次操作没有成功，继续调整。",
        "command_done_timeout": "{phase}中：这次操作超时，继续调整。",
        "command_skipped": "{phase}中：跳过重复命令，切换思路。",
        "command_start_brief": "{phase}中：{summary}",
        "config_path": "配置文件：",
        "current_language": "当前语言：{language}",
        "doctor_check": "检查项",
        "doctor_importable": "可导入",
        "doctor_missing": "缺失",
        "doctor_no": "否",
        "doctor_not_checked": "未检查",
        "doctor_ok": "通过",
        "doctor_set": "已设置",
        "doctor_status": "状态",
        "doctor_title": "ai-ctfer 检查",
        "doctor_unavailable": "不可用",
        "doctor_yes": "是",
        "exit_status": "退出码 {code}",
        "finished_status": "结束状态：",
        "flag_candidates": "Flag 候选：",
        "flag_submitted": "{phase}中：提交候选 flag。",
        "language_set": "语言已设置为{language}。",
        "language_value_error": "不支持的语言。请使用 Chinese/中文 或 English/英语。",
        "llm_wait": "{phase}中：思考下一步...",
        "llm_key_both": "DeepSeek 和 OpenAI 均可用",
        "llm_key_deepseek": "DeepSeek 可用",
        "llm_key_missing": "缺失",
        "llm_key_openai": "OpenAI 可用",
        "plan_rule": "计划",
        "planning": "正在规划...",
        "planning_complete": "规划完成。",
        "run_directory": "运行目录：",
        "run_started": "开始规划...",
        "solved": "已解出：",
        "solving_rule": "开始解题",
        "smoke_failed": "Smoke 测试失败：",
        "smoke_solved": "Smoke 测试已解出：",
        "summary_flag_candidates_heading": "Flag 候选",
        "summary_heading": "# ai-ctfer 运行摘要",
        "summary_status": "状态：",
        "timeout": "超时",
        "summary_analyze_binary": "分析二进制文件",
        "summary_check_external": "查询外部资料",
        "summary_connect_remote": "探测远程服务",
        "summary_decode_or_crypto": "运行密码或编码分析",
        "summary_inspect_files": "检查题目附件",
        "summary_run_script": "运行分析脚本",
        "summary_write_and_run_script": "编写并运行解题脚本",
        "summary_generic_command": "运行一次有针对性的检查",
        "wrote": "已写入",
    },
}
