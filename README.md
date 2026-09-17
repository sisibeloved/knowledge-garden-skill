# 🌿 知识花园园丁

[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](plugins/knowledge-garden-gardener/CHANGELOG.md)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-D97757.svg)](#安装)
[![Codex](https://img.shields.io/badge/Codex-plugin-0A7EA4.svg)](#安装)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-bundle-8A2BE2.svg)](#安装)
[![Hermes](https://img.shields.io/badge/Hermes-plugin-FF6B35.svg)](#安装)
[![Tests](https://img.shields.io/badge/tests-131%20pass-success.svg)](#测试)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

面向个人工作流的知识花园复合技能插件,以 Claude Code / Codex 插件形式交付。核心理念:**Agent 当园丁,不当作者**——负责搜、整理、补链接、生成草稿、发现孤岛与矛盾;真正进入长期知识库的结论必须经人在 Notion 移动端审批。

---

## 🎯 核心理念

| 角色 | 权限 | 类比 |
|---|---|---|
| **园丁 Plugin** | 全库只读审计 + 生成提案 + 应用已授权写 | 园丁巡视,提建议,按授权动花 |
| **人(园主)** | 唯一的授权来源(在 Notion 审批) | 只有园主能授权移栽 |

**Obsidian** = 知识真相源(可 Git、可迁移、双链图谱);**Notion** = 执行跟踪 + 人机交互(移动端审批/提醒/周报);**授权模型** = 分级信任(L0/L1 自动,L2/L3 在 Notion 审批),所有 Evergreen 写入可追溯。

## 📦 入口动词

| 入口 | 用途 | 风险 |
|---|---|---|
| 🌱 `init` | 首次引导:自动建 vault 骨架 + Notion 5 库 + 插件清单(integration token 授权是唯一人工断点) | L0 |
| 🔍 `weekly-audit` | 只读审计 vault(孤岛/过时/Inbox),生成提案入 Notion | 不写 Evergreen |
| ✅ `apply-approved` | 轮询 Notion 已批准提案 → apply 到 Evergreen + git commit + 回写 | L2/L3 需授权 |
| 📥 `triage-inbox` | 列出 `_System/_Inbox/` 待处理 Raw | 只读 |

入口动词是标准 CLI(`garden`),不是任何 Agent 的私有插件格式——所有能调 shell 的 Agent 宿主都能用。详见 [Agent 宿主适配指南](docs/agent-adapters.md)。

## 🛡️ 安全模型(L0-L3)

| 风险档 | 操作类型 | 执行路径 |
|---|---|---|
| 🟢 L0 自由 | 追加 Raw/Drafts/Reports | 直接写 |
| 🟡 L1 自动+留痕 | 修改已有笔记的元数据/链接 | 自动写 + git commit |
| 🟠 L2 需审批 | 新增 Evergreen / 改正文结论 | Notion 提案 → approve → apply |
| 🔴 L3 需审批+二次确认 | 删除/移动/重命名 | Notion 提案 → approve → 二次确认 → apply |

**红线**:无 Notion `approved` 凭证绝不写 Evergreen L2+;L3 破坏性操作即便已批准,定时场景下也拒(需人在场);git pull 失败必须中止。

---

## 🚀 安装

### Claude Code(插件市场)

```
/plugin marketplace add https://github.com/sisibeloved/knowledge-garden-skill
/plugin install knowledge-garden-gardener
```

安装后,Agent 通过 `using-garden` skill 按需加载入口动词。

### Codex CLI

```bash
codex plugin marketplace add https://github.com/sisibeloved/knowledge-garden-skill
codex plugin add knowledge-garden-gardener@knowledge-garden
```

### OpenClaw(Plugin Bundles,几乎免费兼容)

OpenClaw 原生支持把 Claude/Codex 插件当 bundle 安装,无需额外格式:
```bash
openclaw plugins install knowledge-garden-gardener@knowledge-garden
```

### Hermes(薄 plugin 包装)

```bash
# plugins 目录因平台而异,用 Hermes 自身查询(不要假设 ~/.hermes/)
PLUGINS_DIR=$(python -c "from hermes_cli.plugins_cmd import _plugins_dir; print(_plugins_dir())")
mkdir -p "$PLUGINS_DIR/garden"
cp -r plugins/knowledge-garden-gardener/hermes-plugin/garden/* "$PLUGINS_DIR/garden/"
hermes plugins enable garden
```
Hermes 包装把 garden 4 个入口注册为 tool + `hermes garden` CLI 子命令。

### 本地开发安装

```bash
git clone https://github.com/sisibeloved/knowledge-garden-skill
cd knowledge-garden-skill/plugins/knowledge-garden-gardener
pip install -e . pytest pyyaml httpx
```

## 💬 使用示例

```bash
# 首次引导(自动建 vault + Notion 5 库,授权是唯一人工断点)
garden init --vault ./Garden --parent-page <notion页面URL或page-id>
#    → exit 3 + 指引:建 integration(https://notion.so/my-integrations)、
#      设 NOTION_TOKEN=ntn-xxx、把父页面 ··· → Connections 分享给它
# 授权完成后带 --auth-done 续跑(其余全自动)
garden init --vault ./Garden --parent-page <notion页面URL或page-id> --auth-done

# 每周巡园(只读审计 + 生成提案入 Notion,不写 Evergreen)
garden --config _Config/gardener.config.yaml --vault . weekly-audit

# 应用已批准提案(定时场景用 --actor scheduled_run)
garden --config _Config/gardener.config.yaml --vault . --actor scheduled_run apply-approved
```

---

## 📁 仓库结构

```
knowledge-garden-skill/
├── .claude-plugin/marketplace.json          Claude Code 插件市场注册
├── .agents/plugins/marketplace.json         Codex CLI 插件市场注册
├── README.md
├── docs/
│   ├── knowledge-garden-design.md           完整设计方案(6 章 + 附录)
│   ├── agent-adapters.md                    Agent 宿主适配指南
│   └── superpowers/plans/                   实现计划
└── plugins/knowledge-garden-gardener/       插件本体
    ├── .claude-plugin/plugin.json           Claude Code 插件元数据
    ├── .codex-plugin/plugin.json            Codex CLI 插件元数据
    ├── package.json
    ├── CHANGELOG.md
    ├── skills/using-garden/SKILL.md         入口 router 技能
    ├── garden_gardener/                      Python CLI 主体(13 模块)
    ├── templates/gardener.config.yaml        配置模板
    └── tests/                                46 tests,全 pass
```

## 🧪 测试

```bash
cd plugins/knowledge-garden-gardener
python -m pytest -v
```

当前:131 tests pass,覆盖 config/risk/frontmatter/vault/gitutil/notion/audit/proposal/apply/capture/triage/init 全模块(含 Notion REST wire 契约)。

## 📚 文档

- [完整设计方案](docs/knowledge-garden-design.md) — 6 章 + 决策记录 + 术语表
- [Agent 宿主适配指南](docs/agent-adapters.md) — Claude Code/Codex/Hermes/OpenClaw 接入步骤
- [变更日志](plugins/knowledge-garden-gardener/CHANGELOG.md)

## 🔗 设计参考

| 项目 | 借鉴点 |
|---|---|
| [Kohei-Wada/knowledge-gardener](https://github.com/Kohei-Wada/knowledge-gardener) | WHEN/HOW 分离的园丁决策层 |
| [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | Obsidian 官方 CLI 护栏(13 silent failures) |
| [Notion 官方 MCP](https://developers.notion.com/guides/mcp/overview) | Notion 数据库 + 提案库自动化 |

## License

MIT
