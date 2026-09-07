#!/usr/bin/env python3
"""Validate Spec Harness artifacts without running project commands.

This is the only checker implementation. check_spec.ps1 only launches it.
It checks document structure and mappings, not independence or test truth.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


AC_PATTERN = re.compile(
    r"^[ \t]*[-*+][ \t]+\[[ xX]\][ \t]+\*\*(AC-\d+)\*\*[ \t]+"
    r"\[风险：[ \t]*(低|中|高)\][ \t]+"
    r"\[证据类型：[ \t]*(自动化|可复现命令|浏览器|人工)\][ \t]+\S[^\n]*$",
    re.MULTILINE,
)
TASK_PATTERN = re.compile(
    r"^[ \t]*[-*+][ \t]+\[([ xX])\][ \t]+\*\*(T-\d+)\*\*[ \t]+"
    r"\[(required|optional)\][ \t]+\S.*?[ \t]+→[ \t]*(.*)$"
)
DECLARATION_PATTERN = re.compile(
    r"^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?(?:\[[^\]]*\][ \t]*)?(?:\*\*)?(AC|T)-"
)
KR_PATTERN = re.compile(r"^-\s*(KR-\d+)\s*\[([^]]+)\]\s*→\s*(.+)$", re.MULTILINE)
ARTIFACT_PATTERN = re.compile(r"(?:文件|file)\s*[:：]\s*([^\s#；;|]+)", re.IGNORECASE)
PLACEHOLDER_VALUES = {"", "无", "不适用", "n/a", "na", "待确认", "待填写", "未填写"}
GENERIC_EVIDENCE = PLACEHOLDER_VALUES | {"正常", "通过", "已验证", "pass", "-", "…"}
COMPLETED_REVIEW_STATUSES = {"自审通过", "对抗自审通过", "独立复查通过", "fresh review", "人工复查"}
INDEPENDENT_ACTORS = ("新 agent", "不同模型", "人工")
DEPENDENT_MARKERS = ("同一 agent", "当前 agent", "非人工", "自审", "未独立", "新上下文")
RISK_SURFACES = {
    "数据写入/删除": ("数据写入/删除", "数据写入", "数据删除"),
    "权限/敏感数据": ("权限/敏感数据", "权限敏感", "敏感数据", "权限"),
    "外部副作用": ("外部副作用",),
    "不可逆": ("不可逆",),
    "生产或批量": ("生产或批量", "生产", "批量"),
}
ELEVATE_SURFACES = ("权限/敏感数据", "外部副作用", "不可逆", "生产或批量")
SINGLE_VALUE_FIELDS = {
    "流程档位", "Spec 版本", "原始需求", "审核状态", "实施授权", "作者确认",
    "审核的 Spec", "审核者", "审核来源", "输入范围", "独立性声明",
    "审核方式", "审核范围", "审核结论", "结论", "状态", "实际执行",
} | set(RISK_SURFACES)


def read(path: Path, errors: list[str]) -> str:
    if not path.is_file():
        errors.append(f"缺少文件：{path}")
        return ""
    return path.read_text(encoding="utf-8")


def record_text(text: str, errors: list[str]) -> str:
    """Exclude fenced examples while preserving record line numbers."""
    lines: list[str] = []
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^[ \t]*(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = ""
            lines.append("")
        elif marker:
            fence = marker[1]
            lines.append("")
        else:
            lines.append(line)
    if fence:
        errors.append("文档存在未闭合代码块，不能确认其后的记录是否完整")
    records = "\n".join(lines)
    seen: set[str] = set()
    for label in re.findall(r"^[>-][ \t]*([^：\n]+)：", records, re.MULTILINE):
        if label not in SINGLE_VALUE_FIELDS:
            continue
        if label in seen:
            errors.append(f"单值字段重复：{label}；更新原字段，历史变化写入说明")
        seen.add(label)
    return records


def value_after(text: str, label: str) -> str | None:
    match = re.search(rf"^[>-][ \t]*{re.escape(label)}：[ \t]*(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def unresolved(value: str | None) -> bool:
    return not value or "{{" in value or value.strip().lower() in PLACEHOLDER_VALUES


def mentions_version(text: str | None, version: str) -> bool:
    if not text or not version:
        return False
    return re.search(rf"(?<![\w.]){re.escape(version)}(?![\w.])", text) is not None


def process_tier(spec: str) -> str | None:
    raw = value_after(spec, "流程档位")
    if raw is None:
        return None
    tier = raw.split("（", 1)[0].strip()
    if tier in {"Spec", "Standard", "Strict"}:
        return tier
    return None


def elevated_risk(spec: str, surfaces: dict[str, str] | None = None) -> bool:
    if process_tier(spec) == "Strict":
        return True
    values = surfaces if surfaces is not None else parse_risk_surfaces(spec, [])
    return any(values.get(surface) == "是" for surface in ELEVATE_SURFACES)


def claims_independent_review(status: str | None, elevated: bool) -> bool:
    if elevated:
        return True
    text = status or ""
    if "未独立" in text:
        return False
    return bool(re.match(r"^\s*(fresh review\b|人工复查|独立复查)", text, re.IGNORECASE))


def conclusion_ok(value: str | None) -> bool:
    return (value or "").strip() == "通过"


def independent_actor(value: str | None) -> bool:
    normalized = (value or "").lower()
    if not normalized or any(marker in normalized for marker in DEPENDENT_MARKERS):
        return False
    return any(actor in normalized for actor in INDEPENDENT_ACTORS)


def validate_review(directory: Path, spec: str, elevated: bool, errors: list[str]) -> None:
    review = record_text(read(directory / "session" / "independent-review.md", errors), errors)
    if not review.strip():
        errors.append("独立审核文件为空或缺失")
        return
    version = value_after(spec, "Spec 版本") or ""
    for label in ("审核的 Spec", "审核者", "审核来源", "输入范围", "独立性声明"):
        if unresolved(value_after(review, label)):
            errors.append(f"独立审核文件未填写：{label}")
    if version and not mentions_version(value_after(review, "审核的 Spec"), version):
        errors.append(f"独立审核文件版本不匹配：需要 {version}")
    if not independent_actor(value_after(review, "审核者")):
        errors.append("独立审核文件的审核者不具备独立性")
    if "未读取起草过程" not in (value_after(review, "独立性声明") or ""):
        errors.append("独立审核文件缺少未读取起草过程的声明")
    if not conclusion_ok(value_after(review, "结论")):
        errors.append("独立审核文件没有有效的通过结论")


def validate_adversarial_review(directory: Path, spec: str, errors: list[str]) -> None:
    path = directory / "session" / "adversarial-review.md"
    if not path.is_file():
        return
    review = record_text(read(path, errors), errors)
    if not review.strip():
        errors.append("对抗自审文件为空")
        return
    version = value_after(spec, "Spec 版本") or ""
    for label in ("审核的 Spec", "审核方式", "输入范围", "结论"):
        if unresolved(value_after(review, label)):
            errors.append(f"对抗自审未填写：{label}")
    if version and not mentions_version(value_after(review, "审核的 Spec"), version):
        errors.append(f"对抗自审版本不匹配：需要 {version}")
    if "反方视角" not in (value_after(review, "审核方式") or ""):
        errors.append("对抗自审必须声明反方视角")
    if not conclusion_ok(value_after(review, "结论")):
        errors.append("对抗自审没有有效的通过结论")


def parse_risk_surfaces(spec: str, errors: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for surface in RISK_SURFACES:
        match = re.search(rf"^-\s*{re.escape(surface)}：\s*(.+)$", spec, re.MULTILINE)
        if not match:
            errors.append(f"变更面未裁定：{surface}")
            continue
        value = match.group(1).strip()
        if value not in {"是", "否"}:
            errors.append(f"变更面必须写成是或否：{surface}")
            continue
        values[surface] = value
    return values


def validate_risk_mapping(
    spec: str, acs: list[tuple[str, str, str]], surfaces: dict[str, str], errors: list[str]
) -> None:
    high_risk_ids = {ac_id for ac_id, risk, _ in acs if risk == "高"}
    mappings = [
        (kind.strip(), set(re.findall(r"AC-\d+", linked)))
        for _, kind, linked in KR_PATTERN.findall(spec)
        if kind.strip() in {alias for aliases in RISK_SURFACES.values() for alias in aliases}
    ]
    for surface, aliases in RISK_SURFACES.items():
        if surfaces.get(surface) != "是":
            continue
        mapped = set().union(*(ids for kind, ids in mappings if kind in aliases)) if mappings else set()
        if not mapped:
            errors.append(f"高风险变更面缺少关键风险映射：{surface}")
        elif not mapped.issubset(high_risk_ids):
            errors.append(f"关键风险映射必须指向高风险 AC：{surface}")


def validate_draft(directory: Path, spec: str, errors: list[str]) -> list[tuple[str, str, str]]:
    for label in ("Spec 版本", "原始需求", "审核状态"):
        if unresolved(value_after(spec, label)):
            errors.append(f"Spec 元数据未填写：{label}")
    if process_tier(spec) is None:
        errors.append("流程档位必须写成 Spec")

    acs: list[tuple[str, str, str]] = []
    for number, line in enumerate(spec.splitlines(), 1):
        declaration = DECLARATION_PATTERN.match(line)
        has_ac_fields = re.match(r"^[ \t]*[-*+][ \t]+\[[^\]]*\].*\[(?:风险|证据类型)：", line)
        if not (declaration and declaration[1] == "AC") and not has_ac_fields:
            continue
        match = AC_PATTERN.fullmatch(line)
        if not match or "{{" in line:
            errors.append(f"AC 记录格式不完整或非法（第 {number} 行）：{line.strip()}")
        else:
            acs.append(match.groups())
    ids = [ac_id for ac_id, _, _ in acs]
    if not ids:
        errors.append("未找到带风险和证据类型的 AC")
    if len(ids) != len(set(ids)):
        errors.append("AC 编号重复")
    surfaces = parse_risk_surfaces(spec, errors)
    validate_risk_mapping(spec, acs, surfaces, errors)
    validate_adversarial_review(directory, spec, errors)

    elevated = elevated_risk(spec, surfaces)
    if claims_independent_review(value_after(spec, "审核状态"), elevated):
        validate_review(directory, spec, elevated, errors)
    return acs


def report_outcomes(directory: Path, report: str, errors: list[str]) -> dict[str, tuple[str, str, str]]:
    outcomes: dict[str, tuple[str, str, str]] = {}
    for line in report.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not re.fullmatch(r"AC-\d+", cells[0]):
            continue
        ac_id, result, evidence_type, evidence = cells[:4]
        if result not in {"pass", "fail", "partial", "skipped"}:
            errors.append(f"AC 结果非法：{ac_id} = {result}")
            continue
        if evidence_type not in {"自动化", "可复现命令", "浏览器", "人工"}:
            errors.append(f"AC 证据类型非法：{ac_id} = {evidence_type}")
        if ac_id in outcomes:
            errors.append(f"检查报告中的 AC 重复：{ac_id}")
            continue
        summary = ARTIFACT_PATTERN.sub("", evidence).strip(" ；;，,")
        if summary.lower() in GENERIC_EVIDENCE or "{{" in evidence:
            errors.append(f"AC 证据为空或过于泛化：{ac_id}")
        artifact = ARTIFACT_PATTERN.search(evidence)
        if not artifact:
            errors.append(f"AC 证据缺少文件引用：{ac_id}")
        else:
            artifact_path = (directory / artifact.group(1)).resolve()
            try:
                artifact_path.relative_to(directory.resolve())
            except ValueError:
                errors.append(f"AC 证据文件超出任务目录：{ac_id}")
            else:
                if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
                    errors.append(f"AC 证据文件不存在或为空：{ac_id}")
        outcomes[ac_id] = (result, evidence_type, evidence)
    return outcomes


def validate_confirmation(spec: str, errors: list[str]) -> None:
    authorization = value_after(spec, "实施授权")
    if authorization is not None:
        if unresolved(authorization) or authorization.startswith(("待", "未授权")):
            errors.append("实施授权未填写或仍待确认")
        return
    # Older artifacts explicitly confirm a Spec version; preserve that contract.
    version = value_after(spec, "Spec 版本") or ""
    confirmation = value_after(spec, "作者确认")
    if unresolved(confirmation):
        errors.append("作者确认未填写")
    elif not mentions_version(confirmation, version):
        errors.append(f"作者确认未关联当前 Spec 版本：需要 {version}")


def validate_delivery_review(directory: Path, spec: str, errors: list[str]) -> None:
    path = directory / "check_reports" / "delivery-review.md"
    if not path.is_file():
        return
    review = record_text(read(path, errors), errors)
    if not review.strip():
        errors.append("交付审核文件为空")
        return
    for label in ("审核的 Spec", "审核者", "审核范围", "审核来源", "审核结论"):
        if unresolved(value_after(review, label)):
            errors.append(f"交付审核未填写：{label}")
    version = value_after(spec, "Spec 版本") or ""
    if version and not mentions_version(value_after(review, "审核的 Spec"), version):
        errors.append(f"交付审核版本不匹配：需要 {version}")
    if not conclusion_ok(value_after(review, "审核结论")):
        errors.append("交付审核未通过")


def require_nonempty(directory: Path, relative: str, errors: list[str]) -> None:
    path = directory.joinpath(*relative.split("/"))
    text = read(path, errors)
    if path.is_file() and not text.strip():
        errors.append(f"文件为空：{relative}")


def validate_strict_session_log(directory: Path, errors: list[str]) -> None:
    text = record_text(read(directory / "session" / "log.md", errors), errors)
    if not text.strip():
        errors.append("外部授权记录为空或缺失")
        return

    state = value_after(text, "实际执行")
    if state is not None and state not in {"有", "无"}:
        errors.append("实际执行必须明确填写有或无")
    # Legacy standalone declarations remain valid; mentions in prose do not.
    no_execution = state == "无" or any(
        re.fullmatch(r"无外部副作用(?:[：:].*)?", line.strip()) for line in text.splitlines()
    )
    operations: list[list[str]] = []
    in_operations = False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if re.match(r"^#{1,6}\s", line):
                in_operations = False
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == "操作":
            in_operations = len(cells) == 5 and cells[3] == "用户确认原话"
            if not in_operations:
                errors.append("外部授权表头应包含操作、范围、预览、用户确认原话和失效条件五列")
            continue
        if not in_operations or all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if len(cells) != 5:
            errors.append("外部授权操作记录必须包含五列")
            continue
        if cells[0] == "无":
            no_execution = True
            if any(cells[1:4]):
                errors.append("未执行操作的记录不能同时填写目标、预览或授权")
            continue
        operations.append(cells)

    if no_execution and (operations or state == "有"):
        errors.append("未执行声明与实际操作记录矛盾；执行操作时移除无操作声明或占位行")
    if not no_execution and not operations:
        errors.append("外部授权记录必须明确未执行，或逐项填写实际操作")
    for index, cells in enumerate(operations, 1):
        for label, value in zip(("操作", "范围", "预览", "用户确认原话", "失效条件"), cells):
            if unresolved(value) or value.startswith(("待", "未授权")):
                errors.append(f"外部操作第 {index} 项缺少有效的{label}")


def validate_delivery(directory: Path, spec: str, acs: list[tuple[str, str, str]], errors: list[str]) -> None:
    status = value_after(spec, "审核状态") or ""
    if status.lower() not in COMPLETED_REVIEW_STATUSES:
        errors.append("审核状态未明确通过；待澄清、阻塞或仅描述审核独立性不能交付")
    validate_confirmation(spec, errors)
    validate_delivery_review(directory, spec, errors)
    if elevated_risk(spec):
        require_nonempty(directory, "plan.md", errors)
        validate_strict_session_log(directory, errors)

    tasks = record_text(read(directory / "tasks.md", errors), errors)
    report = record_text(read(directory / "check_reports" / "harness-check.md", errors), errors)
    for name, content in (("tasks.md", tasks), ("check_reports/harness-check.md", report)):
        if not content.strip():
            errors.append(f"文件为空或没有代码块之外的有效记录：{name}")
    if not tasks.strip() or not report.strip():
        return

    required_ac_ids: set[str] = set()
    current_ac_ids = {ac_id for ac_id, _, _ in acs}
    task_ids: set[str] = set()
    for number, line in enumerate(tasks.splitlines(), 1):
        declaration = DECLARATION_PATTERN.match(line)
        has_task_kind = re.match(r"^[ \t]*[-*+][ \t]+\[[^\]]*\].*\[(?:required|optional)\]", line)
        if not (declaration and declaration[1] == "T") and not has_task_kind:
            continue
        match = TASK_PATTERN.fullmatch(line)
        if not match or "{{" in line:
            errors.append(f"任务记录格式不完整或非法（第 {number} 行）：{line.strip()}")
            continue
        checked, task_id, kind, linked = match.groups()
        linked = linked.strip()
        if task_id in task_ids:
            errors.append(f"任务编号重复：{task_id}")
        task_ids.add(task_id)
        if kind == "required" and checked.lower() != "x":
            errors.append(f"必需任务未完成：{line.strip()}")
        if not re.fullmatch(r"AC-\d+(?:[ \t]*[,，][ \t]*AC-\d+)*", linked) and not (kind == "optional" and linked == "无"):
            errors.append(f"任务 AC 映射缺失或非法：{task_id}")
            continue
        linked_ids = set(re.findall(r"AC-\d+", linked))
        if linked_ids - current_ac_ids:
            errors.append(f"任务引用不存在的当前 AC：{task_id}")
        if kind == "required":
            required_ac_ids.update(linked_ids)
        elif current_ac_ids.intersection(linked_ids):
            errors.append(f"optional 任务不得引用当前 AC：{line.strip()}")
    for ac_id, _, _ in acs:
        if ac_id not in required_ac_ids:
            errors.append(f"AC 未映射到 required 任务：{ac_id}")

    outcomes = report_outcomes(directory, report, errors)
    for ac_id, risk, expected_type in acs:
        result = outcomes.get(ac_id)
        if result is None:
            errors.append(f"检查报告缺少 AC：{ac_id}")
        elif result[0] != "pass":
            errors.append(f"AC 未通过：{ac_id} = {result[0]}")
        elif result[1] != expected_type:
            errors.append(f"AC 证据类型不匹配：{ac_id} 需要 {expected_type}，实际 {result[1]}")
        elif risk == "高" and result[1] == "人工":
            errors.append(f"高风险 AC 不得只使用人工证据：{ac_id}")
    if value_after(tasks, "状态") != "待交付":
        errors.append("tasks.md 尚未标记为待交付")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec_dir", type=Path, help=".spec 下的单个任务目录")
    parser.add_argument("--stage", choices=("draft", "delivery"), required=True)
    args = parser.parse_args()
    errors: list[str] = []
    spec = record_text(read(args.spec_dir / "spec.md", errors), errors)
    if not spec.strip():
        errors.append("Spec 为空或没有代码块之外的有效记录")
    acs = validate_draft(args.spec_dir, spec, errors) if spec else []
    if args.stage == "delivery" and spec:
        validate_delivery(args.spec_dir, spec, acs, errors)
    if errors:
        print("Spec 检查失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Spec 检查通过：{args.spec_dir} ({args.stage})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
