# knowledge-garden-skill

知识花园系统的设计仓库。核心理念:**Agent 当"园丁",不当作者**——Agent 负责搜、整理、补链接、生成草稿、发现孤岛与矛盾;真正进入长期知识库的结论必须经人确认。

## 仓库内容

| 文件 | 说明 |
|---|---|
| `docs/knowledge-garden-design.md` | 完整设计方案(6 章 + 附录) |
| `docs/agent-adapters.md` | **各 Agent 宿主(Claude Code/Codex/Hermes/OpenClaw)接入步骤** |

## 架构一句话

- **Obsidian** = 知识真相源(可 Git、可迁移、双链图谱)
- **Notion** = 执行跟踪 + 人机交互(移动端审批/提醒/周报)
- **园丁 Plugin** = 标准 CLI(`garden`),所有能调 shell 的 Agent 宿主都能用;不含调度器
- **授权模型** = 分级信任(L0/L1 自动,L2/L3 在 Notion 审批),所有 Evergreen 写入可追溯

## 在哪个 Agent 里用?

`garden` 是标准 CLI,不是任何 Agent 的私有插件格式。各宿主只是"换个触发 `garden` 命令的入口":

| 宿主 | 调用 | 定时 |
|---|---|---|
| Claude Code | `SKILL.md` + 直接命令 | 手动/外部 cron |
| Codex | `codex exec` | app Automations |
| Hermes/OpenClaw | cron job 的 prompt | 内置 cron scheduler |
| Cursor | MCP/rules | 外部 cron |

**详细接入步骤见 [`docs/agent-adapters.md`](docs/agent-adapters.md)**。

## 当前状态

设计已确认,一期 MVP 已实现(**44 tests pass**,含 `garden init` 自动化引导)。

## 仓库结构

```
knowledge-garden-skill/
├── SKILL.md                  Agent 入口说明(各入口动词怎么调)
├── pyproject.toml
├── garden_gardener/          园丁 plugin 主体(Python)
│   ├── config.py             加载/校验 gardener.config.yaml
│   ├── risk.py               风险分级判定(WHO×WHAT 安全闸)
│   ├── frontmatter.py        YAML frontmatter 解析
│   ├── vault.py              vault 访问抽象层(CLI 优先 + filesystem 降级)
│   ├── gitutil.py            git 操作封装(带 gardener 前缀 + notion-id)
│   ├── notion.py             Notion MCP 客户端封装
│   ├── audit.py              只读审计(孤岛/过时/Inbox)
│   ├── proposal.py           提案生成 + Notion 失败降级暂存
│   ├── apply.py              轮询 approved → apply + commit + 回写
│   ├── init_vault.py         vault 骨架初始化(幂等)
│   ├── init_notion.py        Notion 4 库 schema + 自动创建
│   ├── init_plugins.py       Obsidian 插件启用清单 + 安装指引
│   ├── init_orchestrator.py  init 编排(checkpoint 续跑 + OAuth 断点)
│   └── cli_entry.py          CLI 入口(init/weekly-audit/apply-approved/triage-inbox)
├── templates/                Obsidian vault 模板
├── tests/                    44 tests,全 pass
└── docs/
    ├── knowledge-garden-design.md       完整设计方案
    └── superpowers/plans/               实现计划
```

## 运行

```bash
pip install -e . pytest pyyaml httpx

# 首次引导(自动建 vault + Notion 库 + 插件清单,OAuth 是唯一人工断点)
garden init --vault ./Garden --mcp-endpoint <endpoint> --parent-page <notion-page-id>
# OAuth 完成后续跑
garden init --vault ./Garden --mcp-endpoint <endpoint> --parent-page <notion-page-id> --oauth-done

# 审计(在 vault 根目录)
garden --config _Config/gardener.config.yaml --vault . weekly-audit
# 应用已批准提案
garden --config _Config/gardener.config.yaml --vault . apply-approved
```

测试:`python -m pytest -v`
