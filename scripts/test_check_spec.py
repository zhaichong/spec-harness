import sys
import tempfile
import unittest
import shutil
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_spec import main


SURFACES = """
## 变更面
- 数据写入/删除：否
- 权限/敏感数据：否
- 外部副作用：否
- 不可逆：否
- 生产或批量：否
"""

SPEC = """# Spec
> 流程档位：Spec
> Spec 版本：v1
> 原始需求：增加示例功能
> 审核状态：自审通过
> 作者确认：v1，确认；接受未独立审核
""" + SURFACES + """
## 验收标准
- [ ] **AC-01** [风险：低] [证据类型：自动化] 示例行为可验证
"""

TASKS = """# Tasks
- [x] **T-01** [required] 实现示例 → AC-01

## 当前状态
- 状态：待交付
"""

DELIVERY_REVIEW = """# Delivery Review
> 审核的 Spec：v1
> 审核者：当前 Agent（自审）
> 审核范围：任务、AC、证据与遗留风险
> 审核来源：本次任务会话
> 审核结论：通过
"""

REPORT = """# Harness Check
| AC | 结果 | 证据类型 | 证据 | 未覆盖风险 |
|---|---|---|---|---|
| AC-01 | pass | 自动化 | pytest test_example；文件：evidence/AC-01-test.txt | 无 |
"""

STRICT_SPEC = """# Spec
> 流程档位：Strict
> Spec 版本：v2
> 原始需求：执行受控迁移
> 审核状态：fresh review
> 作者确认：待确认
""" + SURFACES + """
## 验收标准
- [ ] **AC-01** [风险：高] [证据类型：可复现命令] dry-run 输出可复核

## Spec 审核
- 审核者：新 Agent / session-2
- 审核版本与输入：Spec v2、原始需求、迁移代码
- 审核输出引用：session/independent-review.md
- 独立性：fresh review
"""

STRICT_REVIEW = """# Independent Review
> 审核的 Spec：v2
> 审核者：新 Agent
> 审核来源：Codex 新 Agent / session-2
> 输入范围：原始需求、迁移代码、Spec v2
> 独立性声明：审核者确认未读取起草过程，只读取上述输入

## 结论
- 结论：通过
"""

ADVERSARIAL_REVIEW = """# 对抗自审
> 审核的 Spec：v1
> 审核方式：同一 Agent 的反方视角
> 输入范围：原始需求、Spec v1、目标代码
- 结论：通过
"""


