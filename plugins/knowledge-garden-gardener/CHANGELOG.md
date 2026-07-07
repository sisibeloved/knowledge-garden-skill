# Changelog

本文件记录 `knowledge-garden-gardener` 的显著变更,面向使用者和维护者,而不是 git 日志的简单堆砌。

格式基于 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/),版本号遵循 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)。

## [0.3.0] - 2026-07-02

OpenClaw 与 Hermes 宿主适配。

### Added

- 新增 `openclaw.plugin.json`(native manifest),让 OpenClaw 识别更稳。OpenClaw 的 Plugin Bundles 机制原生兼容 Claude/Codex 格式,几乎零额外工作——它自动检测 `.claude-plugin/plugin.json` 把 `skills/` 当 skill 加载。
- 新增 `hermes-plugin/garden/` 薄包装(plugin.yaml + __init__.py + tools.py + schemas.py + cli.py):把 garden 4 个入口动词注册为 4 个 Hermes tool(LLM 自动调用)+ `hermes garden` CLI 子命令(用户手动),内部 subprocess 调 garden CLI。handler 参数对齐真实 CLI(--vault/--config/--actor),非虚构 --path。
- 新增 `tests/test_hermes_plugin.py`(13 tests):覆盖 build_command 参数拼装、register(ctx) 注册逻辑、cli setup_fn/handler_fn 路由、handler 不 raise、plugin.yaml 校验、schemas 参数对齐真实 CLI。
- 扩充 `tests/test_layout.py`:守卫 OpenClaw manifest 与 Hermes 包装目录存在。

### Changed

- `docs/agent-adapters.md` 重写:核实并记录四宿主(Claude Code/Codex/OpenClaw/Hermes)真实接入方式,纠正之前笼统描述。明确 OpenClaw 的 Gateway 级 cron ≠ agent tools.exec 区分。
- README 增加 OpenClaw/Hermes badge 与安装分区。
- 三处版本(plugin.json/package.json/openclaw.plugin.json/plugin.yaml/marketplace.json)对齐到 0.3.0。
- **本机 Hermes v0.18.0 实测验证**:`hermes plugins list` 显示 garden/enabled/0.3.0/user;`register(ctx)` 成功注册 4 tool + 1 cli command;`hermes garden --help` 显示 4 子命令。修正了安装路径文档(真实路径是 `get_hermes_home()/plugins`,非 `~/.hermes/plugins/`——后者是历史遗留)。Hermes plugin API 从本机 bundled plugin(google_meet)反推确认:`register_cli_command`(非 `register_command`)+ `register_tool` 带 `emoji`/`check_fn`/`toolset`。

## [0.2.0] - 2026-07-02

重构为 marketplace 布局,支持 Claude Code 与 Codex 双插件市场安装。

### Added

- 新增 `.claude-plugin/marketplace.json` 与 `.agents/plugins/marketplace.json`,支持从插件市场安装:
  - Claude Code:`/plugin marketplace add` + `/plugin install`
  - Codex CLI:`codex plugin marketplace add` + `codex plugin add`
- 新增 `plugins/knowledge-garden-gardener/.claude-plugin/plugin.json` 与 `.codex-plugin/plugin.json`,双宿主插件元数据对齐(version/interface/keywords)。
- 新增 `skills/using-garden/SKILL.md`,作为薄 router 入口技能,引导到 4 个入口动词(init/weekly-audit/apply-approved/triage-inbox)。
- 新增 `docs/agent-adapters.md`,核实并记录各 Agent 宿主(Claude Code/Codex/Hermes/OpenClaw)的真实接入方式与定时机制。
- 新增根 `.gitignore`,排除 Python 缓存、venv、Obsidian 本地状态。

### Changed

- 仓库重构为 marketplace 标准布局:插件本体移至 `plugins/knowledge-garden-gardener/`,根目录仅保留 marketplace 元数据与仓库级文档(`docs/`)。
- README 重写:增加 version/Codex/Claude Code/tests badge、入口动词表、L0-L3 安全模型表、安装分区(Claude Code/Codex/本地开发)。
- `SKILL.md` 从根目录移至 `skills/using-garden/SKILL.md`,符合 Agent Skills 规范的目录约定。

## [0.1.1] - 2026-07-02

`garden init` 命令错误处理修复(验证阶段发现)。

### Fixed

- 修正 `garden init --vault X` 参数解析失败:`--vault` 原为全局参数,init 子命令重新声明自身的 `--vault`/`--config`。
- Notion 不可达时不再抛 Python 栈,改为捕获 `NotionBootstrapError` → exit 4 + 友好消息,checkpoint 保留可续跑。
- 新增 `tests/test_cli_init_errors.py`(2 tests)覆盖以上两种失败模式。

## [0.1.0] - 2026-07-01

首个 MVP 版本。Agent 当园丁不当作者的核心闭环成形。

### Added

- **风险分级引擎**(`risk.py`):WHO × WHAT 三维授权判定。L0/L1 自动,L2 需 Notion approved 凭证,L3 破坏性操作即便已批准在定时场景下也拒(需人在场)。无凭证写 Evergreen 硬禁。
- **vault 访问抽象层**(`vault.py`):CLI 优先 + filesystem 降级,路径逃逸防护(`Path.relative_to`)。
- **git 操作封装**(`gitutil.py`):commit 带 `gardener(Lx)` 前缀 + notion-id(跨系统审计链),支持 revert。
- **Notion MCP 客户端**(`notion.py`):提案 CRUD + `poll_approved` 客户端二次过滤(纵深防御,不盲信服务端 filter)。
- **只读审计**(`audit.py`):找孤岛(无 links + 无 backlinks + age>7天)、找过时(last_reviewed>90天)、Inbox 待处理统计。
- **提案生成**(`proposal.py`):审计转提案写 Notion,失败降级暂存 `_PendingProposals/`,绝不直接 apply。
- **apply 编排**(`apply.py`):轮询 Notion approved → 经 risk.decide 校验 → 写 Evergreen + commit + 回写 applied_commit。集成核心,授权模型端到端验证。
- **`garden init` 命令**:自动建 vault 骨架(幂等)、调 Notion MCP 建 4 库(Projects/Tasks/Habits/待审核提案)、填回 database id 到 config、生成 Obsidian 插件启用清单。checkpoint 续跑,OAuth 是唯一人工断点。
- **CLI 入口**(`cli_entry.py`):`init`/`weekly-audit`/`apply-approved`/`triage-inbox` 四个子命令。
- **frontmatter 解析**(`frontmatter.py`):YAML frontmatter 解析与回写。
- **配置加载**(`config.py`):加载并校验 `gardener.config.yaml`,所有 operation 映射的 risk level 必须存在。
- 46 tests 全 pass,TDD 过程中捕获 3 个真实 bug(risk 的 L2/L3 actor 能力边界、notion 的服务端 filter 盲信、config 模板的 YAML 花括号被 format 误解析)。

### 设计决策

- Obsidian 为知识真相源(纯 md、可 Git、可迁移),Notion 为执行/交互层(移动端审批/提醒/周报)。结论只存 Obsidian,Notion 只链接,不双向复制。
- 同步选 Git → 调度节点不能 Headless(只连 Obsidian Sync),走 filesystem 降级。
- 提案审批放 Notion 移动端(异步循环:审计→提案→手机批→下轮 apply),非 Obsidian 桌面端。
