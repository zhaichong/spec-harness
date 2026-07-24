# Spec Harness

一个面向 AI 编程 Agent 的风险自适应开发工作流。它将开发任务分为 Fast、Standard 和 Strict 三档：小改动保持轻量；跨文件功能保留需求与验证追踪；数据、权限、迁移和外部操作则使用更严格的确认与安全检查。

## 它解决什么问题

- 避免 Agent 在没有理解项目和需求前直接改代码。
- 让需求、任务和验证结果可以通过 `AC-01 → T-01 → 证据` 追踪。
- 对批量数据、权限、敏感信息、迁移和外部操作增加 dry-run、回滚、对账等保护。
- 避免所有小修改都被冗长文档流程拖慢。

## 选择档位

| 档位 | 适用场景 | 默认产物 |
|---|---|---|
| Fast | 文案、小修复、局部测试、可逆且范围清晰的改动 | 聊天内范围与验证结果 |
| Standard | 普通功能、跨文件修改、一般回归风险 | Spec、任务清单、检查报告；复杂时补充方案 |
| Strict | 批量写入、迁移、权限/安全、不可逆或外部操作 | 完整 Spec、方案、任务、检查和关键事件记录 |

Skill 不会覆盖系统规则、用户明确要求或项目 `AGENTS.md`。除非用户明确授权，它不会自动合并、发布、写数据库或执行其他外部副作用操作。

## Spec 确认与编码门禁

用户把需求说清楚后，Skill 先探测项目、补齐关键问题并生成 `spec.md` 草案；这一步**不等于**允许编码。

| 档位 | 用户确认前允许做什么 | 何时可以编码 |
|---|---|---|
| Fast | 说明范围与验证方式 | 默认可直接执行；用户可要求提升档位 |
| Standard | 探测、澄清、创建/更新 Spec 草案 | 用户明确确认 Spec，或明确说“开始编码 / 直接实施 / 不需确认” |
| Strict | 探测、澄清、创建/更新 Spec 草案 | Spec 确认后；外部执行前还需再次确认 |

Standard / Strict 在确认前禁止写 `plan.md`、`tasks.md`、业务代码或迁移脚本。若用户修改需求，先更新 Spec，再次请求确认。

## 安装

本仓库根目录就是 Skill 目录。可安装为个人全局 Skill，也可放进某个项目，让团队随代码一起使用。

### 个人全局安装（Codex）

PowerShell：

```powershell
New-Item -ItemType Directory -Force 'C:\Users\<你的用户名>\.agents\skills' | Out-Null
git clone https://github.com/zhaichong/spec-harness.git 'C:\Users\<你的用户名>\.agents\skills\spec-harness'
```

安装后，Codex 在该 Windows 用户的所有项目中都可以发现 `spec-harness`。

### 项目级安装（Codex）

在项目根目录运行：

```powershell
New-Item -ItemType Directory -Force '.agents\skills' | Out-Null
git clone https://github.com/zhaichong/spec-harness.git '.agents\skills\spec-harness'
```

将 `.agents/skills/spec-harness` 提交到项目 Git 仓库后，团队成员克隆项目即可使用同一套流程。

> 不要长期同时保留用户级和项目级的同名 Skill。Codex 不会合并它们，可能在选择器中出现两个 `spec-harness`。

## 在 Codex 中使用