class CheckSpecTest(unittest.TestCase):
    def test_delivery_rejects_empty_required_documents(self) -> None:
        for relative in ("tasks.md", "check_reports/harness-check.md"):
            for content in ("", " \n\t", "```\nexample\n```"):
                with self.subTest(relative=relative, content=content), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    self.make_artifacts(root)
                    (root / relative).write_text(content, encoding="utf-8")
                    with self._args(root, "delivery"):
                        self.assertEqual(main(), 1)

    def test_delivery_rejects_duplicate_single_value_fields(self) -> None:
        for relative, extra in (
            ("spec.md", "> 审核状态：阻塞"),
            ("spec.md", "- 权限/敏感数据：是"),
            ("spec.md", "> Spec 版本：v1"),
            ("tasks.md", "- 状态：已阻塞"),
            ("check_reports/delivery-review.md", "> 审核结论：阻塞"),
        ):
            with self.subTest(relative=relative, extra=extra), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root)
                path = root / relative
                path.write_text(path.read_text(encoding="utf-8") + "\n" + extra + "\n", encoding="utf-8")
                with self._args(root, "delivery"):
                    self.assertEqual(main(), 1)

    def test_duplicate_external_execution_state_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_strict_delivery(root, "> 实际执行：无\n> 实际执行：有\n")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_canonical_risk_surface_names_are_accepted(self) -> None:
        for surface in ("数据写入/删除", "权限/敏感数据"):
            with self.subTest(surface=surface), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root)
                spec = SPEC.replace(f"{surface}：否", f"{surface}：是").replace("风险：低", "风险：高")
                if surface == "权限/敏感数据":
                    (root / "session").mkdir()
                    (root / "session/independent-review.md").write_text(STRICT_REVIEW.replace("v2", "v1"), encoding="utf-8")
                (root / "spec.md").write_text(spec + f"\n- KR-01 [{surface}] → AC-01\n", encoding="utf-8")
                with self._args(root, "draft"):
                    self.assertEqual(main(), 0)

    def make_artifacts(self, root: Path, task_line: str = TASKS) -> None:
        (root / "check_reports").mkdir()
        (root / "evidence").mkdir()
        (root / "spec.md").write_text(SPEC, encoding="utf-8")
        (root / "tasks.md").write_text(task_line, encoding="utf-8")
        (root / "check_reports" / "harness-check.md").write_text(REPORT, encoding="utf-8")
        (root / "check_reports" / "delivery-review.md").write_text(DELIVERY_REVIEW, encoding="utf-8")
        (root / "evidence" / "AC-01-test.txt").write_text("pytest test_example: passed", encoding="utf-8")

    def test_delivery_accepts_complete_traceability(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            with self._args(root, "delivery"):
                self.assertEqual(main(), 0)

    def test_delivery_does_not_require_delivery_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            (root / "check_reports" / "delivery-review.md").unlink()
            with self._args(root, "delivery"):
                self.assertEqual(main(), 0)

    def test_delivery_requires_explicit_completed_review_status(self) -> None:
        for status, expected in (
            ("自审通过", 0), ("对抗自审通过", 0), ("阻塞", 1), ("待澄清", 1),
            ("未通过", 1), ("自审通过；仍待澄清", 1), ("未独立（用户明确接受）", 1),
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root)
                (root / "spec.md").write_text(SPEC.replace("审核状态：自审通过", f"审核状态：{status}"), encoding="utf-8")
                with self._args(root, "delivery"):
                    self.assertEqual(main(), expected)

    def test_draft_can_record_pending_clarification(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(SPEC.replace("审核状态：自审通过", "审核状态：待澄清"), encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 0)

    def test_existing_delivery_review_must_be_complete_and_passed(self) -> None:
        for review in (
            "", " \n\t", "# Delivery Review\n",
            DELIVERY_REVIEW.replace("审核结论：通过", "审核结论：未通过"),
            DELIVERY_REVIEW.replace("审核结论：通过", "审核结论：待通过"),
            DELIVERY_REVIEW.replace("审核的 Spec：v1", "审核的 Spec：v2"),
        ):
            with self.subTest(review=review), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root)
                (root / "check_reports" / "delivery-review.md").write_text(review, encoding="utf-8")
                with self._args(root, "delivery"):
                    self.assertEqual(main(), 1)

    def test_delivery_accepts_existing_implementation_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            spec = SPEC.replace(
                "> 作者确认：v1，确认；接受未独立审核",
                "> 实施授权：用户在本任务要求“实现示例功能”，涵盖当前实现范围。",
            )
            (root / "spec.md").write_text(spec, encoding="utf-8")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 0)

    def test_delivery_rejects_pending_authorization_even_with_old_confirmation(self) -> None:
        for authorization in ("", "待确认", "{{用户原话}}", "待确认：扩大的数据范围", "无"):
            with self.subTest(authorization=authorization), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root)
                (root / "spec.md").write_text(
                    SPEC + f"\n> 实施授权：{authorization}\n", encoding="utf-8"
                )
                with self._args(root, "delivery"):
                    self.assertEqual(main(), 1)

    def test_blank_authorization_does_not_consume_next_metadata_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            (root / "spec.md").write_text(
                SPEC.replace("> 作者确认：", "> 实施授权：\n> 作者确认："), encoding="utf-8"
            )
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_empty_review_files_are_not_valid_reviews(self) -> None:
        for name, spec in (("adversarial-review.md", SPEC), ("independent-review.md", STRICT_SPEC)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "spec.md").write_text(spec, encoding="utf-8")
                (root / "session").mkdir()
                (root / "session" / name).write_text("", encoding="utf-8")
                with self._args(root, "draft"):
                    self.assertEqual(main(), 1)

    def test_chinese_independent_review_claim_requires_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(
                SPEC.replace("自审通过", "独立复查通过"), encoding="utf-8"
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_optional_adversarial_review_is_checked_when_present(self) -> None:
        for version, conclusion, expected in (("v1", "通过", 0), ("v2", "通过", 1), ("v1", "阻塞", 1), ("v1", "未通过", 1)):
            with self.subTest(version=version, conclusion=conclusion), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root)
                (root / "session").mkdir()
                (root / "session" / "adversarial-review.md").write_text(
                    ADVERSARIAL_REVIEW.replace("v1", version).replace("结论：通过", f"结论：{conclusion}"),
                    encoding="utf-8",
                )
                with self._args(root, "delivery"):
                    self.assertEqual(main(), expected)

    def test_incremental_delivery_can_reuse_unaffected_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            spec = SPEC.replace("Spec 版本：v1", "Spec 版本：v2").replace(
                "> 作者确认：v1，确认；接受未独立审核",
                "> 实施授权：本任务用户要求实现示例并补充空数据提示。",
            )
            spec += "\n- [ ] **AC-02** [风险：低] [证据类型：自动化] 空数据提示可验证\n"
            (root / "spec.md").write_text(spec, encoding="utf-8")
            (root / "tasks.md").write_text(
                TASKS + "\n- [x] **T-02** [required] 增加空数据提示 → AC-02\n", encoding="utf-8"
            )
            report = REPORT.replace("pytest test_example；", "复用 v1 的测试；依赖和行为未变；")
            report += "| AC-02 | pass | 自动化 | pytest test_empty；文件：evidence/empty-test.txt | 无 |\n"
            (root / "check_reports" / "harness-check.md").write_text(report, encoding="utf-8")
            (root / "evidence" / "empty-test.txt").write_text("empty state: passed", encoding="utf-8")
            (root / "check_reports" / "delivery-review.md").write_text(
                DELIVERY_REVIEW.replace("v1", "v2"), encoding="utf-8"
            )
            with self._args(root, "delivery"):
                self.assertEqual(main(), 0)

    def test_multiple_acceptance_criteria_can_share_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            (root / "spec.md").write_text(
                SPEC + "\n- [ ] **AC-02** [风险：低] [证据类型：自动化] 空数据不报错\n", encoding="utf-8"
            )
            (root / "tasks.md").write_text(TASKS.replace("→ AC-01", "→ AC-01, AC-02"), encoding="utf-8")
            (root / "check_reports" / "harness-check.md").write_text(
                REPORT + "| AC-02 | pass | 自动化 | pytest test_example 覆盖空数据；文件：evidence/AC-01-test.txt | 无 |\n",
                encoding="utf-8",
            )
            with self._args(root, "delivery"):
                self.assertEqual(main(), 0)

    def test_delivery_rejects_orphaned_ac(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root, TASKS.replace("→ AC-01", ""))
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_incomplete_acceptance_criteria_are_not_silently_dropped(self) -> None:
        for declaration in (
            "- [ ] [风险：低] [证据类型：自动化] 缺少验收编号",
            "- [ ] **AC-02** 异常时必须可重试",
            "- [ ] **AC-02** [风险：中] 异常时必须可重试",
            "- [ ] **AC-02** [证据类型：自动化] 异常时必须可重试",
            "- [ ] **AC-02** [风险：未知] [证据类型：自动化] 异常时必须可重试",
            "- [ ] **AC-02** [风险：低] [证据类型：自动化] {{验收结果}}",
            "- [ ] **AC-new** [风险：低] [证据类型：自动化] 异常时必须可重试",
        ):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root)
                (root / "spec.md").write_text(SPEC + "\n" + declaration + "\n", encoding="utf-8")
                with self._args(root, "delivery"):
                    self.assertEqual(main(), 1)

    def test_task_records_must_be_complete_and_use_current_unique_ids(self) -> None:
        for declaration in (
            "- [ ] [required] 缺少任务编号 → AC-01",
            "- [ ] **T-02** [required] 增加错误提示",
            "- [x] **T-02** [required] 增加错误提示 →",
            "- [ ] **T-02** 增加错误提示 → AC-01",
            "- [ ] **T-new** [required] 增加错误提示 → AC-01",
            "- [x] **T-02** [required] 增加错误提示 → AC-99",
            "- [x] **T-02** [required] 增加错误提示 → AC-01x",
            "- [x] **T-01** [required] 重复编号 → AC-01",
        ):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root, TASKS + "\n" + declaration + "\n")
                with self._args(root, "delivery"):
                    self.assertEqual(main(), 1)

    def test_optional_task_without_acceptance_criteria_remains_optional(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root, TASKS + "\n- [ ] **T-02** [optional] 后续改进建议 → 无\n")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 0)

    def test_fenced_examples_are_not_acceptance_or_task_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root, TASKS + "\n~~~markdown\n- [ ] **T-99** [required] 示例 → AC-01\n~~~\n")
            (root / "spec.md").write_text(
                SPEC + "\n```markdown\n- [ ] **AC-99** [风险：高] [证据类型：人工] 仅示例\n```\n",
                encoding="utf-8",
            )
            with self._args(root, "delivery"):
                self.assertEqual(main(), 0)

    def test_unclosed_example_cannot_hide_pending_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root, TASKS + "\n```text\n- [ ] **T-02** [required] 增加提示\n")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_empty_or_example_only_spec_cannot_pass(self) -> None:
        for content in ("", " \n\t", "```markdown\n" + SPEC + "\n```\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_artifacts(root)
                (root / "spec.md").write_text(content, encoding="utf-8")
                with self._args(root, "delivery"):
                    self.assertEqual(main(), 1)

    def test_delivery_status_must_be_exact_not_a_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root, TASKS.replace("状态：待交付", "状态：待交付前仍需验证"))
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_delivery_rejects_duplicate_ac_or_empty_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            report = (root / "check_reports" / "harness-check.md")
            report.write_text(REPORT.replace("pytest test_example", "正常") + "| AC-01 | pass | 自动化 | pytest duplicate | 无 |\n", encoding="utf-8")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_delivery_rejects_missing_evidence_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            (root / "evidence" / "AC-01-test.txt").unlink()
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def _write_strict_delivery(self, root: Path, log: str, confirm: str = "v2，确认") -> None:
        (root / "check_reports").mkdir()
        (root / "evidence").mkdir()
        (root / "session").mkdir()
        spec = STRICT_SPEC.replace("作者确认：待确认", f"作者确认：{confirm}")
        (root / "spec.md").write_text(spec, encoding="utf-8")
        (root / "plan.md").write_text("# Plan\ncontrolled migration\n", encoding="utf-8")
        (root / "session" / "independent-review.md").write_text(STRICT_REVIEW, encoding="utf-8")
        (root / "session" / "log.md").write_text(log, encoding="utf-8")
        (root / "tasks.md").write_text(
            TASKS.replace("AC-01", "AC-01").replace("实现示例", "执行迁移"),
            encoding="utf-8",
        )
        report = REPORT.replace("自动化", "可复现命令").replace("pytest test_example", "python migrate.py --dry-run")
        (root / "check_reports" / "harness-check.md").write_text(report, encoding="utf-8")
        (root / "evidence" / "AC-01-test.txt").write_text("python migrate.py --dry-run: ok", encoding="utf-8")

    def test_strict_delivery_requires_external_auth_or_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_strict_delivery(root, "# Log\n| 操作 | 范围 | 预览 | 用户确认原话 | 失效 |\n|---|---|---|---|---|\n| 迁移 | prod | dry-run | | 范围变化 |\n")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_strict_delivery_accepts_no_side_effect_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_strict_delivery(root, "# Log\n无外部副作用\n")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 0)

    def test_external_log_checks_actual_state_and_every_operation(self) -> None:
        header = "| 操作 | 目标/数据范围 | dry-run / 预览证据 | 用户确认原话 | 失效条件 |\n|---|---|---|---|---|\n"
        valid = "| 更新数据 | 测试租户 | preview.txt | 用户要求更新此租户 | 范围变化 |\n"
        missing_auth = "| 无损迁移 | 生产用户表 | preview.txt | | 范围变化 |\n"
        cases = (
            ("explicit_none", "> 实际执行：无\n", 0),
            ("legacy_none", "无外部副作用：只实现代码\n", 0),
            ("legacy_none_row", header + "| 无 | | | | |\n", 0),
            ("authorized", "> 实际执行：有\n" + header + valid, 0),
            ("legacy_authorized", header + valid, 0),
            ("all_authorized", "> 实际执行：有\n" + header + valid + valid.replace("更新数据", "无损迁移"), 0),
            ("instruction_is_not_state", "仅实现代码时写「无外部副作用：未执行共享或外部写入」。\n" + header + missing_auth, 1),
            ("other_table_is_not_authorization", "| 时间 | 事件 | 决策 | 影响 |\n|---|---|---|---|\n| 今天 | 进入 Spec | 已知 | 无 |\n\n" + header + missing_auth, 1),
            ("second_operation_unauthorized", header + valid + missing_auth, 1),
            ("contradictory_none", "> 实际执行：无\n" + header + valid, 1),
            ("contradictory_legacy_none", "无外部副作用\n" + header + valid, 1),
            ("leftover_none_row", header + "| 无 | | | | |\n" + valid, 1),
            ("executed_without_operations", "> 实际执行：有\n" + header, 1),
            ("executed_with_none_row", "> 实际执行：有\n" + header + "| 无 | | | | |\n", 1),
            ("empty", "", 1),
            ("unknown_state", "> 实际执行：待填写\n" + header + valid, 1),
            ("no_state_no_operations", "# Log\n仅供参考：无外部副作用\n", 1),
            ("unfilled_template", (SCRIPTS.parent / "templates" / "session-log.md").read_text(encoding="utf-8"), 1),
        )
        for name, log, expected in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self._write_strict_delivery(root, log)
                with self._args(root, "delivery"):
                    self.assertEqual(main(), expected)

    def test_external_operation_requires_all_record_fields(self) -> None:
        header = "| 操作 | 范围 | 预览 | 用户确认原话 | 失效 |\n|---|---|---|---|---|\n"
        for column in range(5):
            for missing in ("", "{{待填写}}", "待确认"):
                with self.subTest(column=column, missing=missing), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    fields = ["更新", "租户 A", "preview.txt", "用户已授权更新租户 A", "范围变化"]
                    fields[column] = missing
                    self._write_strict_delivery(root, "> 实际执行：有\n" + header + "| " + " | ".join(fields) + " |\n")
                    with self._args(root, "delivery"):
                        self.assertEqual(main(), 1)

    def test_external_records_survive_spacing_and_ignore_examples(self) -> None:
        header = "| 操作 | 范围 | 预览 | 用户确认原话 | 失效 |\n|---|---|---|---|---|\n"
        valid = "| 更新 | 租户 A | preview.txt | 用户要求更新 A | 范围变化 |\n"
        invalid = "| 删除 | 租户 B | preview.txt | | 范围变化 |\n"
        for name, log, expected in (
            ("blank_between_operations", "> 实际执行：有\n" + header + valid + "\n" + invalid, 1),
            ("note_between_operations", "> 实际执行：有\n" + header + valid + "\n补充一项操作：\n" + invalid, 1),
            ("valid_spacing", "> 实际执行：有\n" + header + valid + "\n" + valid.replace("租户 A", "租户 B"), 0),
            ("example_only", "示例：\n```text\n无外部副作用\n```\n", 1),
            ("example_cannot_supply_state", "~~~text\n> 实际执行：无\n~~~\n", 1),
            ("example_cannot_supply_authorization", "> 实际执行：有\n```text\n" + header + valid + "```\n", 1),
            ("example_does_not_conflict", "> 实际执行：有\n" + header + valid + "\n```text\n无外部副作用\n```\n", 0),
            ("longer_fence", "> 实际执行：有\n" + header + valid + "\n````markdown\n```text\n无外部副作用\n```\n````\n", 0),
            ("unclosed_fence", "> 实际执行：有\n" + header + valid + "\n```text\n" + invalid, 1),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self._write_strict_delivery(root, log)
                with self._args(root, "delivery"):
                    self.assertEqual(main(), expected)

    def test_powershell_rejects_pending_self_review(self) -> None:
        def populate(root: Path) -> None:
            self.make_artifacts(root)
            (root / "spec.md").write_text(SPEC.replace("审核状态：自审通过", "审核状态：待澄清"), encoding="utf-8")

        self._assert_powershell(populate, "delivery", 1)

    def test_spec_elevate_surface_requires_independent_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(
                SPEC.replace("权限/敏感数据：否", "权限/敏感数据：是"),
                encoding="utf-8",
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_ordinary_data_write_does_not_require_independent_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = SPEC.replace("数据写入/删除：否", "数据写入/删除：是")
            spec = spec.replace("风险：低", "风险：高")
            spec += "\n- KR-01 [数据写入] → AC-01\n"
            (root / "spec.md").write_text(spec, encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 0)

    def test_legacy_standard_tier_still_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(SPEC.replace("流程档位：Spec", "流程档位：Standard"), encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 0)

    def test_strict_draft_requires_real_review_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "session").mkdir()
            (root / "spec.md").write_text(STRICT_SPEC, encoding="utf-8")
            (root / "session" / "independent-review.md").write_text(STRICT_REVIEW, encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 0)

    def test_delivery_rejects_high_risk_manual_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            (root / "spec.md").write_text(SPEC.replace("风险：低] [证据类型：自动化", "风险：高] [证据类型：人工"), encoding="utf-8")
            report = root / "check_reports" / "harness-check.md"
            report.write_text(REPORT.replace("自动化", "人工"), encoding="utf-8")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_draft_rejects_claimed_review_without_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(SPEC.replace("自审通过", "fresh review"), encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_draft_rejects_unmapped_high_risk_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(SPEC.replace("数据写入/删除：否", "数据写入/删除：是"), encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_draft_rejects_unresolved_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(SPEC.replace("数据写入/删除：否", "数据写入/删除：是 / 否"), encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_draft_rejects_broad_kr_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = SPEC.replace("数据写入/删除：否", "数据写入/删除：是")
            spec += "\n- KR-01 [日志写入] → AC-01\n"
            (root / "spec.md").write_text(spec.replace("风险：低", "风险：高"), encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_draft_rejects_claimed_review_by_current_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "session").mkdir()
            spec = SPEC.replace("自审通过", "fresh review")
            spec += """
## Spec 审核
- 审核者：当前 Agent（非人工）
- 审核版本与输入：Spec v1、原始需求、相关代码
- 审核输出引用：session/independent-review.md
- 独立性：fresh review
"""
            (root / "spec.md").write_text(spec, encoding="utf-8")
            (root / "session" / "independent-review.md").write_text(
                STRICT_REVIEW.replace("v2", "v1").replace("新 Agent", "当前 Agent（非人工）"),
                encoding="utf-8",
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_draft_rejects_unfilled_ac_options(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(
                SPEC.replace(
                    "[风险：低] [证据类型：自动化]",
                    "[风险：低 / 中 / 高] [证据类型：自动化 / 可复现命令 / 浏览器 / 人工]",
                ),
                encoding="utf-8",
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_draft_ignores_unfilled_kr_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            leftover = "\n- KR-01 [数据写入 / 权限敏感 / 外部副作用 / 不可逆] → AC-01\n"
            (root / "spec.md").write_text(SPEC.replace("数据写入/删除：否", "数据写入/删除：是") + leftover, encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_powershell_accepts_complete_traceability(self) -> None:
        self._assert_powershell(self.make_artifacts, "delivery", 0)

    def test_ac_pattern_stays_on_one_line(self) -> None:
        from check_spec import AC_PATTERN

        text = "- [ ] **AC-01** [风险：高] 无证据类型\n- [ ] **AC-02** [风险：低] [证据类型：自动化] ok\n"
        self.assertEqual(AC_PATTERN.findall(text), [("AC-02", "低", "自动化")])

    def test_draft_accepts_unindependent_status_mentioning_fresh_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(
                SPEC.replace("自审通过", "未独立（无法获得 fresh review）"),
                encoding="utf-8",
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 0)

    def test_draft_rejects_unresolved_tier(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(
                SPEC.replace("流程档位：Spec", "流程档位：Spec / Fast"),
                encoding="utf-8",
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_delivery_rejects_prefix_version_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            (root / "spec.md").write_text(SPEC.replace("作者确认：v1，确认", "作者确认：v10，确认"), encoding="utf-8")
            with self._args(root, "delivery"):
                self.assertEqual(main(), 1)

    def test_draft_rejects_review_conclusion_without_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "session").mkdir()
            (root / "spec.md").write_text(STRICT_SPEC, encoding="utf-8")
            (root / "session" / "independent-review.md").write_text(
                STRICT_REVIEW.replace("结论：通过", "结论：已修正问题"),
                encoding="utf-8",
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_runtimes_accept_strict_draft_pass_conclusion(self) -> None:
        def write_strict(root: Path) -> None:
            (root / "session").mkdir()
            (root / "spec.md").write_text(STRICT_SPEC, encoding="utf-8")
            (root / "session" / "independent-review.md").write_text(STRICT_REVIEW, encoding="utf-8")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_strict(root)
            with self._args(root, "draft"):
                self.assertEqual(main(), 0)
        self._assert_powershell(write_strict, "draft", 0)

    def _assert_powershell(self, populate, stage: str, expected: int) -> None:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            self.skipTest("PowerShell is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            populate(root)
            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPTS / "check_spec.ps1"),
                    "-SpecDir",
                    str(root),
                    "-Stage",
                    stage,
                ],
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                expected,
                result.stderr.decode("utf-8", errors="replace") or result.stdout.decode("utf-8", errors="replace"),
            )

    def _args(self, root: Path, stage: str):
        import sys

        class Arguments:
            def __enter__(self):
                self.original = sys.argv
                sys.argv = ["check_spec.py", str(root), "--stage", stage]

            def __exit__(self, *_):
                sys.argv = self.original

        return Arguments()


if __name__ == "__main__":
    unittest.main()
