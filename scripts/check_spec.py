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
    r"\*\*(AC-\d+)\*\*[^\n]*风险：\s*(低|中|高)(?!\s*/)[^\n]*证据类型：\s*(自动化|可复现命令|浏览器|人工)(?!\s*/)"
)
TASK_PATTERN = re.compile(r"- \[[ xX]\] \*\*T-\d+\*\* \[(required|optional)\].*?→\s*(.+)")
KR_PATTERN = re.compile(r"^-\s*(KR-\d+)\s*\[([^]]+)\]\s*→\s*(.+)$", re.MULTILINE)
ARTIFACT_PATTERN = re.compile(r"(?:文件|file)\s*[:：]\s*([^\s#；;|]+)", re.IGNORECASE)
PLACEHOLDER_VALUES = {"", "无", "不适用", "n/a", "na", "待确认", "待填写", "未填写"}
GENERIC_EVIDENCE = PLACEHOLDER_VALUES | {"正常", "通过", "已验证", "pass", "-", "…"}
BLOCKING_CONCLUSIONS = ("阻塞", "退回", "不通过", "有条件")
INDEPENDENT_ACTORS = ("新 agent", "不同模型", "人工")
DEPENDENT_MARKERS = ("同一 agent", "当前 agent", "非人工", "自审", "未独立", "新上下文")
RISK_SURFACES = {
    "数据写入/删除": ("数据写入/删除", "数据写入", "数据删除"),
    "权限/敏感数据": ("权限/敏感数据", "权限敏感", "敏感数据", "权限"),
    "外部副作用": ("外部副作用",),
    "不可逆": ("不可逆",),
}


def read(path: Path, errors: list[str]) -> str:
    if not path.is_file():
        errors.append(f"缺少文件：{path}")
        return ""
    return path.read_text(encoding="utf-8")


def value_after(text: str, label: str) -> str | None:
    match = re.search(rf"^[>-]\s*{re.escape(label)}：\s*(.+)$", text, re.MULTILINE)
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
    return any(value == "是" for value in values.values())


def claims_independent_review(status: str | None, elevated: bool) -> bool:
    if elevated:
        return True
    text = status or ""
    if "未独立" in text:
        return False
    return bool(re.match(r"^\s*(fresh review|人工复查)\b", text, re.IGNORECASE))


def conclusion_ok(value: str | None) -> bool:
    text = value or ""
    return "通过" in text and not any(word in text for word in BLOCKING_CONCLUSIONS)


def independent_actor(value: str | None) -> bool:
    normalized = (value or "").lower()
    if not normalized or any(marker in normalized for marker in DEPENDENT_MARKERS):
        return False
    return any(actor in normalized for actor in INDEPENDENT_ACTORS)


def validate_review(directory: Path, spec: str, elevated: bool, errors: list[str]) -> None:
    for label in ("审核者", "审核版本与输入", "审核输出引用", "独立性"):
        if unresolved(value_after(spec, label)):
            errors.append(f"独立审核记录未填写：{label}")
    if not independent_actor(value_after(spec, "审核者")):
        errors.append("审核者不满足所声明的独立性要求")
    if "session/independent-review.md" not in (value_after(spec, "审核输出引用") or ""):
        errors.append("审核输出引用必须指向 session/independent-review.md")

    review = read(directory / "session" / "independent-review.md", errors)
    if not review:
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
    if elevated and "未独立" in (value_after(spec, "独立性") or ""):
        errors.append("高风险变更不能以未独立状态通过审核")


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
        if "/" not in kind and "{{" not in kind
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

    acs = AC_PATTERN.findall(spec)
    ids = [ac_id for ac_id, _, _ in acs]
    if not ids:
        errors.append("未找到带风险和证据类型的 AC")
    if len(ids) != len(set(ids)):
        errors.append("AC 编号重复")
    surfaces = parse_risk_surfaces(spec, errors)
    validate_risk_mapping(spec, acs, surfaces, errors)

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
    version = value_after(spec, "Spec 版本") or ""
    confirmation = value_after(spec, "用户确认")
    if unresolved(confirmation):
        errors.append("用户确认未填写")
    elif not mentions_version(confirmation, version):
        errors.append(f"用户确认未关联当前 Spec 版本：需要 {version}")
    if "未独立" in (value_after(spec, "审核状态") or "") and "接受未独立" not in (confirmation or ""):
        errors.append("未独立审核必须获得用户明确接受")


def validate_delivery_review(directory: Path, spec: str, errors: list[str]) -> None:
    path = directory / "check_reports" / "delivery-review.md"
    if not path.is_file():
        return
    review = read(path, errors)
    if not review:
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
    text = read(directory / "session" / "log.md", errors)
    if not text:
        return
    if "无外部副作用" in text:
        return
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] in {"操作", ":---", "---"} or set(cells[0]) <= {"-"}:
            continue
        if cells[0].startswith("无"):
            return
        quote = cells[3] if len(cells) >= 4 else ""
        if not unresolved(quote):
            return
    errors.append("高风险外部授权记录必须写无，或填写用户确认原话")


def validate_delivery(directory: Path, spec: str, acs: list[tuple[str, str, str]], errors: list[str]) -> None:
    validate_confirmation(spec, errors)
    validate_delivery_review(directory, spec, errors)
    if elevated_risk(spec):
        require_nonempty(directory, "plan.md", errors)
        validate_strict_session_log(directory, errors)

    tasks = read(directory / "tasks.md", errors)
    report = read(directory / "check_reports" / "harness-check.md", errors)
    if not tasks or not report:
        return

    required_ac_ids: set[str] = set()
    current_ac_ids = {ac_id for ac_id, _, _ in acs}
    for line in tasks.splitlines():
        match = TASK_PATTERN.search(line)
        if not match:
            continue
        kind, linked = match.groups()
        if kind == "required" and not line.startswith("- [x]") and not line.startswith("- [X]"):
            errors.append(f"必需任务未完成：{line.strip()}")
        linked_ids = set(re.findall(r"AC-\d+", linked))
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
    if "- 状态：待交付" not in tasks:
        errors.append("tasks.md 尚未标记为待交付")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec_dir", type=Path, help=".spec 下的单个任务目录")
    parser.add_argument("--stage", choices=("draft", "delivery"), required=True)
    args = parser.parse_args()
    errors: list[str] = []
    spec = read(args.spec_dir / "spec.md", errors)
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
