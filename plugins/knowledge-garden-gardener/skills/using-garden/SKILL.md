---
name: using-garden
description: Use when 用户要搭建知识花园、跑巡园审计、应用已批准提案、整理 Inbox,或涉及 Obsidian 知识库 + Notion 任务库的整理与提案审批。
---

# Knowledge Garden Gardener(入口 router)

薄 router:理解用户目标,路由到 5 个入口动词(+ init)。本 plugin 是标准 CLI(`garden`),Agent 通过 shell 调用。

## 何时用

- 用户首次搭建知识花园 → `init`
- 用户说"巡园"/"整理知识花园"/"跑审计" → `weekly-audit`(含 L1 自动补链/补字段 + 周报)
- 用户说"应用已批准的提案"/"执行审批" → `apply-approved`
- 用户说"整理 Inbox"/"处理原料" → `triage-inbox`(含归类建议)
- 用户说"找孤岛"/"审查孤立笔记"/"补链" → `review-orphans`
- 用户随手记一条/"记一下"/"捕获这个" → `capture`

## 前置

`garden` 命令必须可用(已 `pip install -e .` 或通过插件市场安装)。所有命令需指定 `--vault`(vault 根目录)与 `--config`(gardener.config.yaml 路径,通常在 `<vault>/_Config/`)。

## 入口动词

### init(首次引导,可断点续跑)

引导整个知识花园:自动建 vault 骨架 + .gitignore、调 Notion 官方 REST API 建 5 个库(Projects/Tasks/Habits/待审核提案/周报)、把 database id 填回 config、生成 Obsidian 插件启用清单。

```
garden init --vault <vault> --parent-page <notion页面URL或page-id>
```

**integration token 授权是唯一人工断点**:首次跑返回 exit 3 + 指引(建 integration → 设 `NOTION_TOKEN` 环境变量 → 父页面 ··· → Connections 分享给它),完成后带 `--auth-done` 重跑续上。仅"在 Obsidian GUI 内装插件"这步因 Obsidian 官方 CLI 不支持 `plugin:install` 而需人工(启用清单已自动生成)。

### weekly-audit(只读审计 + L1 自动 apply + 周报)

只读审计 vault(孤岛/过时/Inbox),生成 L2 提案入 Notion「待审核提案」库。**不写 Evergreen 结论**(只产 L2 提案),但会**本轮自动执行 L1 低风险写**(无需 Notion 凭证):
- backfill 缺失 frontmatter(id/created_at/updated_at/status)
- 关键词补链(正文命中其它 Evergreen 标题 → 加 `[[ ]]` + links 字段)
- 英文高频词补 tags(仅 tags 为空时;中文分词待二期)

每类 L1 操作各自一个 git commit(`gardener(L1): ...`,可整类 revert),受 `batch_l1_max` 截断。最后生成周报:本地 `_System/_Reports/weekly-report.md`(始终)+ Notion 周报队列(若配置,失败降级)。

```
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> weekly-audit
```

### apply-approved(应用已批准)

轮询 Notion `status=approved` 的提案,apply 到 Evergreen + git commit(带 notion-id)+ 回写 applied_commit。

```
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> --actor scheduled_run apply-approved
```

定时/无人值守场景用 `--actor scheduled_run`(能力受限,L3 破坏性操作即便已批准也拒,需人在场)。

### triage-inbox(整理 + 归类建议)

列出 `_System/_Inbox/` 待处理 Raw,并为每条给出 next step 建议:任务候选(从 capture 降级来的)→ 提升为 Task;含 URL → 晋升 Reference;概念性内容 → 提炼 Evergreen。只读,不写。

### review-orphans(孤岛审查)

只读审计孤岛笔记(无 links + 无反向链接 + 较老),生成补链提案入 Notion「待审核提案」库(L2 link 提案)。比 weekly-audit 聚焦——只看孤岛。不写 Evergreen。

```
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> review-orphans
```

### capture(随手记捕获)

接收一段文本(手机/手动),路由到 Obsidian Raw 或 Notion Task。判定:任务语义(计划/待办/截止/deadline/todo 等)→ Task;其余 → Raw。Task 不可达(Notion 配置缺失/不可达)时降级落 Raw Inbox 并标 `type=task_candidate`(下轮 triage 提示提升)。离线也能落 Raw。

```
garden --vault <vault> capture --text "明天要完成 RAG 综述的笔记"
garden --vault <vault> capture --text "双链是 Obsidian 核心机制" --source manual
```

References/Concepts 是 Evergreen(L2 需审批),capture 是 L0 自由写——**不能直接落 Evergreen**,所以"出处/资料/不确定"一律先落 Raw,下轮 triage 提升(设计 §4.5.5)。

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
