# Changelog

本文件记录 `knowledge-garden-gardener` 的显著变更,面向使用者和维护者,而不是 git 日志的简单堆砌。

格式基于 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/),版本号遵循 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)。

## [0.5.0] - 2026-09-17

**Notion 传输层从未经真机验证的 REST 风格 mock 改为真 Notion 官方 REST API**(internal integration token 认证)。这是打通真实 Notion 的关键一步:此前 `POST {endpoint}/{tool}` 契约既不兼容官方 hosted MCP(JSON-RPC 单端点)也不兼容官方 REST API,`garden init` 从未在真实工作区建库成功过。

### Added

- **`NotionClient` 真 REST 传输**(`notion.py` 重写):Bearer token + `Notion-Version: 2022-06-28` 头;`send(method, path, json)` 注入点替代 `post(tool, payload)`;新增 `NotionAPIError`(继承 `httpx.HTTPError`,现有降级路径零改动);属性值双向转换(业务侧扁平值 ⇄ Notion 类型化对象:title/rich_text/select/multi_select/number/date/url/checkbox,`flatten_properties` 归一化查询结果)。
- **token 走环境变量**:config 记 `token_env: NOTION_TOKEN`(secret 不入 Git);显式 `token` 参数 > 环境变量。
- **`init_notion.create_all_databases` 产出真 REST payload**:title 富文本数组(此前是裸字符串,真 API 必 400)、select options 完整下发(此前被丢弃)、Tasks→Projects relation 自动接线(按创建顺序解析目标库 id)。
- **`check_connection` 预检**(`GET /users/me`):401 → 指引检查 NOTION_TOKEN;404 → 指引父页面 ··· → Connections 分享给 integration。
- **`parse_page_ref`**:`--parent-page` 接受页面 URL / 带/不带连字符的 32-hex id;正确丢弃 `?v=` view id。
- **`garden init` 新参数**:`--api-base`(默认官方)/`--token-env`(默认 NOTION_TOKEN)/`--auth-done`;`--oauth-done` 保留为废弃别名;`--mcp-endpoint` 移除(从未对真实端点工作过)。
- **config 兼容**:老 config 的 `mcp_endpoint` key 仍被读取(当 api_base 用),升级不破坏;`api_base`/`token_env`/`habits_database_id` 缺省时走默认值。

### Changed

- **`NotionClient` 构造改全关键字参数**(`proposal_db=`/`projects_db=`/...):传输层重写的破坏性变更,业务方法签名(create_proposal/poll_approved/write_applied_commit/create_task/write_weekly_report)不变。
- **config notion 块**:`transport: rest` + `api_base` + `token_env` + 5 个 database id(新增 habits_database_id 回填)。
- Hermes 包装 schemas/tools/cli:init 参数 mcp_endpoint → api_base/token_env/parent_page/auth_done,CLI 侧同步。
- README/SKILL/agent-adapters 的 init 用法示例全部更新。

### Fixed

- **`garden init --config` 默认相对 CWD 解析**:argparse 默认值 `_Config/gardener.config.yaml` 相对调用者目录而非 vault,config 会写错位置(本机真机验证发现)。改为显式路径参数缺省时取 `<vault>/_Config/gardener.config.yaml`(新增 `_init_config_path` + 2 回归测试)。

### Verified

- `pytest tests/ -q` → **133 passed**(原 118 + 新增 15:REST 契约 8 + init payload 3 + parse_page_ref 4 + auth 别名/config 路径回归,净增因合并旧用例)。测试现锁死与 Notion API v1 的 wire 格式(类型化属性、filter 语法、parent 结构)。
- **真机端到端验证**(v0.5.0 首次):`garden init --auth-done` 在真实工作区建 5 库成功;`GET /databases` 确认提案库 status 5 个 select options 完整、Tasks→Projects relation 正确接线、周报库 8 字段齐全;`poll_approved()` 真机空查询通过。
- 版本号全量校验:9 处清单/断言同步 0.5.0。

## [0.4.0] - 2026-08-12

补齐设计 §5.2 全部 5 个标准入口动词。原仅 `apply-approved` 完整,本次新增 `review-orphans`/`capture`,补全 `weekly-audit`(L1 自动 apply + 周报)与 `triage-inbox`(归类建议),并扩展 Notion 基础设施(第 5 库 + Task/周报写入)。

### Added

- **`review-orphans` 入口动词**:只读审计孤岛 + 生成补链提案入 Notion(L2 link)。复用 `audit()` 取 orphans,聚焦孤岛,不写 Evergreen。
- **`capture` 入口动词**:手机/手动随手记 → 路由 Obsidian Raw 或 Notion Task。关键词规则树判定(§4.5.5),Task 不可达时降级落 Raw(`type=task_candidate`),离线可用。新增 `capture.py`(route + 落地原语)。
- **L1 自动 apply 引擎**(`l1_apply.py`):weekly-audit 本轮自动执行三类 L1 操作(无需 Notion 凭证)——backfill 缺失 frontmatter(id/created_at/updated_at/status)、关键词补链(正文命中标题 → `[[ ]]` + links)、英文高频词补 tags(仅空 tags 时;中文分词待二期)。每类一个 git commit(可整类 revert),受 `batch_l1_max` 截断。
- **周报生成**(`weekly_report.py`):审计数据 + Projects 活动 → markdown 报告。双写:本地 `_System/_Reports/weekly-report.md`(始终)+ Notion 周报队列(若配置,失败降级 stderr 警告)。
- **`triage-inbox` 归类建议**(`triage.py`):对每个 inbox item 给 next step(任务候选→Task / 含 URL→Reference / 概念→Evergreen)。只读,不写。
- **Notion 第 5 库「周报」**(`init_notion.py`):独立交互库(§5.5),schema 含 week/summary/各 count/generated_at。`garden init` 现在建 5 库并回填 5 个 id。
- **`NotionClient.create_task` / `write_weekly_report`**:capture 路由 + 周报写入;db 未配置时抛 `NotionConfigError`(新异常),调用方据此优雅降级。
- **Hermes 侧 6 tool / 6 cli 子命令**:新增 `garden_review_orphans`/`garden_capture` tool + `hermes garden review-orphans|capture` 子命令;schemas/tools/cli/plugin.yaml 同步。

