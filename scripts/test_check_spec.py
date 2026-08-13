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
"""

SPEC = """# Spec
> 流程档位：Standard
> Spec 版本：v1
> 原始需求：增加示例功能
> 审核状态：未独立（用户明确接受）
> 用户确认：v1，确认；接受未独立审核
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
> 用户确认：待确认
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


class CheckSpecTest(unittest.TestCase):
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

    def test_delivery_rejects_orphaned_ac(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root, TASKS.replace("→ AC-01", ""))
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
        spec = STRICT_SPEC.replace("用户确认：待确认", f"用户确认：{confirm}")
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
            (root / "spec.md").write_text(SPEC.replace("未独立（用户明确接受）", "fresh review"), encoding="utf-8")
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
            spec = SPEC.replace("未独立（用户明确接受）", "fresh review")
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
                SPEC.replace("未独立（用户明确接受）", "未独立（无法获得 fresh review）"),
                encoding="utf-8",
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 0)

    def test_draft_rejects_unresolved_tier(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "spec.md").write_text(
                SPEC.replace("流程档位：Standard", "流程档位：Standard / Strict"),
                encoding="utf-8",
            )
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_delivery_rejects_prefix_version_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            (root / "spec.md").write_text(SPEC.replace("用户确认：v1，确认", "用户确认：v10，确认"), encoding="utf-8")
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
