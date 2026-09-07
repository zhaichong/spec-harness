# Spec Harness

面向 AI 编程 Agent 的开发工作流。普通功能和缺陷修复默认直接设计、实施与验证；复杂变化按需留一份简短 Spec。权限/敏感边界、外部副作用、不可逆或生产/批量变化增加针对性复查，普通业务写库不自动加码。领域细则覆盖前端、Java 后端和前后端契约；其他技术栈走主流程。

流程、档位、门禁、产物和校验命令以 `SKILL.md` 为准，不要在本文件另写一份。

## 实施与持续变更

明确要求实施且边界清楚时，Agent 完成必要设计后继续编码。普通自审检查实际 diff，只有无法查明且影响业务结果、兼容性或授权范围的问题才询问。高风险部分交付或实际操作前完成独立复查，不阻塞可独立进行的本地实现和隔离测试；真实操作在执行点核对授权，已有授权覆盖当前范围时直接沿用。

后续修改只更新受影响的设计、验收点、代码及验证，保留仍适用的证据。优先复用已有代码和项目文档；普通任务不建流程文件，简短 Spec 不强制编号或报告。只有明确需要完整追踪时才启用模板、任务映射和结构校验。构建和测试按风险与项目要求选择。详细规则以 [SKILL.md](SKILL.md) 和按需参考文件为准。

优化效果应通过实际任务的耗时、确认次数、验收和返工情况比较；结构校验通过不能证明代码质量或 token 节省比例。

## 快速开始

在 Codex、Claude Code、Grok 或 ZCode 中显式调用，然后直接描述需求：

```text
$spec-harness 给患者列表增加姓名搜索，保留现有分页和筛选条件。
```

常用示例：

```text
$spec-harness 修复设置页保存按钮重复提交，并运行最小相关测试。

$spec-harness 为订单 API 增加幂等校验，保持现有客户端兼容。

$spec-harness 给用户管理页增加批量禁用；前后端同时修改，先对齐接口字段、权限和错误码。

$spec-harness 编写客户数据迁移。先提供 dry-run、回滚和对账方案，不要执行生产写入。
```

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

> 不要长期同时保留用户级和项目级的同名 Skill。同一 Agent 不会合并它们，可能出现两个 `spec-harness`。

### 个人全局安装（Grok）

PowerShell：

```powershell
New-Item -ItemType Directory -Force 'C:\Users\<你的用户名>\.grok\skills' | Out-Null
git clone https://github.com/zhaichong/spec-harness.git 'C:\Users\<你的用户名>\.grok\skills\spec-harness'
```

若 Codex 已装在 `.agents\skills\spec-harness`，不要再维护一份会漂的副本：把 `.grok\skills\spec-harness` 做成指向前者的目录联接，或每次改完后把同一提交同步过去。

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

随后在 Codex 或 Grok 重启应用或新建任务；在 ZCode 的 **Settings → Skills** 中点击 **Refresh**。如果使用 ZCode 的 Copy 导入，请重新导入或手动替换副本。同时使用 `.agents` 和 `.grok` 两份安装时，必须同步到同一提交，不要只更新其中一份。

## 排查

- **Skill 没出现**：确认目录名是 `spec-harness`，其中直接包含 `SKILL.md`；刷新或重启应用。
- **出现两个同名 Skill**：保留项目级或用户级其中一个，避免同名重复来源。
- **没有自动触发**：在提示词开头明确写 `$spec-harness`。
- **流程过重或过轻**：写清是否涉及权限、外部副作用、不可逆或生产/批量；普通写库不应被加码。
