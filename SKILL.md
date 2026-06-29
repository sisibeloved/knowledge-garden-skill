---
name: knowledge-garden-gardener
description: 知识花园园丁。只读审计 Obsidian vault,生成提案入 Notion,轮询已批准提案 apply 到 Evergreen。Agent 当园丁,人定稿。
---

# Knowledge Garden Gardener

## 何时用
- 用户说"巡园"/"整理知识花园"/"跑审计" → `weekly-audit`
- 用户说"应用已批准的提案"/"执行审批" → `apply-approved`
- 用户说"整理 Inbox" → `triage-inbox`

## 入口动词(调 Python CLI)
所有入口经 `python -m garden_gardener.cli_entry`(或 `pip install -e .` 后的 `garden`)。

### weekly-audit
只读审计 vault(孤岛/过时/Inbox),生成提案写入 Notion「待审核提案」库。
```
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> weekly-audit
```
**不写 Evergreen**(只产提案)。

### apply-approved
轮询 Notion `status=approved` 的提案,apply 到 Evergreen + git commit(带 notion-id)+ 回写 applied_commit。
```
garden --config <vault>/_Config/gardener.config.yaml --vault <vault> --actor scheduled_run apply-approved
```
定时场景用 `--actor scheduled_run`(能力受限)。

### triage-inbox
列出 `_System/_Inbox/` 待处理 Raw。

## 红线(不可违反)
- 无 Notion `approved` 凭证绝不写 Evergreen L2+ 操作(create/update/delete/move/rename)。
- Notion 删除操作任何情况禁用。
- git pull 失败必须中止本轮,不基于脏数据跑。

## 授权模型
见 `gardener.config.yaml` 的 operations/actors/hard_disabled。风险档 L0-L3,详见 `docs/knowledge-garden-design.md` §4。
