# Agent 宿主适配指南

> 本文档说明 `knowledge-garden-gardener`(以下简称 `garden`)如何接入各 Agent 宿主。
> **核心事实**:`garden` 是一个**标准 CLI**,4 个宿主的接入方式各不相同——其中 OpenClaw 几乎免费兼容,Claude/Codex 走插件市场,Hermes 需薄 plugin 包装。

## 适配矩阵速览

| 宿主 | 接入方式 | 我们的工作 | 难度 |
|---|---|---|---|
| **Claude Code** | 插件市场 + Skill | `.claude-plugin/plugin.json` + `skills/` | ⭐ 已完成 |
| **Codex** | 插件市场 + Skill | `.codex-plugin/plugin.json` + `skills/` | ⭐ 已完成 |
| **OpenClaw** | **Plugin Bundles**(原生兼容 Claude/Codex 格式) | `openclaw.plugin.json`(让 native 识别更稳) | ⭐ 几乎免费 |
| **Hermes** | 原生 Python plugin | `hermes-plugin/garden/` 薄包装(4 tool + 1 slash command) | ⭐⭐ 已完成 |

---

## 前置:所有宿主通用

```bash
pip install -e .  # 让 garden 命令可用
garden init --vault ./Garden --parent-page <notion页面URL或page-id>
```

---

## 1. Claude Code

```text
/plugin marketplace add https://github.com/sisibeloved/knowledge-garden-skill
/plugin install knowledge-garden-gardener
```
安装后 Agent 通过 `using-garden` skill 自动加载。也可直接让 Claude 跑 `garden` 命令。无内置定时,用手动或外部 cron。([Skills 文档](https://code.claude.com/docs/en/skills))

## 2. Codex

```bash
codex plugin marketplace add https://github.com/sisibeloved/knowledge-garden-skill
codex plugin add knowledge-garden-gardener@knowledge-garden
```
定时用 Codex app Automations([官方](https://developers.openai.com/codex/app/automations))或 `codex exec`([headless](https://www.developersdigest.tech/blog/codex-exec-ci-headless-guide))。注意:Codex CLI 无原生定时([issue #8317](https://github.com/openai/codex/issues/8317))。

## 3. OpenClaw(几乎免费)

OpenClaw 的 [Plugin Bundles](https://docs.openclaw.ai/plugins/bundles)**原生支持把 Claude/Codex 插件当 bundle 安装**——它会自动检测 `.claude-plugin/plugin.json`,把 `skills/` 当 skill 加载。我们额外提供了 `openclaw.plugin.json`(native manifest)让识别更稳。

```bash
openclaw plugins install knowledge-garden-gardener@knowledge-garden
# 或从本地
openclaw plugins install ./plugins/knowledge-garden-gardener
```

**关键架构区分**:OpenClaw 区分 [Gateway 级 cron](https://docs.openclaw.ai/automation/cron-jobs)(运维面,适合 garden 定时巡园)和 agent `tools.exec`(运行时)。garden 的定时巡园走 Gateway 级 cron:
```bash
openclaw cron add --schedule "0 9 * * 0" \
  --prompt "在 <vault> 运行 garden weekly-audit"
```

## 4. Hermes(薄 plugin 包装)

Hermes 有原生 Python plugin 系统(`plugin.yaml` + `register(ctx)`)。我们提供 `hermes-plugin/garden/` 薄包装,把 garden 4 个入口注册成 **4 个 tool**(LLM 自动调用)+ **`hermes garden` CLI 子命令**(用户手动)。

**安装**:把 `hermes-plugin/garden/` 复制到 Hermes plugins 目录(注意:不是 `~/.hermes/plugins/`,而是 `hermes plugins install` 用的真实目录,可用 `python -c "from hermes_cli.plugins_cmd import _plugins_dir; print(_plugins_dir())"` 查询;Windows 上通常是 `C:\Users\<用户>\AppData\Local\hermes\plugins`):
```bash
PLUGINS_DIR=$(python -c "from hermes_cli.plugins_cmd import _plugins_dir; print(_plugins_dir())")
mkdir -p "$PLUGINS_DIR/garden"
cp -r plugins/knowledge-garden-gardener/hermes-plugin/garden/* "$PLUGINS_DIR/garden/"
hermes plugins enable garden
hermes  # 启动后 garden tool 和 hermes garden 子命令可用
```

**使用**:
- LLM 自主:`garden_weekly_audit` 等 tool(模型按 schema 决定何时调)
- 手动:`hermes garden weekly-audit --vault ./Garden`、`hermes garden init --parent-page <pp> [--auth-done]`

**定时**:用 Hermes 内置 [cron scheduler](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron),job 的 prompt 让 agent 调 garden tool。([Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin))

**本机验证记录(v0.18.0)**:`register(ctx)` 成功注册 4 tool + 1 cli command;`hermes garden --help` 显示 4 个子命令;`hermes plugins list` 显示 `garden / enabled / 0.3.0 / user`。

---

## 通用注意:授权 actor

定时/无人值守场景**必须**用 `--actor scheduled_run`(能力受限,L3 破坏性操作即便已批准也拒):
```bash
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> --actor scheduled_run apply-approved
```

## 为什么 OpenClaw 几乎免费

OpenClaw 的 bundle 机制设计上就兼容三大生态(Claude/Codex/Cursor)。我们已有的 `.claude-plugin/plugin.json` + `.codex-plugin/plugin.json` 让 OpenClaw 能直接识别——**不需要写 OpenClaw 专属逻辑**,只需补一个 native manifest 让安装更顺滑。这是生态兼容的红利,不是我们额外做的工程。

## 为什么 Hermes 需要薄包装

Hermes 不复用 Claude/Codex 格式,有自己的 `plugin.yaml` + `register(ctx)` + tool schema 系统。但它就是普通 Python 包,我们的包装只是把 4 个 `garden` 子命令包成 tool/slash command,内部 `subprocess` 调 garden CLI——**核心逻辑仍只在 garden CLI 一处**,Hermes 包装不重复实现业务。
