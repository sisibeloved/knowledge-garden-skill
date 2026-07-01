# Agent 宿主适配指南

> 本文档说明 `knowledge-garden-gardener`(以下简称 `garden`)如何接入各 Agent 宿主。
> **核心事实**:`garden` 是一个**标准 CLI**(装后提供 `garden` 命令),不是任何 Agent 的私有插件格式。因此**所有能调用 shell 命令的 Agent 宿主都能用**它。各宿主的差异只在"怎么让 Agent 去调这个命令、怎么定时"。

## 适配矩阵速览

| 宿主 | 调用方式 | 定时方式 | 适配难度 |
|---|---|---|---|
| **Claude Code** | Skill(`SKILL.md`)+ 直接 `garden` 命令 | 自身调度/手动 | ⭐ 最简单 |
| **Codex** | `codex exec` 跑 `garden` | Codex app Automations | ⭐⭐ |
| **Hermes / OpenClaw** | cron job 的 prompt 让 agent 调 `garden` | 内置 cron scheduler | ⭐⭐ |
| Cursor(未重点适配) | MCP / `.cursor/rules` | 外部 cron | 可类推 |

---

## 前置:所有宿主通用的准备

无论用哪个宿主,先完成:

1. `pip install -e .`(在仓库根目录)——让 `garden` 命令可用
2. `garden init` 引导 vault + Notion(见 README)
3. 确认 `garden --help` 能跑

每个宿主只是"换个触发 `garden` 命令的入口"。

---

## 1. Claude Code(最简单)

Claude Code 原生认 Agent Skills 规范。本仓库已提供 `SKILL.md`。

### 接入步骤

**方式 A — 作为 Skill 放进项目(推荐)**

把本仓库的 `SKILL.md` 软链或复制到你的 vault 项目下:
```bash
mkdir -p <vault>/.claude/commands
cp SKILL.md <vault>/.claude/commands/garden.md
```
之后在 Claude Code 里对它说"跑巡园"/"整理 Inbox",它会按 `SKILL.md` 调 `garden` 命令。

**方式 B — 直接当命令行工具用**

Claude Code 在 vault 目录里跑,你能直接对它说:
> "用 garden 跑一下 weekly-audit,config 在 _Config/gardener.config.yaml"

它会执行 `garden --config _Config/gardener.config.yaml --vault . weekly-audit`。

### 定时

Claude Code 没有内置定时任务。两种做法:
- **手动**:你需要时对它说"跑巡园"
- **外部 cron**:系统定时任务里 `garden ... weekly-audit`(此时不经 Claude Code,直接跑 CLI)

> 参考:[Claude Code Skills 官方文档](https://code.claude.com/docs/en/skills)、[Plugins reference](https://code.claude.com/docs/en/plugins-reference)

---

## 2. Codex(OpenAI)

Codex 有两条路:**Codex app 的 Automations**(有定时)或 **`codex exec`**(headless)。

### 方式 A — Codex app Automations(有定时,推荐用于巡园)

在 Codex app 的对话里,用自然语言描述 automation([官方 Automations 文档](https://developers.openai.com/codex/app/automations)):
> "每周日上午 9 点,在 `<vault>` 目录跑 `garden weekly-audit`(config 在 `_Config/gardener.config.yaml`),然后把结果摘要发给我。"

Codex 会把它注册成定时 automation。

### 方式 B — `codex exec`(headless,用于脚本/CI)

[headless 指南](https://www.developersdigest.tech/blog/codex-exec-ci-headless-guide):
```bash
codex exec "在 <vault> 目录运行 garden apply-approved,处理所有已批准提案" \
  --cd <vault>
```

### 注意:Codex CLI 本身无原生定时

Codex **CLI** 没有内置定时([issue #8317](https://github.com/openai/codex/issues/8317))。要定时,用 **app Automations** 或外部 cron 调 `codex exec`。

---

## 3. Hermes / OpenClaw

两者都有**内置 cron scheduler**,每个 job 存一个 prompt + schedule,到点让 agent 执行。

### Hermes

[Hermes cron 文档](https://nousresearch-hermes-agent.mintlify.app/user-guide/features/cron)。创建一个 job:
- **prompt**:`在 <vault> 目录运行 garden weekly-audit(config: _Config/gardener.config.yaml),完成后总结新增的提案。`
- **schedule**:如 `0 9 * * 0`(每周日 9 点)

### OpenClaw

[OpenClaw cron 文档](https://docs.openclaw.ai/automation/cron-jobs)。用 CLI 加 job:
```bash
openclaw cron add \
  --schedule "0 9 * * 0" \
  --prompt "在 <vault> 运行 garden weekly-audit,config 在 _Config/gardener.config.yaml"
```

### 关键架构区分(避免踩坑)

OpenClaw 明确区分两层([文档原文](https://docs.openclaw.ai/automation/cron-jobs)):
- **Gateway 级 cron** = 运维/管理员自动化面(适合 garden 这种定时巡园)
- **Agent `tools.exec`** = 运行时工具调用(不适合定时)

**garden 的定时巡园应走 Gateway 级 cron**,不要塞进 agent 的 tools.exec。

---

## 通用注意:授权 actor

定时/无人值守场景**必须**用 `--actor scheduled_run`(能力受限,L3 破坏性操作即便已批准也拒,需人在场):
```bash
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> --actor scheduled_run apply-approved
```
手动会话(你在场)用默认 `--actor manual_session`。详见 `docs/knowledge-garden-design.md` §4.3。

---

## 为什么这样设计(适配性的来源)

garden 的多 Agent 兼容性来自三个设计决策(对应 design §5.2):
1. **入口动词标准化**:`init`/`weekly-audit`/`apply-approved`/`triage-inbox`,任何宿主都能调
2. **配置随 vault Git 同步**:`gardener.config.yaml` 在 vault 里,所有宿主读同一套规则
3. **不含调度器**:定时交给宿主原生能力(Codex Automations / Hermes cron / OpenClaw cron / 外部 cron),garden 只管"被调用时做什么"

这意味着:**新增一个 Agent 宿主 = 写一段"怎么让它调 garden 命令"的说明**,不需要改 garden 代码。