### Changed

- **`NotionClient` 构造扩参** `tasks_db`/`weekly_db`(关键字字参数,默认空):老 config(无 tasks/weekly id)构造不破坏,对应方法抛 `NotionConfigError` 降级。`weekly-audit`/`apply-approved`/`review-orphans` 路径从 `cfg.notion` 读取并传入。
- **config notion 块** 加 `tasks_database_id`/`weekly_database_id`(`init_orchestrator._CONFIG_TEMPLATE` + `templates/gardener.config.yaml`)。`garden init` 自动回填;手写 config 可留空(对应能力降级)。
- **`weekly-audit` 主流程**:audit + emit_proposals 之后,串接 `apply_l1`(L1 自动写 + commit)+ `summarize`/`publish`(周报)。各 Notion 异常独立 try/except,互不阻断。

### Fixed

- **`pyproject.toml` version 历史遗漏**:停留在 `0.1.0`(0.2.0 起其它清单文件已同步到 0.3.x,pyproject 漏更)。本次一并修正到 `0.4.0`。

### Verified

- `pytest tests/ -q` → **118 passed**(原 76 + 新增 42:Phase A 8 + L1 13 + 周报 5 + capture 7 + triage 5 + cli 集成 4 + Hermes 8)。
- 版本号全量校验:`grep "0.3"` 跨 8 处清单文件(pyproject/claude-plugin/codex-plugin/openclaw/package.json/hermes plugin.yaml/marketplace.json ×2)无遗留。

## [0.3.1] - 2026-08-04

修复 3 个 bug + 改进 `garden init` 安装前置(`pyproject.toml` 缺 build-system 导致 `pip install -e .` 失败)。

### Fixed

- **`garden` CLI `--config` 默认相对 CWD 解析**:argparse `default="_Config/gardener.config.yaml"` 没有 vault 上下文,任何不显式传 `--config` 的调用必 `FileNotFoundError`。改成 `default=None`,新增 `_resolve_config_path()` 回退到 `<vault>/_Config/gardener.config.yaml`;`load_config` 失败给 exit 5 + 友好引导(指向 `garden init`)。
- **Notion 不可达裸 traceback**:`apply-approved` / `weekly-audit` 路径没 try/except,`httpx.RequestError` / `UnsupportedProtocol` 直接抛栈给 caller(scheduled_run cron 会误判)。包 `httpx.HTTPError, httpx.RequestError`,`apply-approved` 退出 4 + 提示幂等重试;`weekly-audit` 降级到 stderr 警告 + 继续走本地 `_PendingProposals/` 暂存(已有机制)。
- **`hermes garden <verb>` 子命令 stdout 被吞**:Hermes dispatcher(`hermes_cli/main.py:12562-12565`)只把 handler 的 `int` 返回值当 exit code,字符串返回值整体丢弃。改 `garden_command` 返回 int,直接 `print` stdout/stderr,JSON 解析分别走 ok/失败路径。未知子命令返回 rc=1。
- **`triage-inbox` 不再误依赖 config**:`triage-inbox` 业务逻辑只需要 `audit(vault)`,但旧实现把它和另外两个 Notion 命令一起放在 `load_config` 之后,设计误差。把它移到 `load_config` 之前,**恢复"vault-only"语义**。

### Added

- 新增 `tests/test_cli_subcommand_errors.py`(4 tests):
  - `test_triage_inbox_runs_without_config`
  - `test_triage_inbox_with_explicit_config`
  - `test_weekly_audit_missing_config_exits_5`
  - `test_apply_approved_notion_unreachable_exits_4`
- 新增 vault 模板占位符入仓(`.gitkeep`):`Concepts/`, `Notes/`, `Index/`, `References/`, `_Config/`, `_System/`, `_Templates/` —— 这些是 `init_vault.py` 骨架输出,但之前没有 `.gitkeep` 占位,导致 git 不入仓。

### Changed

- `pyproject.toml` 补 `[build-system]` 和 `[tool.setuptools.packages.find]`:`pip install -e .` 之前因"Multiple top-level packages discovered"(setuptools 68+ 默认拒绝自动发现)失败,现在能直接装。
- `.gitignore` 加 `.garden-init.json` 排除 init 运行时 checkpoint。

### Verified

- `pytest tests/ -q` → **68 passed**(原 64 + 新 4)。
- 端到端实测:`garden --vault X triage-inbox`(无 config)→ exit 0;`garden --vault X weekly-audit`(无 config)→ exit 5 + 引导;`garden --vault X apply-approved`(Notion 占位符)→ exit 4 无 traceback;`hermes garden triage-inbox --vault X` → stdout 可见(Bug 3 修复);`garden init` → 仍 exit 3 OAuth 指引。

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
