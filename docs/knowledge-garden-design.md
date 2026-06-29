# 知识花园详细设计方案

> **状态**:设计已确认,待审阅
> **日期**:2026-06-28
> **作者**:陆尘 × ZCode(协作设计)
> **核心理念**:Agent 当"园丁",不当作者。Agent 负责搜、整理、补链接、生成草稿、发现孤岛与矛盾;真正进入长期知识库的结论必须经人确认。

---

## 0. 文档导航

| 章节 | 内容 |
|---|---|
| [§1 总体架构与分层](#1-总体架构与分层) | 三层结构、角色边界、多机同步、一期/二期边界 |
| [§2 园丁 Plugin 与授权交互逻辑](#2-园丁-plugin-与授权交互逻辑) | 三层写入、风险分级、异步审批循环 |
| [§3 数据模型与目录结构](#3-数据模型与目录结构) | vault 目录、frontmatter schema、Bases 视图、Git 策略 |
| [§4 权限与分级信任模型](#4-权限与分级信任模型) | 三维度授权(WHO×WHERE×WHAT)、Notion/Obsidian 边界 |
| [§5 调度、降级与人机交互](#5-调度降级与人机交互) | 异步循环、各 Agent 调度、降级路径、失败处理 |
| [§6 落地路线图](#6-落地路线图) | 三阶段、技术风险、成功标准、YAGNI 边界 |
| [附录 A:决策记录](#附录-a决策记录) | 关键设计决策及理由 |
| [附录 B:术语表](#附录-b术语表) | |

---

## 1. 总体架构与分层

### 1.1 一句话定义

一个名为 `knowledge-garden-gardener` 的**复合 Agent Plugin**,扮演"园丁"角色:负责搜、整理、补链接、生成草稿、发现孤岛与矛盾。它**只读审计 + 生成提案**,所有进入长期库的结论必须经人确认。它复用社区现成 skill(kepano/obsidian-skills、Notion 官方 MCP、Smart Connections MCP)作为"手脚",自己只做"大脑(决策 + 审核门)"。

### 1.2 工具职责划分(已论证的双工具)

经论证,Obsidian 与 Notion 共存合理,职责正交:

| 工具 | 本质定位 | 不可替代的能力 |
|---|---|---|
| **Obsidian** | "思考与沉淀"工作台 | 纯 markdown 资产、可 Git 管理、可迁移、双链图谱、本地离线 |
| **Notion** | "执行与跟踪 + 人机交互"工作台 | 富文档+任务同体、移动端原生同步、结构化视图流转(看板/日历/时间线) |

> **边界口诀**:Obsidian 管"知道什么、为什么"(知识结论);Notion 管"做什么、做到哪了"(执行跟踪)以及"在哪交互"(审批/提醒)。

**回退条件**:若未来场景变轻(如工作项目已转入专业 tracker),可砍掉 Notion,回退到 Obsidian 单库。此设计保留降级路径。

### 1.3 三层知识结构

| 层 | 位置 | 内容 | 谁能写 |
|---|---|---|---|
| **Raw(原料区)** | Obsidian `_Inbox/`、`_AgentDrafts/` | 网页剪藏、会议纪要、PDF 摘要、Agent 草稿 | Agent 可追加;人工确认后才晋升 |
| **Evergreen(长期花园)** | Obsidian `Concepts/`、`Notes/`、`References/`、`Index/` | 人工授权后定稿的概念笔记 | **Agent 经授权写** / 人;授权模型见 §2 |
| **Project(执行区)** | Notion Projects/Tasks/Habits | 项目状态、任务、阅读计划、生活待办 | 人工为主;Agent 经 Notion MCP 写"待审核"项 |

**核心不变量**:Obsidian Evergreen 是**唯一知识真相源**;Notion Project 只**链接回** Evergreen,不复制结论。

### 1.4 多机同步模型(Git)

```
   机器A / 机器B / 机器C  (日常编辑节点)
        │  Obsidian + 插件 + Obsidian-Git 插件
        ▼
   ┌──────── Git 私仓(GitHub private 等)────────┐
   │   .md 文件多机一致;完整版本史;手动/插件解冲突 │
   └───────────────────────┬────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                          ▼
   [编辑节点] Obsidian 开               [调度节点] 按各 Agent 调度运行
   园丁手动调用 → CLI/IPC               filesystem 直写 .md(默认降级)
                                     + 提案入 Notion → 手机批 → 下轮 apply
```

**两类节点**:
- **编辑节点**:日常用机,Obsidian 开着,CLI/IPC 可用,手动让园丁整理。
- **调度节点**:按各 Agent 宿主调度(Codex automation / Hermes 定时 / Claude Code 等)触发 plugin,默认走 filesystem 直写,不要求 Obsidian 常驻。

**同步选型**:Git(Obsidian-Git 插件 + 私仓)。理由:免费、完整版本史、与授权模型叠加成"草稿晋升 = 一次 commit"。

> **约束**:因选 Git(非 Obsidian Sync),调度节点**不能用 Obsidian Headless**(它只连 Obsidian Sync)。调度节点默认走 filesystem 直写,双链/Bases 索引等 Obsidian 下次打开重算。

**冲突面已压到最低**(设计红利):
- 园丁只追加 Raw/Drafts,追加几乎不冲突
- Evergreen 由 Agent 经授权写,人不会两机同时改同一条
- Git 版本史 = 草稿晋升的可审计记录

### 1.5 三个角色的边界

| 角色 | 权限 | 类比 |
|---|---|---|
| **园丁 Plugin(大脑)** | 全库只读审计 + 生成提案 + 应用已授权写 | 园丁巡视,提建议,按授权动花 |
| **现成 skills(手脚)** | 受园丁委托执行具体读写 | 园丁的锄头、剪刀 |
| **人(园主)** | 唯一的授权来源(在 Notion 审批) | 只有园主能授权移栽 |

### 1.6 一期 / 二期边界

- **一期**:复合 Plugin + Obsidian CLI(kepano)+ Smart Connections MCP + Notion 官方 MCP + Git 同步 + 异步审批循环 + 定时巡园。
- **二期**:接入 Khoj 作为只读跨库语义问答层,plugin 可调用它生成更智能的周报;A-Mem 建链算法做智能补链。

---

## 2. 园丁 Plugin 与授权交互逻辑

### 2.1 核心思想:三层写入,授权下沉

把"写 Evergreen"拆成三层,每层对应不同授权深度。**关键洞察:授权不是"人手敲",而是"人在 Notion 点 approve,plugin 落盘"。人始终是审批者,不是打字员。**

```
Raw 层         →  Agent 自由追加(默认允许,无授权)
低风险 Evergreen →  Agent 自动写 + 留 commit(隐式授权,可回滚)
高风险 Evergreen →  Agent 生成提案入 Notion → 人手机批 → 下轮 Agent 落盘(显式授权)
```

### 2.2 操作风险分级表(授权依据)

每个园丁操作按风险归入一档,决定走自动还是审批。此表是**单一事实源**,存于 `gardener.config.yaml`(§4.6)可调:

| 风险档 | 操作类型 | 执行路径 | 示例 |
|---|---|---|---|
| 🟢 L0 自由 | 追加 Raw/Drafts/Reports | 直接写 | 网页剪藏、会议纪要、Agent 草稿 |
| 🟡 L1 自动+留痕 | **修改**已有笔记的元数据/链接 | Agent 直接写 Evergreen,单独 commit | 补 frontmatter 字段、加双链 `[[ ]]`、加标签 |
| 🟠 L2 需审批 | **新增** Evergreen / **修改正文结论** | 提案入 Notion → approve → 下轮 apply | 新建概念笔记、修订观点、合并两条笔记 |
| 🔴 L3 需审批+二次确认 | **删除/移动/重命名** | 提案入 Notion → approve → 二次确认 → apply | 删除过时笔记、移动到另一主题、重命名(影响双链) |

**L3 二次确认内容**(防"热心改园艺布局"):
- 重命名/移动:列出**所有受影响的双链**(悬空清单),要求人确认"同意一并更新这些链接"或"放弃"
- 删除:列出**所有反向链接**,要求人确认"这些引用会变悬空,确认删除?"

**白名单可配置**:信任熟了可降档放权,出错可升档收紧(§4.6)。

### 2.3 异步审批循环(核心交互模型)

因审批放 Notion(移动端),流程从"现场 approve"变为"提案入 Notion → 手机批 → 下轮 apply":

```
[第 N 轮 Agent 运行 — 审计]
  1. 读 Obsidian(只读审计:孤岛/冲突/待复核/Inbox 新增)
  2. 读 Notion(项目状态,交互③)
  3. 生成提案 → 写入 Notion「待审核提案」库(diff/sources/confidence/risk)
  4. Notion 自动给手机发提醒:"N 条提案待审"
  5. L1 低风险本轮自动 apply + 留 commit(周报抽查可 revert)
       │
       ▼  你在手机上随时
[人 — 移动端审批]
  6. 看 Notion 提案(按风险档分组视图)
  7. approve / reject(改 Status 字段)
       │
       ▼
[第 N+1 轮 Agent 运行 — 应用]
  8. 轮询 Notion,取出 status=approved 的提案
  9. apply 到 Obsidian Evergreen(此时才写知识库)
 10. git commit -m "gardener(L2): create X (approved <notion-id>)"
 11. 回写 Notion 提案:status=已应用, applied_commit=<hash>
```

**此模型好处**:移动端审批、异步不占桌面时间、多 Agent 兼容(每轮不分是谁触发)、知识仍只在 Obsidian/Git。
**代价**:Evergreen 更新有最多"一轮"延迟。

### 2.4 调用契约(plugin 与现成 skills 的分工)

| 园丁要做什么 | 委托给 | 契约 |
|---|---|---|
| 读/扫描 vault | kepano/obsidian-skills(编辑节点) 或 filesystem(调度节点) | 统一抽象 `vault.read(path/glob/query)` |
| 语义检索"相关笔记" | Smart Connections MCP | `sc.search(query) → [notes]` |
| 跨库查 Notion 项目 | Notion 官方 MCP | `notion.search/query` |
| 写 Raw/Drafts | filesystem | `vault.append(draft)` |
| 写 Evergreen(L1 自动) | filesystem + git commit | `vault.write() + commit` |
| 写 Evergreen(L2/L3 审批后) | filesystem + git commit | 同上,但前置 Notion `approved` 凭证 |
| 创建提案 | Notion MCP | `notion.create_proposal(...)` |
| 轮询已批提案 | Notion MCP | `notion.poll_approved()` |

**降级透明**:plugin 内有 `vault.read/write` 抽象层,编辑节点走 CLI、调度节点走 filesystem,业务逻辑不感知差异(§5.3)。

---

## 3. 数据模型与目录结构

### 3.1 Vault 顶层目录

```
Garden/                              ← Obsidian vault 根
├── _System/                         ← 园丁系统区(下划线=不进图谱主体)
│   ├── _Inbox/                      Raw 层:剪藏/会议/PDF 摘要落地点
│   ├── _AgentDrafts/                Agent 生成的草稿(L0)
│   ├── _PendingProposals/           Notion 不可达时,提案临时暂存
│   ├── _Reports/                    周报/孤岛报告/冲突报告/审计工作稿
│   └── _Archive/                    已应用提案的本地副本(供离线查阅)
│
├── Concepts/                        Evergreen:概念笔记(原子化结论)
├── Notes/                           Evergreen:长文/读书笔记/深度总结
├── References/                      Evergreen:文献/出处/可引用资料卡
├── Index/                           Evergreen:MOC(地图笔记)、入口页
│
├── _Templates/                      模板(各层共用)
│   ├── inbox-raw.md
│   ├── concept-evergreen.md
│   └── weekly-report.md
│
├── _Config/                         园丁配置
│   ├── gardener.config.yaml         风险分级表/白名单/阈值
│   └── CHANGELOG-gardener.md        园丁操作日志
│
└── .obsidian/                       Obsidian 配置(仅同步必要部分,见 §3.6)
```

**命名约定**:`_` 开头 = 系统区(不进 Evergreen 图谱、不参与"真相源"),园丁对这些区有较高写权限。

> **修订说明**:原设计中 `_Proposals/` 曾位于 Obsidian。经确认(审批放 Notion 移动端),提案改存 **Notion「待审核提案」库**。Obsidian 仅保留 `_PendingProposals/`(Notion 不可达时的临时暂存)与 `_Archive/`(已应用提案本地副本)。

### 3.2 三层与目录映射

| 层 | 目录 | 谁写 | 风险档 |
|---|---|---|---|
| Raw | `_Inbox/`、`_AgentDrafts/` | Agent/剪藏/人随手 | L0 自由 |
| 提案 | **Notion「待审核提案」库** | Agent 生成 / 人审 | (审批载体) |
| Evergreen | `Concepts/`、`Notes/`、`References/`、`Index/` | Agent 经授权写 / 人 | L1 自动 / L2 审批 / L3 二次确认 |
| Project | **Notion**(Projects/Tasks/Habits) | Agent 经 MCP / 人 | 见 §4.5 |
| 报告 | `_Reports/` | Agent 生成 | L0 自由 |

### 3.3 Frontmatter Schema

#### Raw 层
```yaml
---
id: raw-2026-06-25-a3f1            # 唯一 id(时间+短hash)
type: raw                          # raw | draft
source: web                        # web | meeting | pdf | agent | manual
source_url:                        # 原始出处
captured_at: 2026-06-25T14:30:00+08:00
status: inbox                      # inbox | processing | processed
generated_by:                      # 若 agent 生成,标注 skill+版本
needs_review: false
tags: [RAG, 检索]
---
```

#### Evergreen 层
```yaml
---
id: concept-rag-retrieval
type: concept                      # concept | note | reference | moc
title: RAG 检索的核心权衡
created_at: 2026-06-25T14:30:00+08:00
updated_at: 2026-06-25T14:30:00+08:00
status: evergreen
sources: [raw-2026-06-25-a3f1]     # ← 溯源到 Raw id
confidence: 0.82
last_reviewed_at: 2026-06-25
aliases: [Retrieval-Augmented Generation]
tags: [RAG, 检索]
links: [[检索系统]]              # 显式双链
notion_ref:                        # 关联 Notion Project 时填 page id
---
```

> **`sources` + `notion_ref` 是双真相源隔离的关键**:Evergreen 通过 `sources` 溯源到 Raw,通过 `notion_ref` 链接到 Notion——**链接,不复制内容**。

#### Notion「待审核提案」库字段
```yaml
proposal_id: 2026-06-25-001
created_at: 2026-06-25T14:30:00+08:00
status: pending                    # pending | approved | rejected | applied | reverted
risk: L2
action: create                     # create | update | delete | move | rename | link
target: Concepts/RAG检索.md
sources: [raw-2026-06-25-a3f1]
confidence: 0.82
generated_by: knowledge-garden-gardener v0.1
diff: |-                          # 变更内容(+/- 行)
review_decision:                  # 人批准时填
reviewed_at:
applied_commit:                   # 落盘后的 git commit hash
```

### 3.4 双链与标签策略

| 机制 | 用途 | 园丁用法 |
|---|---|---|
| **双链 `[[ ]]`** | 结构关联 | L1 自动补链:扫描正文关键词匹配 Evergreen 标题 → 加 `[[ ]]` |
| **`links` 字段** | frontmatter 显式关联 | 孤立笔记判定依据 |
| **`tags`** | 跨笔记聚类 | 找"同 tag 下结论冲突"的笔记对 |
| **`sources`/`notion_ref`** | 跨层/跨库溯源 | 周报反溯"这条结论来自哪" |

**孤立笔记定义**(写入 config):无 `links` 值 + 无反向链接 + 已存在 > 7 天 → 进入孤岛报告,生成补链提案。

### 3.5 Bases 视图(Evergreen 侧,只读派生)

| Base | 过滤 | 用途 |
|---|---|---|
| `Inbox 待处理` | type=raw, status=inbox | Raw 晋升队列 |
| `孤岛笔记` | 无 links 且无 backlinks | 园丁关注 |
| `过期待复核` | last_reviewed_at < 今天-90天 | 结论可能过时 |
| `本周新增 Evergreen` | created_at 在本周 | 周报数据源 |

> 审批面在 Notion(看板视图按 risk 分组),不在 Obsidian Bases。

### 3.6 Git 同步策略

| 内容 | 进 Git? | 原因 |
|---|---|---|
| 所有 `.md`(Raw/Evergreen/Reports) | ✅ | 核心资产 |
| `_Templates/`、`_Config/` | ✅ | 多机一致 |
| `.obsidian/`(部分) | ⚠️ | 仅 `app.json`/插件配置/模板;不同步 workspace/cache |
| `.obsidian/workspace*.json`、`*.cache` | ❌ | `.gitignore`,每机本地 |

**`.gitignore` 关键项**:
```
.obsidian/workspace*.json
.obsidian/plugins/*/data.json
*.cache
_Trash/
```

**Commit 规范**(与授权模型挂钩):
```
gardener(L0): append draft raw-xxx
gardener(L1): backfill source on 12 notes
gardener(L2): create Concepts/RAG检索 (approved <notion-id>)
manual: edit Concepts/RAG检索
```
**notion-id 进 commit message = 授权凭证可追溯**(§5.7 跨系统审计链)。

---

## 4. 权限与分级信任模型

### 4.1 三维度授权模型

```
                ┌─────────────────────────────────┐
                │      操作目标区域 (WHERE)        │
                │  Raw  Evergreen  Notion  Reports │
                └────────┬────────────────────────┘
                         │
   操作主体 (WHO)        ▼        操作风险 (WHAT)
   ┌──────────┐    ┌──────────┐
   │ 手动会话  │───▶│ L0~L3     │ ──▶ 允许/审批/拒绝
   │ 定时/调度 │    │ (见 §2.2)│
   │ 人        │    └──────────┘
   └──────────┘
```

规则:WHO × WHERE × WHAT 查表 → 允许 / 需审批 / 拒绝。

### 4.2 WHERE 维度:基线最小权限

| 区域 | 默认读 | 默认写 | 默认删/移 |
|---|---|---|---|
| `_Inbox/`、`_AgentDrafts/` (Raw) | ✅ | ✅ 追加/改 | ❌ |
| `_Reports/` | ✅ | ✅ 生成 | ✅ 自己生成的 |
| `_Archive/` | ✅ | ⚠️ 仅归档动作 | ❌ |
| `Concepts/`等 (Evergreen) | ✅ | 🔒 按风险档(§2.2) | 🔒 L3+二次确认 |
| Notion Project/Task | ✅ search/fetch | 🔒 待审核态 | ❌(归档代替删除) |

**红线**:plugin **永不**直接删除/移动 Evergreen,除非走完 L3 审批 + 二次确认。删除/移动原语默认禁用,审批通过后才临时解锁单次执行。

### 4.3 WHO 维度:主体能力上限

| 操作主体 | 可执行最大风险档 | 原因 |
|---|---|---|
| **手动会话**(你在 Agent 里交互) | L0~L3 全可,但 L2/L3 需 Notion approve | 你在场 |
| **定时/调度轮**(无人值守) | L0 + L1 + **应用已 Notion approved 的 L2/L3** | 见下 |
| **人** | 任意 | 园主 |

> **关键修订**(原规则"定时仅 L0"已放宽):定时轮允许应用 Notion 已 approved 的提案。新原则:**禁止的是"无授权的写入源头",不是"已授权写入的执行"**。授权来源 = Notion `status=approved`。plugin 只认此凭证。
>
> **例外**:config 可关闭定时轮的 L1 自动写(若想更保守),默认开启。

### 4.4 WHAT 维度:风险档细则

| 档 | 触发条件 | 执行路径 | 留痕 | 回滚 |
|---|---|---|---|---|
| 🟢 L0 | 追加 Raw/Drafts/Reports | 直接写 | git commit | revert/删文件 |
| 🟡 L1 | 改 Evergreen 的 frontmatter/双链/标签/typo | 自动写 + 单 commit | commit 标 L1 | git revert |
| 🟠 L2 | 新增 Evergreen / 改正文结论 / 合并 | Notion 提案 → approve → apply + commit | notion-id 进 commit | revert(提案标 reverted) |
| 🔴 L3 | 删除/移动/重命名 | Notion 提案 → approve → 二次确认 → apply + commit | notion-id + 确认记录 | revert(链接修复需额外处理) |

### 4.5 Notion / Obsidian 边界与交互

#### 4.5.1 职责边界(单一事实源)

| 信息类型 | 真相源 | 判定理由 |
|---|---|---|
| 概念结论/知识原子 | **Obsidian Evergreen** | 长期、原子化、需双链图谱 |
| 参考资料/出处 | **Obsidian References** | 被知识引用的原料 |
| 原始捕获 | **Obsidian Raw** | 待提炼素材 |
| 阅读/学习计划(进度) | **Notion** | 有进度跟踪、状态流转 |
| 工作/职业项目 | **Notion** | 需状态共享、协作 |
| 生活待办/习惯 | **Notion** | 轻量、时效、重复性 |

**反例(必须避免)**:一本书的结论只存 Obsidian,Notion 只存"读到第几章";工作任务的知识背景用 `notion_ref` 链接回 Evergreen,不重写。

**判定树**:同一主题信息,按"做什么/做到哪了"→ Notion;"知道什么/结论"→ Obsidian;"出处"→ References。

#### 4.5.2 Notion 数据库结构(基于三类 Project)

```
Projects (项目库)
  字段: Name, Type[阅读/工作/生活], Status[计划中/进行中/完成/搁置],
        Start, Due, notion_ref(→Obsidian链接), Owner
        │ relation (1对多)
        ▼
Tasks (任务库)
  字段: Name, Project→, Status[待办/进行中/完成], Due, Priority,
        source_ref(→Obsidian链接,可选)

Habits (习惯库)  ← 生活待办/打卡
  字段: Name, Type[习惯/待办], Frequency[每日/每周],
        Streak, Last_done, History
```

**字段原则**:Notion 只存结构化跟踪字段(状态/进度/日期/关联),**不存知识结论正文**;涉及知识处用 `obsidian://` 链接(点开跳回 Obsidian)。

#### 4.5.3 四个交互方向

| # | 方向 | 内容 | 触发 | 频率 |
|---|---|---|---|---|
| ① | Obsidian→Notion | `notion_ref` 链接(不含结论) | 人填/园丁提案建议 | Evergreen 变更时 |
| ② | Notion→Obsidian | 点链接取结论(不复制) | 人跳转/园丁周报 | 推进任务时 |
| ③ | Notion→园丁 | 只读查 Project 状态 | 定时巡园 | 每周 |
| ④ | 园丁→Notion | 创建待审核 Task / 提案 | 手动会话 | 按需 |

**核心不变量**:没有任何知识结论被双向复制;跨库流动的都是"链接"或"只读查询"。

#### 4.5.4 `obsidian://` 双向链接

```
# Notion Task 指向 Obsidian Evergreen
source_ref: obsidian://open?vault=Garden&file=Concepts/RAG%E6%A3%80%E7%B4%A2

# Obsidian Evergreen 指向 Notion Project
notion_ref: https://notion.so/<workspace>/<page-id>
```
两端均可点击跳转,让"链接不复制"在体验上接近无缝。

#### 4.5.5 归类判定器(plugin 内置)

```
新信息进来:
├─ "做什么/做到哪了/计划/任务/进度" → Notion(Project/Habit)
├─ "知道什么/结论/概念"             → Obsidian Raw → (提炼) → Evergreen
├─ "出处/资料"                      → Obsidian References
└─ 不确定                           → 默认 Obsidian Raw(安全落点),人后续归类
```

### 4.6 `gardener.config.yaml`(信任模型配置化)

所有分级集中配置,信任可调:

```yaml
version: 0.1

risk_levels:
  L0: { auto: true,  needs_review: false, confirm: false }
  L1: { auto: true,  needs_review: false, confirm: false, log: commit }
  L2: { auto: false, needs_review: true,  confirm: once,  log: commit+notion }
  L3: { auto: false, needs_review: true,  confirm: twice, log: commit+notion }

operations:
  append_raw:           L0
  append_draft:         L0
  generate_report:      L0
  create_proposal:      L0
  backfill_frontmatter: L1
  add_wikilink:         L1
  add_tag:              L1
  create_evergreen:     L2
  update_conclusion:    L2
  merge_notes:          L2
  rename_evergreen:     L3
  move_evergreen:       L3
  delete_evergreen:     L3

actors:
  manual_session: [L0, L1, L2, L3]
  scheduled_run:  [L0, L1]    # + 可应用 Notion approved 的 L2/L3

hard_disabled:
  - unsanctioned: create_evergreen    # 无 Notion approved 凭证绝不写 L2+
  - unsanctioned: update_conclusion
  - any: notion_delete
  - any: overwrite_without_backup

thresholds:
  orphan_age_days: 7
  stale_review_days: 90
  confidence_min: 0.6      # 低于此的 L2 提案强制 needs_review
  batch_l1_max: 50         # 单次 L1 批量上限

access:
  preferred: cli           # 编辑节点
  fallback: filesystem     # 调度节点/Obsidian 未跑
```

### 4.7 安全边界总结

| 威胁 | 防护 |
|---|---|
| Agent 擅自删/移 Evergreen | L3 硬上锁 + 二次确认 + 双链影响清单 |
| Agent 无凭证写 Evergreen | `hard_disabled: unsanctioned` 硬禁 |
| Agent 覆盖无回滚 | 写前必须有干净 commit 基线;overwrite 前 stash |
| 定时任务闯祸 | 定时轮不主动写 L2+,只应用已 approved |
| Notion 账户全暴露 | OAuth scope 最小化 + human confirmation + 删除硬禁 |
| 双真相源漂移 | Evergreen 唯一结论源;Notion 只链接;不双向复制 |
| 提案被擅自改 | Notion 已审提案(pending→approved)plugin 不可改 |
| 大规模误改 | `batch_l1_max` 限制;L1 commit 独立可逐条 revert |
| 多机同步冲突 | 分级信任压低冲突面;冲突手动 merge |

---

## 5. 调度、降级与人机交互

### 5.1 核心模型:审计循环 + Notion 审批中枢

```
   各 Agent 宿主 (Codex/OpenClaw/Hermes/Claude Code)
   按各自调度触发 plugin 入口
        │  调用
        ▼
   ┌─ knowledge-garden-gardener plugin ──────────────────┐
   │  入口动词:                                          │
   │   weekly-audit / apply-approved / triage-inbox ... │
   └──┬───────────────────────┬──────────────────────────┘
      │ 读/写 vault            │ 经 Notion MCP
      ▼ (filesystem 降级)      ▼
   Obsidian (知识真相源)    Notion (人机交互中枢)
   ─ Git 版本史             ─ 提案库/审批/提醒/周报
```

**职责再划分**:
- **Obsidian/Git**:知识真相源 + 版本史(沉淀)
- **Notion**:所有**人机交互**——提案、审批、提醒、周报、待办队列(交互、移动)
- **plugin**:纯逻辑,被各 Agent 调用,**不含调度器**

### 5.2 plugin 标准入口动词(多 Agent 兼容)

| 入口 | 作用 | 触发场景 |
|---|---|---|
| `weekly-audit` | 只读审计 + 生成提案入 Notion + L1 自动 apply + 周报 | 定时/手动 |
| `apply-approved` | 轮询 Notion approved → apply 到 Evergreen + commit + 回写 | 定时/手动 |
| `triage-inbox` | 整理 Raw → 建议晋升/归类 | 手动 |
| `review-orphans` | 找孤岛 + 生成补链提案 | 手动/定时 |
| `capture` | 接收手机随手记 → 路由到 Obsidian Raw 或 Notion Task | 手动/手机 |

**可移植性保证**:
1. 入口动词标准化
2. `gardener.config.yaml` 放 vault 随 Git 多机同步 → 所有 Agent 共享规则
3. 依赖最小化:能读 vault 文件 + 调 Notion MCP 即可跑;Obsidian CLI/Smart Connections 是**增强项**(有则更强,无则降级)

### 5.3 各 Agent 宿主调度对照

| Agent 宿主 | 调度机制 | 用法 |
|---|---|---|
| Codex | automation | automation 定期触发入口 |
| OpenClaw / Hermes | 原生定时任务 | 定时任务直接调入口 |
| Claude Code | 手动 / 自身调度 | 你说"跑巡园",或配调度 |
| 其它 | 任意的 | plugin 不关心 |

### 5.4 降级访问层

```
园丁业务逻辑
   │ 调用统一接口
   ▼
vault access 抽象层: read / read_glob / search / find_orphans / append / write_proposal
   │ 探测
   ├─→ CLI 在? → kepano skill(IPC,Obsidian 运行中)
   └─→ 否   → filesystem 直读写 .md + rg/grep(降级)
```

**降级判定**:plugin 启动时试调 Obsidian CLI → 成功用 CLI;失败自动降级 filesystem;在 `_Reports/run-log` 记录模式。

**filesystem 模式限制**(写入 plugin,防误用):
- ❌ 不能依赖双链实时解析(悬空检测不准 → 提案标"需桌面端复核")
- ❌ 不能用 Smart Connections 语义检索 → 退化为关键词(rg)
- ✅ 能做:读写 .md、补 frontmatter、找孤立(用 `links` 字段 + 反向 grep)、生成提案/报告

**后果**:filesystem 模式下审计能力退化,但仍能产出基础审计 + 提案;重活留编辑节点手动会话(CLI + SC 都在)。

### 5.5 Notion 侧人机交互队列(移动端)

| Notion 队列 | 用途 | 为何放 Notion |
|---|---|---|
| **提案审批** | L2/L3 变更待批 | 移动端审批 |
| **本周知识摘要**(周报) | 新增/冲突/孤岛概览 | 移动端随手读 |
| **冲突解决队列** | "这两条结论矛盾,哪个对?" | 手机轻决策 |
| **孤岛 triage 队列** | "这条无链接,该连谁?" | 手机快速决定 |
| **过期待复核队列** | "这条结论 90 天了,还成立吗?" | 手机 confirm/flag |
| **快速捕获 Inbox** | 手机随手记 → 下轮路由 | 移动端捕获强 |

**设计取舍**:这些队列是 Notion 数据库视图,共用一个**独立的交互库**(按 `Type` 字段区分),与 §4.5.2 的项目执行库(Projects/Tasks/Habits)是**两组不同的库**——前者是"人机交互面",后者是"项目跟踪面"。详细审计工作稿(带补链推理的孤岛明细)仍留 Obsidian `_Reports/`(工作文档,非交互对象)。

> **Notion = 交互面(轻、移动、决策);Obsidian = 工作面(重、桌面、创作)**。

### 5.6 跨系统审计链(防丢失授权凭证)

提案在 Notion、写入在 Git,双向可追溯:

```
Notion 提案页                    Git commit
  applied_commit: abc123  ◀────▶  msg: "gardener(L2): create X
  status: 已应用                       (approved <notion-page-id>)"
```

- Git 看 Evergreen 变更 → commit msg 带 notion-id → 开 Notion 看授权记录
- Notion 看提案 → applied_commit → 开 Git 看 diff

授权凭证跨两系统,但**互相引用**,不丢失。

### 5.7 失败与异常处理

| 异常 | 处理 |
|---|---|
| git pull 失败(网络/冲突) | 本轮审计**中止**;`_Reports/run-log` 记原因;Notion 推送"巡园失败"。不基于脏数据跑 |
| Notion MCP 不可达(写提案时) | 提案暂存 Obsidian `_System/_PendingProposals/`,下轮补写 Notion。**绝不直接 apply**(没经审批) |
| Agent 轮询 Notion 不可达 | 跳过 apply,只做审计;已批提案下轮再 apply |
| Smart Connections 不可用 | 语义检索降级关键词;相关提案标"需桌面端复核" |
| LLM 调用失败(生成提案时) | 该轮跳过,已生成部分仍提交;不回滚已落盘 Raw |
| 提案 apply 后发现错误 | `git revert <commit>`(提案标 reverted);L1 误改逐条 revert |

**红线不变**:任何 Evergreen 写入要么有 Notion `approved` 凭证(L2/L3),要么是 L1 留 commit 可回滚。无凭证写入 = 硬禁。

---

## 6. 落地路线图

### 6.1 总体节奏:三阶段,不并行

```
阶段 0(地基)        阶段 1(一期·核心闭环)        阶段 2(二期·问答层)
  ↓ 1-2 天             ↓ 1-2 周                       ↓ 视需求
[Obsidian + Notion]  [园丁 plugin + 审批中枢]      [Khoj 跨库问答]
   打地基、迁数据      自动审计→Notion提案→手机批      周报升级、语义问答
```

每阶段独立可跑,跑顺了再加下一块。

### 6.2 阶段 0:地基(1-2 天)

**目标**:两工具就位、同步通、目录立起、**手动**跑通 Raw→Evergreen 晋升。

| 步骤 | 动作 | 验证标准 |
|---|---|---|
| 0.1 | Obsidian 建 vault `Garden/`,按 §3.1 建目录骨架 | 目录存在 |
| 0.2 | 初始化 Git 私仓,配 `.gitignore`(§3.6),装 Obsidian-Git,多机 clone | A 提交 B 能 pull |
| 0.3 | 装 Web Clipper、Bases、Smart Connections;建 §3.5 Base 视图 | 剪藏/视图/语义搜可用 |
| 0.4 | Notion 建 Projects/Tasks/Habits 三库(§4.5.2) | 库结构 + relation 生效 |
| 0.5 | Notion 建「待审核提案」库(§3.3) | 库可写、移动端可见 |
| 0.6 | **手动迁移**:挑 3-5 条已有笔记套 frontmatter,手动走 Raw→Evergreen | schema 跑通、双链生效、`obsidian://` 可点 |
| 0.7 | 配 Notion 官方 MCP(scope 最小化)、装 Smart Connections MCP server | Agent 能 search/fetch 两边 |

**出口**:你能**纯手动**用这套结构管理笔记,无 Agent 也成立——后续自动化的退路。

### 6.3 阶段 1:一期·核心闭环(1-2 周)

**目标**:plugin 跑起来,实现"审计→Notion提案→手机批→下轮 apply"完整循环。

- **1a plugin 骨架(2-3 天)**:搭开放 Agent Skills 规范骨架;写 `SKILL.md`(入口动词/契约/config schema);实现 vault 访问抽象层(CLI 优先 + filesystem 降级)。验证:Claude Code 手动调 `triage-inbox` 读写正常。
- **1b 审计能力(2-3 天)**:实现只读审计(孤岛/过时/冲突/Inbox 统计);实现提案生成写入 Notion。验证:`weekly-audit` 跑一次,Notion 出现提案行,手机收到提醒。
- **1c 应用能力(1-2 天)**:实现 `apply-approved`(轮询 approved → apply + commit + 回写 applied_commit);实现跨系统审计链。验证:Notion approve 一条 → 下轮 apply → Evergreen 更新 + commit 带 notion-id。
- **1d L1 自动 + 周报(1-2 天)**:L1 自动 apply 单独 commit;周报入 Notion 周报队列。验证:L1 commit 周报可列 revert;周报移动端可读。
- **1e 调度接入**:接一个宿主调度(Codex automation / Hermes 定时 / Claude Code)。验证:无人值守跑完整循环。

**出口**:无人值守下每周自动审计、提案进 Notion、手机批、下轮自动入库。**MVP 达成**。

### 6.4 阶段 2:二期·问答层(视需求)

**前置**:一期跑稳 ≥2-4 周,trust config 调过几轮。

| 步骤 | 动作 | 价值 |
|---|---|---|
| 2.1 | 部署 Khoj,接入 Obsidian + Notion 为数据源 | 跨库语义问答 |
| 2.2 | plugin 新增 `ask-garden` 转发 Khoj | Agent 里直接问"我关于 RAG 写过啥" |
| 2.3 | 周报升级:Khoj 语义聚类替代关键词,生成"知识主题演化" | 周报从清单变洞察 |
| 2.4 | (可选)A-Mem 建链算法做智能补链建议 | §2 自主发现连接落地 |

**出口**:跨库问答 + 智能周报。一期跑稳后的增强,非必需。

### 6.5 技术风险与验证顺序

| 风险点 | 不确定性 | 何时验证 | 降级方案 |
|---|---|---|---|
| **各 Agent 宿主的非交互/调度支持** | 高(每家不同) | 阶段 1e 最先 | 用最稳一家先跑通,其它后接 |
| **Notion MCP 待审核态 + 提醒能否如预期** | 中 | 阶段 0.5/1b | 提醒用第三方(webhook→推送)补 |
| **filesystem 降级下审计质量** | 中 | 阶段 1b | 重活留桌面手动会话 |
| **跨系统审计链(Notion↔Git)一致性** | 中 | 阶段 1c | 每周一致性校验脚本 |
| **Obsidian CLI 稳定性** | 低-中 | 阶段 0/1a | filesystem 永久降级 |
| **Git 多机冲突频率** | 低 | 阶段 0.2 起 | 设计已压低冲突面 |

> **建议**:阶段 1e 前先花半天**单独验证你最常用 Agent 宿主的调度能力**——这是自动化的前提,值得前置确认。

### 6.6 成功标准

| 维度 | 一期成功标志 |
|---|---|
| **资产安全** | Evergreen 任何变更都能在 Git 找到 commit + Notion 授权记录;无无凭证写入 |
| **自动化有效** | 连续 4 周无人值守审计无中断;提案进 Notion 手机可批 |
| **人工负担** | 每周整理笔记时间下降;主要动作变成手机审批 |
| **可回退** | 任何 Agent 误改都能 `git revert` 单条恢复;trust config 可随时收紧 |
| **地基独立** | 即使 plugin 全停,仍能纯手动用 Obsidian+Notion 管理(阶段 0 能力不丢) |

### 6.7 YAGNI 边界(一期不做)

- ❌ 多人协作/权限隔离(个人库)
- ❌ Khoj/AnythingLLM 问答层(二期)
- ❌ A-Mem 智能建链(二期,先用规则补链)
- ❌ 复杂工作流引擎(n8n/Make,plugin 入口动词够)
- ❌ 云端 runner 跑 vault(隐私)
- ❌ 自定义 LLM 微调(用现成 Agent 能力)

---

## 附录 A:决策记录

| # | 决策 | 理由 |
|---|---|---|
| D1 | Obsidian 为知识主库,Notion 为执行/交互层 | 资产可迁移(Git/纯 md)+ 移动端交互(Notion 强) |
| D2 | Agent 当园丁不当作者 | 防自动化"热心改园艺布局";人定稿 |
| D3 | Git 同步(非 Obsidian Sync) | 免费、完整版本史、与授权模型叠加 |
| D4 | 提案审批放 Notion(非 Obsidian) | 移动端审批、异步、不占桌面 |
| D5 | plugin 多 Agent 兼容,不含调度器 | 调度交给各宿主原生能力(Codex/Hermes 等) |
| D6 | 三层写入(L0/L1 自由,L2/L3 审批) | 分级信任,低风险自动化、高风险人审 |
| D7 | 定时可应用已 Notion approved 的写 | 区分"无授权擅写"与"应用已授权" |
| D8 | 同步选 Git → 调度节点不能 Headless | Headless 只连 Obsidian Sync;走 filesystem 降级 |
| D9 | Evergreen 结论不复制到 Notion,只链接 | 防双真相源漂移 |
| D10 | `gardener.config.yaml` 信任全配置化 | 信任可调,出错可收紧 |

## 附录 B:术语表

| 术语 | 含义 |
|---|---|
| 园丁 Plugin | `knowledge-garden-gardener`,复合 Agent Plugin,本方案核心 |
| Raw | 原料区,Obsidian `_Inbox/`,未提炼的捕获 |
| Evergreen | 长期花园,Obsidian `Concepts/` 等,人授权后定稿的结论 |
| Project | 执行区,Notion Projects/Tasks/Habits |
| L0-L3 | 操作风险档(L0 自由 → L3 审批+二次确认) |
| 授权凭证 | Notion `status=approved`;plugin 据此 apply |
| 跨系统审计链 | Notion 提案 ↔ Git commit 互相引用 notion-id/applied_commit |
| 编辑节点 | 日常用机,Obsidian 在跑,CLI 可用 |
| 调度节点 | 按 Agent 调度运行,默认 filesystem 降级 |
| 入口动词 | plugin 标准入口(weekly-audit/apply-approved 等) |

---

*文档结束。审阅后如需调整,可直接在对应章节批注。*