Codex 支持 Skill 的自动匹配和显式调用；显式调用更稳定。[Codex Skills 文档](https://learn.chatgpt.com/docs/build-skills)

### Codex 桌面端

1. 确保已安装到用户级或项目级目录。
2. 在左侧 **Skills** 中确认可以看到 **Spec Harness**；首次安装或更新后未显示时，重启 Codex。
3. 在任务输入框中输入 `$spec-harness`，选择它后继续描述需求。

示例：

```text
$spec-harness 给订单列表增加批量导出，导出失败时保留用户选择状态。
```

### Codex CLI

在项目目录启动 Codex：

```powershell
cd C:\path\to\your-project
codex
```

然后使用以下任一方式：

```text
/skills
```

在列表中选择 `spec-harness`；或者直接输入：

```text
$spec-harness 修复登录页重复提交问题，并运行最小相关测试。
```

### Codex IDE 扩展

在编辑器的 Codex Chat 面板中输入 `$`，选择 `spec-harness`，再补充需求；也可以直接输入完整提示词：

```text
$spec-harness 为当前 API 增加幂等校验，并说明兼容性影响。
```

个人全局安装对同一用户的 IDE 生效；项目级安装适合只对当前仓库生效的团队工作流。

## 在 Claude Code 中使用

Claude Code 同样支持 `SKILL.md` 格式。目录名决定斜杠命令，因此本 Skill 在 Claude Code 中的显式调用名是 `/spec-harness`；Claude 也会根据 frontmatter 的 `description` 自动匹配任务。[Claude Code Skills 文档](https://code.claude.com/docs/en/skills)

### 个人全局安装

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force 'C:\Users\<你的用户名>\.claude\skills' | Out-Null
git clone https://github.com/zhaichong/spec-harness.git 'C:\Users\<你的用户名>\.claude\skills\spec-harness'
```

macOS 或 Linux：

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/zhaichong/spec-harness.git ~/.claude/skills/spec-harness
```

个人级安装对该用户的所有 Claude Code 项目可用。

### 项目级安装

在项目根目录运行：

```bash
mkdir -p .claude/skills
git clone https://github.com/zhaichong/spec-harness.git .claude/skills/spec-harness
```

将 `.claude/skills/spec-harness` 提交到项目 Git 仓库后，团队成员和 Claude Code cloud session 都可以使用它。

### 调用

在项目目录启动 Claude Code：

```bash
claude
```

然后输入：

```text
/spec-harness 为订单 API 增加幂等校验，并说明兼容性影响。
```

也可以直接描述符合 Skill 范围的任务，让 Claude 自动选择：

```text
为客户数据导入增加 dry-run、失败记录和恢复方案。
```

更新已有 Skill 时，Claude Code 会监控个人级和项目级 Skill 目录；如果在当前会话开始后才新建了顶层 `skills` 目录，请重启 Claude Code。

## 在 ZCode Agent 中使用

ZCode 支持直接导入其他 Agent 的 Skill。优先使用导入功能，因为它可以复用本机的 Codex 安装目录。[ZCode Skill 文档](https://zcode.z.ai/en/docs/skill)

### 从 Codex 导入

1. 打开 **Settings → Skills**。
2. 点击右上角 **Import**。
3. 在外部 Agent 列表中找到 Codex 和 `spec-harness`。
4. 选择导入模式：
   - **Symlink**：与 Codex 版本保持同步；不要移动或删除原始目录。
   - **Copy**：独立副本；后续需要手动更新。
5. 选择 **Global**（所有工作区可用）或 **Project**（当前项目可用）。
6. 导入后点击 **Refresh**，确认 Skill 已启用。

### 直接安装到 ZCode

如果不想经过 Codex，可直接克隆到 ZCode 的用户级目录：

```powershell
New-Item -ItemType Directory -Force 'C:\Users\<你的用户名>\.zcode\skills' | Out-Null
git clone https://github.com/zhaichong/spec-harness.git 'C:\Users\<你的用户名>\.zcode\skills\spec-harness'
```

随后在 **Settings → Skills** 点击 **Refresh** 并启用它。

### 调用

在 ZCode Agent 聊天框输入 `$` 并选择 `spec-harness`，或直接输入：

```text
$spec-harness 为客户数据导入增加预览、dry-run 和失败记录。
```

ZCode 会将该 Skill 传给当前 Agent，使其按工作流执行。

## 常用提示词

```text
$spec-harness 修复设置页按钮文案，并运行已有相关测试。

$spec-harness 给用户管理页增加批量禁用；需要明确权限、审计和回滚策略。

$spec-harness 编写数据迁移脚本，将重复客户合并。先生成 dry-run 和恢复方案，不要执行生产写入。
```

## 更新

如果使用 Git 克隆安装，在对应目录执行：

```powershell
git pull --ff-only
```

随后在 Codex 重启应用或新建任务；在 ZCode 的 **Settings → Skills** 中点击 **Refresh**。如果使用 ZCode 的 Copy 导入，请重新导入或手动替换副本。

## 排查

- **Skill 没出现**：确认目录名是 `spec-harness`，其中直接包含 `SKILL.md`；刷新或重启应用。
- **出现两个同名 Skill**：保留项目级或用户级其中一个，避免同名重复来源。
- **没有自动触发**：在提示词开头明确写 `$spec-harness`。
- **流程过重或过轻**：在需求中写清风险和范围；Skill 会在 Fast、Standard、Strict 中选择合适档位。
