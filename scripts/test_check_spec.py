import tempfile
import unittest
import shutil
import subprocess
from pathlib import Path

from check_spec import main


SPEC = """# Spec
> 流程档位：Standard
> Spec 版本：v1
> 原始需求：增加示例功能
> 审核状态：未独立（用户明确接受）
> 用户确认：v1，确认；接受未独立审核

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
            (root / "spec.md").write_text(SPEC + "\n- 数据写入/删除：是\n", encoding="utf-8")
            with self._args(root, "draft"):
                self.assertEqual(main(), 1)

    def test_powershell_accepts_complete_traceability(self) -> None:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            self.skipTest("PowerShell is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_artifacts(root)
            result = subprocess.run(
                [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(Path(__file__).with_name("check_spec.ps1")), "-SpecDir", str(root), "-Stage", "delivery"],
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))

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
