---
name: spec-harness
description: 为前端、Java 后端及前后端联动的功能开发、跨文件修改、缺陷修复、数据取数、批量操作、迁移及其他需要范围控制或验证证据的任务执行风险自适应的 Spec + Harness 流程。根据风险选择 Fast、Standard 或 Strict；领域细则覆盖前端、Java 后端和全栈契约，非 Java 后端只走主流程。对小型低风险修改保持轻量，对需求含糊、高风险、不可逆或具有外部副作用的操作设置人工确认卡点。
---

# Spec + Harness

Spec 定义做什么。结构校验只检查产物齐不齐，不证明测试真跑过，也不证明审核独立。终点是待交付，默认不上线。

## 优先级

1. 系统与安全规则
2. 用户明确要求和授权边界
3. 项目 `AGENTS.md`、贡献规范、现有工作流
4. 本 Skill 默认流程

完整描述需求只授权探测和写 Spec 草案。「不需确认」不能代替确认。先读后写；不编造接口或业务规则；不覆盖用户未提交改动；不伪造验证；未经授权不碰共享状态或外部系统。

## 定档

选最低但够用的一档；拿不准就升高。Spec 里「流程档位」只能写成 `Standard` 或 `Strict`。

| 档位 | 何时使用 | 编码前 |
|---|---|---|
| Fast | 局部可逆；不改对外接口、库表/业务数据、权限、外部系统、公共组件默认行为。同一小缺陷改少数相关文件可以 | 聊天说明范围和最小验证后可改 |
| Standard | 新功能、一般回归、改公共契约或共享状态 | 必须确认当前 Spec 版本 |
| Strict | 迁移、批量写、权限/合规、不可逆、生产副作用 | 必须有独立复查记录，再确认当前版本 |

仅调用公共组件且不改其默认行为，仍可以是 Fast。触及前端读 `references/frontend.md`；触及 Java 服务读 `references/backend-java.md`；改双方契约再读 `references/fullstack-contract.md`。非 Java 后端只走主流程。

## 产物

Fast 默认不建文件。Standard / Strict 建在项目根或用户指定目录，已存在则复用或加 `-2`，不覆盖：

```text
.spec/<YYYY-MM-DD>-<简述>/
  spec.md
  tasks.md
  plan.md                      # 仅 Strict 或多种方案时
  check_reports/harness-check.md
  evidence/
  session/log.md               # 仅 Strict
  session/independent-review.md # 仅声称独立或 Strict
```

`tasks.md` 是唯一进度。不要为填模板而编造段落。

## 工作流

1. **探测**：读相关规则、目标代码、构建测试配置、git 状态。输出：事实、未知项、档位及理由。
2. **Spec**：写可观察目标、场景、数据/副作用、AC（`AC-01`，带风险和证据类型）、非目标。高风险变更面必须是单独的「是」或「否」，为「是」时映射到高风险 AC，例如 `KR-01 [数据写入] → AC-02`。数据/权限/外部副作用/不可逆的 AC 不得只用「人工」证据。
3. **审核后确认**：同一会话自审标「未独立」，不得称 fresh review。独立复查只接受人工、新 Agent 或不同模型，并用模板落到 `session/independent-review.md`。Standard 未独立须用户明确接受。Strict 缺独立记录则阻塞。用户回复「确认 / 确认 Spec / OK / 开始编码」且 Spec 写上当前版本后才能编码。范围变化则更新 Spec、重审、再确认。
4. **任务**：拆 `T-01`，每项引用 AC；每个当前 AC 至少被一项 `[required]` 引用。Strict 写 `plan.md`。不默认切分支；未提交改动与本次重叠则先停写。
5. **实施**：按任务做，不做 Spec 外优化。
6. **验证**：只跑与改动相关、成本合理的检查。默认跳过 build/package。把命令、结果和 `文件：evidence/...` 写入 `harness-check.md`。UI/API/数据按类型补最小路径。
7. **待交付**：required 任务完成，每个 AC 为 `pass` 且有证据，副作用未经授权未发生。然后把 `tasks.md` 标为待交付。不自动 merge、push、部署或写生产数据。

Strict 外部写入前：在 `session/log.md` 写清操作、范围、dry-run、用户原话和失效条件，按该范围再确认一次。无外部副作用则在授权表写「无」。

## 结构校验

根目录是本 `SKILL.md` 所在目录。确认前：`scripts/check_spec.py <.spec/任务目录> --stage draft`。待交付前：同一命令 `--stage delivery`。也可用 `scripts/check_spec.ps1` 启动它。校验器只看结构和映射；没有 Python 则停，不用手填清单代替。

## 模板

- `templates/spec.md`、`tasks.md`、`harness-check.md`
- `templates/plan.md`、`session-log.md`：Strict
- `templates/independent-review.md`：声称独立或 Strict
- `templates/delivery-review.md`：可选，给人看，不作为机器门禁
- `scripts/check_spec.py`：唯一校验实现
