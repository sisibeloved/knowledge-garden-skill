---
name: using-garden
description: Use when 用户要搭建知识花园、跑巡园审计、应用已批准提案、整理 Inbox,或涉及 Obsidian 知识库 + Notion 任务库的整理与提案审批。
---

# Knowledge Garden Gardener(入口 router)

薄 router:理解用户目标,路由到 4 个入口动词。本 plugin 是标准 CLI(`garden`),Agent 通过 shell 调用。

## 何时用

- 用户首次搭建知识花园 → `init`
- 用户说"巡园"/"整理知识花园"/"跑审计"/"找孤岛" → `weekly-audit`
- 用户说"应用已批准的提案"/"执行审批" → `apply-approved`
- 用户说"整理 Inbox"/"处理原料" → `triage-inbox`

## 前置

`garden` 命令必须可用(已 `pip install -e .` 或通过插件市场安装)。所有命令需指定 `--vault`(vault 根目录)与 `--config`(gardener.config.yaml 路径,通常在 `<vault>/_Config/`)。

## 入口动词

### init(首次引导,可断点续跑)

引导整个知识花园:自动建 vault 骨架 + .gitignore、调 Notion MCP 建 4 个库(Projects/Tasks/Habits/待审核提案)、把 database id 填回 config、生成 Obsidian 插件启用清单。

```
garden init --vault <vault> --mcp-endpoint <endpoint> --parent-page <notion-page-id>
```

**OAuth 是唯一人工断点**:首次跑返回 exit 3 + 指引,完成 Notion OAuth 后带 `--oauth-done` 重跑续上。仅"在 Obsidian GUI 内装插件"这步因 Obsidian 官方 CLI 不支持 `plugin:install` 而需人工(启用清单已自动生成)。

### weekly-audit(只读审计)

只读审计 vault(孤岛/过时/Inbox),生成提案写入 Notion「待审核提案」库。**不写 Evergreen**(只产提案)。

```
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> weekly-audit
```

### apply-approved(应用已批准)

轮询 Notion `status=approved` 的提案,apply 到 Evergreen + git commit(带 notion-id)+ 回写 applied_commit。

```
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> --actor scheduled_run apply-approved
```

定时/无人值守场景用 `--actor scheduled_run`(能力受限,L3 破坏性操作即便已批准也拒,需人在场)。

### triage-inbox

列出 `_System/_Inbox/` 待处理 Raw。

## 红线(不可违反)

1. **无 Notion `approved` 凭证绝不写 Evergreen L2+ 操作**(create/update/delete/move/rename)。
2. **Notion 删除操作任何情况禁用**(用归档代替)。
3. **git pull 失败必须中止本轮**,不基于脏数据跑。
4. **结论只存 Obsidian**,Notion 只链接,不双向复制内容。

## 授权模型(L0-L3)

| 档 | 操作 | 路径 |
|---|---|---|
| 🟢 L0 | 追加 Raw/Drafts/Reports | 直接写 |
| 🟡 L1 | 补 frontmatter/双链/标签 | 自动写 + commit |
| 🟠 L2 | 新建 Evergreen/改结论 | Notion 提案 → approve → apply |
| 🔴 L3 | 删/移/重命名 | 提案 → approve → 二次确认 → apply |

详见仓库根 `docs/knowledge-garden-design.md` §4。

## 在不同 Agent 宿主里怎么调

本 plugin 是标准 CLI(`garden`),不是任何 Agent 的私有插件。各宿主只是换触发入口:
- **Claude Code**:通过插件市场安装后,Agent 按本 SKILL.md 自动加载;或直接让 Claude 跑 `garden` 命令
- **Codex**:用 `codex exec "在 <vault> 跑 garden weekly-audit" --cd <vault>`,或 Codex app Automations 定时
- **Hermes / OpenClaw**:用内置 cron scheduler,job 的 prompt 让 agent 调 `garden`
- 其它能调 shell 的宿主:直接 `garden <verb> ...`

**详细接入步骤见仓库根 `docs/agent-adapters.md`。**
