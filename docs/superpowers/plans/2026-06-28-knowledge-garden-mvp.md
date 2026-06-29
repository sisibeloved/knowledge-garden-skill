# 知识花园 MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现知识花园一期的可执行核心——一个 Python 实现的园丁 plugin,能只读审计 Obsidian vault、生成提案入 Notion、轮询已批准提案并 apply 到 Evergreen(含 git 提交与跨系统审计链)。

**Architecture:** 确定性逻辑用 Python 包 `garden_gardener/`(可单测的纯函数模块);`SKILL.md` 描述各入口动词供 Agent 宿主(Codex/Hermes/Claude Code)调用;vault 访问走抽象层(CLI 优先 + filesystem 降级);Notion 经官方 MCP;授权凭证 = Notion `status=approved`,无凭证写 Evergreen 硬禁。

**Tech Stack:** Python 3.11、pytest、PyYAML(frontmatter/config)、httpx(Notion MCP 调用)、Git(Obsidian-Git 插件 + CLI)、Obsidian CLI(IPC)、Notion 官方 MCP。

**对应设计:** `docs/knowledge-garden-design.md`。本计划覆盖设计 §3(数据模型)、§4(权限)、§5(调度降级)的代码实现部分,以及 §6 的阶段 0 + 阶段 1。§6.2 阶段 0 中的 Obsidian/Notion/Git **手动配置**作为前置步骤(Task 0),不写代码。

---

## File Structure

```
knowledge-garden-skill/
├── SKILL.md                          # Agent 入口说明(各入口动词怎么调)
├── pyproject.toml                    # 包定义 + 依赖 + pytest 配置
├── garden_gardener/
│   ├── __init__.py
│   ├── config.py                     # 加载/校验 gardener.config.yaml(§4.6)
│   ├── risk.py                       # 风险分级判定:WHO×WHAT→允许/审批/拒绝(§4.1-4.4)
│   ├── vault.py                      # vault 访问抽象层:CLI 优先+filesystem 降级(§5.4)
│   ├── frontmatter.py                # frontmatter 读写/解析(YAML)
│   ├── audit.py                      # 只读审计:孤岛/过时/冲突/Inbox(§5 audit 逻辑)
│   ├── proposal.py                   # 提案生成 + 写 Notion + 暂存降级(§2.3 step3)
│   ├── apply.py                      # 轮询 approved → apply + commit + 回写(§2.3 step8-11)
│   ├── notion.py                     # Notion MCP 客户端封装(交互①③④)
│   ├── gitutil.py                    # git 操作封装(pull/commit/revert 带前缀)
│   └── cli_entry.py                  # CLI 入口:weekly-audit/apply-approved/triage-inbox...
├── templates/                        # Obsidian vault 模板(供阶段 0 复制)
│   ├── gardener.config.yaml
│   ├── inbox-raw.md
│   ├── concept-evergreen.md
│   └── weekly-report.md
├── tests/
│   ├── conftest.py                   # 临时 vault/Notion mock/git fixture
│   ├── test_risk.py
│   ├── test_vault.py
│   ├── test_frontmatter.py
│   ├── test_audit.py
│   ├── test_proposal.py
│   ├── test_apply.py
│   └── test_config.py
└── docs/
    ├── knowledge-garden-design.md
    └── superpowers/plans/2026-06-28-knowledge-garden-mvp.md
```

**职责边界**:
- `risk.py` 纯函数,无 IO,最易测——所有授权判定都过它
- `vault.py` 是唯一碰 vault 文件的模块;其它模块通过它读写
- `notion.py` 是唯一调 Notion MCP 的模块;测试全程 mock
- `apply.py` 编排 gitutil + vault + notion + risk,是集成核心
- `cli_entry.py` 薄壳,只解析参数调模块函数,不含业务逻辑

---

## Task 0: 阶段 0 地基(手动配置,无代码)

> 这些是 Obsidian/Notion/Git 的手动一次性配置,为后续代码提供运行环境。代码任务(Task 1+)依赖其产出。若已部分完成可跳过。

**Files:** 无代码文件;产出在 Obsidian vault 与 Notion workspace。

- [ ] **Step 0.1: 建 Obsidian vault 并初始化 Git**

  在 Obsidian 新建 vault(路径自选,如 `~/Garden`),在 vault 根执行:
  ```bash
  cd <vault-root>
  git init -b main
  ```
  按 design §3.1 建目录骨架:
  ```
  _System/_Inbox/  _System/_AgentDrafts/  _System/_PendingProposals/
  _System/_Reports/  _System/_Archive/
  Concepts/  Notes/  References/  Index/
  _Templates/  _Config/
  ```
  (用 `mkdir -p` 批量建,空目录 git 不跟踪,放 `.gitkeep`)

  验证:`ls` 看到目录结构存在。

- [ ] **Step 0.2: 配 `.gitignore` 并建私仓**

  在 vault 根写 `.gitkeep`(各空目录)与 `.gitignore`,内容抄 design §3.6:
  ```
  .obsidian/workspace*.json
  .obsidian/plugins/*/data.json
  *.cache
  _Trash/
  ```
  在 GitHub 建 private repo,`git remote add origin <url>` 并 `git push -u origin main`。

  验证:另一台机器 `git clone` 能拉到。

- [ ] **Step 0.3: 装 Obsidian 社区插件**

  Obsidian 内装:Web Clipper、Bases(核心插件,默认有)、Smart Connections、Obsidian-Git。
  开启官方 CLI:Settings → General → Command line interface(design §1.4 引用)。

  验证:终端 `obsidian --version` 有输出(或该平台等价命令)。

- [ ] **Step 0.4: 建 Notion 数据库**

  Notion 内建(design §4.5.2 + §3.3):
  - `Projects`(Name, Type[阅读/工作/生活], Status, Start, Due, notion_ref, Owner)
  - `Tasks`(Name, Project→relation, Status, Due, Priority, source_ref)
  - `Habits`(Name, Type, Frequency, Streak, Last_done, History)
  - `待审核提案`(proposal_id, created_at, status, risk, action, target, sources, confidence, diff, review_decision, reviewed_at, applied_commit)

  记录各数据库的 database id(后续 config 要填)。

  验证:移动端能看到这些库、能加行。

- [ ] **Step 0.5: 配 Notion 官方 MCP + Smart Connections MCP**

  按 Notion 官方文档开 hosted MCP(OAuth scope 最小化,只授权上面四个库)。
  装 Smart Connections MCP server(design §2.4 引用的 gogogadgetbytes 版)。
  记录 Notion API token / MCP endpoint 到本地环境变量(不入 Git)。

  验证:用任一 Agent 宿主能 `search` Notion、能语义检索 vault。

---

## Task 1: 项目骨架与配置加载

**Files:**
- Create: `pyproject.toml`
- Create: `garden_gardener/__init__.py`
- Create: `garden_gardener/config.py`
- Create: `templates/gardener.config.yaml`
- Create: `tests/test_config.py`

- [ ] **Step 1.1: 写 pyproject.toml**

```toml
[project]
name = "knowledge-garden-gardener"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
    "httpx>=0.27",
]

[project.scripts]
garden = "garden_gardener.cli_entry:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 1.2: 写 templates/gardener.config.yaml**

内容抄 design §4.6 完整 config(含 risk_levels / operations / actors / hard_disabled / thresholds / access)。注意 `notion` 段补充从 Step 0.4/0.5 拿到的 database id:

```yaml
notion:
  proposal_database_id: "<填待审核提案库 id>"
  projects_database_id: "<填 Projects 库 id>"
  mcp_endpoint: "<填 Notion MCP endpoint>"
```

- [ ] **Step 1.3: 写失败测试 tests/test_config.py**

```python
import textwrap
from pathlib import Path
from garden_gardener.config import load_config, ConfigError

SAMPLE = textwrap.dedent("""
version: 0.1
risk_levels:
  L0: {auto: true, needs_review: false, confirm: false}
  L1: {auto: true, needs_review: false, confirm: false, log: commit}
  L2: {auto: false, needs_review: true, confirm: once, log: commit+notion}
  L3: {auto: false, needs_review: true, confirm: twice, log: commit+notion}
operations:
  append_raw: L0
  create_evergreen: L2
  delete_evergreen: L3
actors:
  manual_session: [L0, L1, L2, L3]
  scheduled_run: [L0, L1]
hard_disabled:
  - unsanctioned: create_evergreen
  - any: notion_delete
thresholds: {orphan_age_days: 7, confidence_min: 0.6, batch_l1_max: 50}
access: {preferred: cli, fallback: filesystem}
notion: {proposal_database_id: "db-1", projects_database_id: "db-2", mcp_endpoint: "http://x"}
""")

def test_load_config_parses_fields(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(SAMPLE, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.operations["create_evergreen"] == "L2"
    assert cfg.actors["scheduled_run"] == ["L0", "L1"]
    assert cfg.thresholds["orphan_age_days"] == 7

def test_load_config_rejects_missing_risk_level(tmp_path: Path):
    bad = tmp_path / "c.yaml"
    body = SAMPLE.replace("  create_evergreen: L2", "  create_evergreen: L9")
    bad.write_text(body, encoding="utf-8")
    try:
        load_config(bad)
        assert False, "should have raised"
    except ConfigError as e:
        assert "L9" in str(e)
```

- [ ] **Step 1.4: 跑测试确认失败**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: garden_gardener.config`

- [ ] **Step 1.5: 写 garden_gardener/__init__.py**

```python
"""knowledge-garden-gardener: Agent 当园丁,不当作者。"""
__version__ = "0.1.0"
```

- [ ] **Step 1.6: 写 garden_gardener/config.py**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml

@dataclass
class Config:
    raw: dict
    operations: dict
    actors: dict
    hard_disabled: list
    thresholds: dict
    access: dict
    notion: dict
    risk_levels: dict

    def risk_of(self, operation: str) -> str:
        if operation not in self.operations:
            raise ConfigError(f"unknown operation: {operation}")
        level = self.operations[operation]
        if level not in self.risk_levels:
            raise ConfigError(f"operation {operation} maps to unknown risk level {level}")
        return level

class ConfigError(Exception):
    pass

def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = ["risk_levels", "operations", "actors", "hard_disabled",
                "thresholds", "access", "notion"]
    for k in required:
        if k not in data:
            raise ConfigError(f"missing top-level key: {k}")
    cfg = Config(
        raw=data, risk_levels=data["risk_levels"], operations=data["operations"],
        actors=data["actors"], hard_disabled=data["hard_disabled"],
        thresholds=data["thresholds"], access=data["access"], notion=data["notion"],
    )
    # 校验所有 operation 映射的 risk level 都存在(触发 ConfigError)
    for op, lvl in cfg.operations.items():
        cfg.risk_of(op)
    return cfg
```

- [ ] **Step 1.7: 跑测试确认通过**

Run: `python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 1.8: Commit**

```bash
git add pyproject.toml garden_gardener/__init__.py garden_gardener/config.py templates/gardener.config.yaml tests/test_config.py
git commit -m "feat(config): 加载并校验 gardener.config.yaml"
```

---

## Task 2: 风险分级判定(纯函数,核心安全逻辑)

**Files:**
- Create: `garden_gardener/risk.py`
- Create: `tests/test_risk.py`

> 这是整个系统的安全闸——所有"能不能写、走哪条路"都过它。必须最先做、最严测。

- [ ] **Step 2.1: 写失败测试 tests/test_risk.py**

```python
import pytest
from garden_gardener.config import Config
from garden_gardener.risk import decide, Decision, Actor, SANCTIONED_OPS

def _cfg() -> Config:
    return Config(
        raw={},
        risk_levels={
            "L0": {"auto": True,  "needs_review": False, "confirm": False},
            "L1": {"auto": True,  "needs_review": False, "confirm": False},
            "L2": {"auto": False, "needs_review": True,  "confirm": "once"},
            "L3": {"auto": False, "needs_review": True,  "confirm": "twice"},
        },
        operations={"append_raw": "L0", "create_evergreen": "L2", "delete_evergreen": "L3"},
        actors={"manual_session": ["L0", "L1", "L2", "L3"], "scheduled_run": ["L0", "L1"]},
        hard_disabled=[{"unsanctioned": "create_evergreen"}, {"any": "notion_delete"}],
        thresholds={"confidence_min": 0.6},
        access={"preferred": "cli", "fallback": "filesystem"},
        notion={},
    )

def test_l0_auto_allowed_for_scheduled():
    d = decide(_cfg(), Actor.SCHEDULED, "append_raw", sanctioned=False)
    assert d == Decision.AUTO  # L0 自由

def test_l2_requires_sanction_unsanctioned_blocked():
    d = decide(_cfg(), Actor.SCHEDULED, "create_evergreen", sanctioned=False)
    assert d == Decision.BLOCKED  # 无 Notion approved 凭证,硬禁

def test_l2_sanctioned_allowed_when_manual():
    d = decide(_cfg(), Actor.MANUAL, "create_evergreen", sanctioned=True)
    assert d == Decision.APPLY  # 有凭证,手动会话,放行 apply

def test_scheduled_can_apply_sanctioned_l2():
    d = decide(_cfg(), Actor.SCHEDULED, "create_evergreen", sanctioned=True)
    assert d == Decision.APPLY  # 定时可应用已 Notion approved 的写

def test_actor_cannot_exceed_capability():
    # scheduled_run 的 actors 上限是 [L0,L1];未授权的 L3 即便 sanctioned 也拒
    d = decide(_cfg(), Actor.SCHEDULED, "delete_evergreen", sanctioned=True)
    assert d == Decision.BLOCKED

def test_notion_delete_always_blocked():
    # hard_disabled: any: notion_delete
    d = decide(_cfg(), Actor.MANUAL, "notion_delete", sanctioned=True)
    assert d == Decision.BLOCKED
```

- [ ] **Step 2.2: 跑测试确认失败**

Run: `python -m pytest tests/test_risk.py -v`
Expected: FAIL with `ModuleNotFoundError: garden_gardener.risk`

- [ ] **Step 2.3: 写 garden_gardener/risk.py**

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .config import Config

class Decision(Enum):
    AUTO = "auto"       # 直接写(含 L0 追加 / L1 自动+留 commit)
    APPLY = "apply"     # 有 Notion approved 凭证,执行 apply
    BLOCKED = "blocked" # 硬禁(无凭证写 L2+/超出 actor 能力/hard_disabled)

class Actor(Enum):
    MANUAL = "manual_session"
    SCHEDULED = "scheduled_run"

# 需要授权凭证(Notion approved)才允许 apply 的操作族
SANCTIONED_OPS = {"create_evergreen", "update_conclusion", "merge_notes",
                  "rename_evergreen", "move_evergreen", "delete_evergreen"}

def _is_hard_disabled(cfg: Config, operation: str) -> bool:
    for rule in cfg.hard_disabled:
        if "unsanctioned" in rule and rule["unsanctioned"] == operation:
            continue  # 此规则由 sanctioned 参数处理,不在这里硬禁
        if "any" in rule and rule["any"] == operation:
            return True
    return False

def decide(cfg: Config, actor: Actor, operation: str, sanctioned: bool) -> Decision:
    # 1. hard_disabled(any 类)直接拒
    if _is_hard_disabled(cfg, operation):
        return Decision.BLOCKED

    # 2. 查风险档
    risk = cfg.risk_of(operation)

    # 3. actor 能力上限检查
    allowed_levels = set(cfg.actors[actor.value])
    if risk not in allowed_levels:
        return Decision.BLOCKED

    risk_def = cfg.risk_levels[risk]

    # 4. 自动档(L0/L1)
    if risk_def["auto"]:
        return Decision.AUTO

    # 5. 需审批档(L2/L3):必须有 sanctioned 凭证
    if operation in SANCTIONED_OPS and not sanctioned:
        return Decision.BLOCKED
    return Decision.APPLY
```

- [ ] **Step 2.4: 跑测试确认通过**

Run: `python -m pytest tests/test_risk.py -v`
Expected: 6 passed

- [ ] **Step 2.5: Commit**

```bash
git add garden_gardener/risk.py tests/test_risk.py
git commit -m "feat(risk): WHO×WHAT 风险分级判定,无凭证写硬禁"
```

---

## Task 3: Frontmatter 读写(纯解析,无 vault 依赖)

**Files:**
- Create: `garden_gardener/frontmatter.py`
- Create: `tests/test_frontmatter.py`

- [ ] **Step 3.1: 写失败测试 tests/test_frontmatter.py**

```python
from garden_gardener.frontmatter import parse, dump

def test_parse_extracts_yaml_and_body():
    text = "---\nid: x\ntype: concept\n---\n# Title\nbody"
    fm, body = parse(text)
    assert fm == {"id": "x", "type": "concept"}
    assert body == "# Title\nbody"

def test_parse_no_frontmatter():
    fm, body = parse("just body")
    assert fm == {}
    assert body == "just body"

def test_dump_roundtrip():
    fm = {"id": "y", "tags": ["a", "b"]}
    text = dump(fm, "body here")
    fm2, body2 = parse(text)
    assert fm2 == fm
    assert body2 == "body here"
```

- [ ] **Step 3.2: 跑测试确认失败**

Run: `python -m pytest tests/test_frontmatter.py -v`
Expected: FAIL ModuleNotFoundError

- [ ] **Step 3.3: 写 garden_gardener/frontmatter.py**

```python
from __future__ import annotations
import yaml

DELIM = "---"

def parse(text: str) -> tuple[dict, str]:
    if not text.startswith(DELIM):
        return {}, text
    # 找第二个 ---
    rest = text[len(DELIM):]
    # 跳过换行
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find(f"\n{DELIM}")
    if end == -1:
        return {}, text
    yaml_block = rest[:end]
    body = rest[end + len(DELIM) + 1:].lstrip("\r\n")
    return yaml.safe_load(yaml_block) or {}, body

def dump(fm: dict, body: str) -> str:
    yaml_block = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"{DELIM}\n{yaml_block}\n{DELIM}\n{body}"
```

- [ ] **Step 3.4: 跑测试确认通过**

Run: `python -m pytest tests/test_frontmatter.py -v`
Expected: 3 passed

- [ ] **Step 3.5: Commit**

```bash
git add garden_gardener/frontmatter.py tests/test_frontmatter.py
git commit -m "feat(frontmatter): YAML frontmatter 解析与回写"
```

---

## Task 4: Vault 访问抽象层(CLI 优先 + filesystem 降级)

**Files:**
- Create: `garden_gardener/vault.py`
- Create: `tests/conftest.py`
- Create: `tests/test_vault.py`

> 关键:抽象层对外暴露 `read/read_glob/append/write/exists` 等,内部探测 CLI 不可用则降级 filesystem。filesystem 模式下行为可测(纯文件),CLI 模式由集成测试单独覆盖(本计划用 filesystem 默认)。

- [ ] **Step 4.1: 写 tests/conftest.py(共享 fixture)**

```python
import shutil
import subprocess
from pathlib import Path
import pytest

@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """一个空的临时 vault 目录,含 §3.1 骨架。"""
    for sub in ["_System/_Inbox", "_System/_AgentDrafts", "_System/_PendingProposals",
                "_System/_Reports", "_System/_Archive",
                "Concepts", "Notes", "References", "Index", "_Templates", "_Config"]:
        (tmp_path / sub).mkdir(parents=True)
    # git init 便于 apply 测试
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path

@pytest.fixture
def force_filesystem(monkeypatch):
    """强制 vault 走 filesystem 模式(不探测 CLI)。"""
    from garden_gardener import vault as v
    monkeypatch.setattr(v, "_cli_available", lambda *a, **k: False)
```

- [ ] **Step 4.2: 写失败测试 tests/test_vault.py**

```python
from pathlib import Path
from garden_gardener.vault import Vault

def test_filesystem_read_write(vault: Path, force_filesystem):
    v = Vault(vault)
    p = v.write("Concepts/foo.md", "---\nid: foo\n---\nhi", risk_level="L2")
    assert v.read("Concepts/foo.md") == "---\nid: foo\n---\nhi"

def test_filesystem_append_creates_if_missing(vault: Path, force_filesystem):
    v = Vault(vault)
    v.append("_System/_Inbox/n.md", "first\n", risk_level="L0")
    v.append("_System/_Inbox/n.md", "second\n", risk_level="L0")
    assert v.read("_System/_Inbox/n.md") == "first\nsecond\n"

def test_read_glob_lists_paths(vault: Path, force_filesystem):
    v = Vault(vault)
    v.write("Concepts/a.md", "x", risk_level="L2")
    v.write("Concepts/b.md", "y", risk_level="L2")
    paths = sorted(p.relative_to(v.root).as_posix() for p in v.read_glob("Concepts/*.md"))
    assert paths == ["Concepts/a.md", "Concepts/b.md"]
```

> 注:测试里 `write` 传 `risk_level` 但**不**传 `sanctioned`,因 filesystem fixture 下审计由 risk 模块把关——本任务暂让 Vault 不重复判定(判定在 apply.py 编排层做),Vault 只负责读写原语。此处 `risk_level` 仅记录到 run-log,不阻断。

- [ ] **Step 4.3: 跑测试确认失败**

Run: `python -m pytest tests/test_vault.py -v`
Expected: FAIL ModuleNotFoundError

- [ ] **Step 4.4: 写 garden_gardener/vault.py**

```python
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

class Vault:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.mode = "cli" if _cli_available() else "filesystem"

    # --- 路径安全:禁止写到 vault 外 ---
    def _resolve(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            if not str(p).startswith(str(self.root.resolve())):
                raise ValueError(f"path escapes vault: {rel}")
        return p

    def read(self, rel: str) -> str:
        return self._resolve(rel).read_text(encoding="utf-8")

    def read_glob(self, pattern: str) -> list[Path]:
        return sorted(self.root.glob(pattern))

    def exists(self, rel: str) -> bool:
        return self._resolve(rel).exists()

    def write(self, rel: str, content: str, *, risk_level: str = "L0") -> Path:
        p = self._resolve(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def append(self, rel: str, content: str, *, risk_level: str = "L0") -> Path:
        p = self._resolve(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return p

def _cli_available() -> bool:
    """探测 Obsidian CLI 是否可用。filesystem 测试用 monkeypatch 关掉。"""
    exe = shutil.which("obsidian")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False
```

- [ ] **Step 4.5: 跑测试确认通过**

Run: `python -m pytest tests/test_vault.py -v`
Expected: 3 passed

- [ ] **Step 4.6: Commit**

```bash
git add garden_gardener/vault.py tests/conftest.py tests/test_vault.py
git commit -m "feat(vault): 访问抽象层,CLI 优先 filesystem 降级"
```

---

## Task 5: Git 操作封装

**Files:**
- Create: `garden_gardener/gitutil.py`
- Create: `tests/test_gitutil.py`

> apply 流程依赖:pull(基于最新)、commit(带 gardener 前缀 + notion-id)、revert(回滚)。

- [ ] **Step 5.1: 写失败测试 tests/test_gitutil.py**

```python
import subprocess
from pathlib import Path
from garden_gardener.gitutil import Git

def test_commit_with_gardener_prefix(vault: Path):
    g = Git(vault)
    (vault / "a.md").write_text("x")
    sha = g.commit_all("L1", "backfill source on 2 notes")
    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=vault,
                         capture_output=True, text=True).stdout.strip()
    assert msg.startswith("gardener(L1)")
    assert "backfill source on 2 notes" in msg

def test_commit_includes_notion_id(vault: Path):
    g = Git(vault)
    (vault / "a.md").write_text("y")
    g.commit_all("L2", "create Concepts/X", notion_id="2026-06-28-001")
    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=vault,
                         capture_output=True, text=True).stdout
    assert "approved 2026-06-28-001" in msg

def test_revert_undoes_commit(vault: Path):
    g = Git(vault)
    (vault / "a.md").write_text("v1")
    sha = g.commit_all("L2", "x", notion_id="n1")
    (vault / "a.md").write_text("v2")
    g.commit_all("L2", "y", notion_id="n2")
    g.revert(sha)
    assert (vault / "a.md").read_text() == "v2"  # revert v1 不影响 v2? 见下注释
```

> 注 Step 5.1 第三个测试:`revert(sha_of_v1)` 会生成一个反向 commit,把 a.md 从 v1 状态……实际 v1 那次 commit 引入了 v1,revert 后该内容被反向应用。但因后续 v2 commit 覆盖了,revert v1 在干净线性历史上会尝试删 v1 内容→冲突或无操作。**这个测试语义有歧义**,修正为更清晰的:revert 最近一次 commit。

- [ ] **Step 5.2: 修正测试 test_revert**

```python
def test_revert_undoes_last_commit(vault: Path):
    g = Git(vault)
    (vault / "a.md").write_text("v1")
    sha = g.commit_all("L2", "create X", notion_id="n1")
    assert (vault / "a.md").read_text() == "v1"
    g.revert(sha)
    # revert 后 a.md 内容被撤销(文件回到 commit 前,即不存在)
    assert not (vault / "a.md").exists()
```

- [ ] **Step 5.3: 跑测试确认失败**

Run: `python -m pytest tests/test_gitutil.py -v`
Expected: FAIL ModuleNotFoundError

- [ ] **Step 5.4: 写 garden_gardener/gitutil.py**

```python
from __future__ import annotations
import subprocess
from pathlib import Path

class Git:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                              text=True, check=check)

    def pull(self) -> bool:
        """拉取最新。返回是否成功;失败由调用方决定中止。"""
        r = self._run("pull", "--rebase", check=False)
        return r.returncode == 0

    def commit_all(self, risk: str, summary: str, *, notion_id: str | None = None) -> str:
        msg = f"gardener({risk}): {summary}"
        if notion_id:
            msg += f" (approved {notion_id})"
        self._run("add", "-A")
        self._run("commit", "-m", msg)
        return self._run("rev-parse", "HEAD").stdout.strip()

    def revert(self, sha: str) -> None:
        self._run("revert", "--no-edit", sha)
```

- [ ] **Step 5.5: 跑测试确认通过**

Run: `python -m pytest tests/test_gitutil.py -v`
Expected: 3 passed

- [ ] **Step 5.6: Commit**

```bash
git add garden_gardener/gitutil.py tests/test_gitutil.py
git commit -m "feat(gitutil): pull/commit/revert 封装,带 gardener 前缀+notion-id"
```

---

## Task 6: Notion MCP 客户端封装(mock 化测试)

**Files:**
- Create: `garden_gardener/notion.py`
- Create: `tests/test_notion.py`

> Notion 交互全程 mock——不依赖真实网络。封装四类操作:建提案、轮询 approved、回写 applied_commit、查 Projects 状态(交互③)。

- [ ] **Step 6.1: 写失败测试 tests/test_notion.py**

```python
from garden_gardener.notion import NotionClient, Proposal

def test_create_proposal_calls_mcp(monkeypatch):
    calls = []
    def fake_post(endpoint, payload):
        calls.append(payload)
        return {"id": "page-1", "url": "http://n/page-1"}
    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    pid = client.create_proposal(Proposal(
        proposal_id="2026-06-28-001", risk="L2", action="create",
        target="Concepts/X.md", sources=["raw-1"], confidence=0.8, diff="+ new"))
    assert pid == "page-1"
    assert calls[0]["database_id"] == "db-1"
    assert calls[0]["properties"]["risk"] == "L2"

def test_poll_approved_returns_only_approved(monkeypatch):
    def fake_post(endpoint, payload):
        return {"results": [
            {"id": "p1", "properties": {"status": "approved", "proposal_id": "001"}},
            {"id": "p2", "properties": {"status": "pending", "proposal_id": "002"}},
        ]}
    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    approved = client.poll_approved()
    assert [a["id"] for a in approved] == ["p1"]

def test_write_applied_commit_updates_status(monkeypatch):
    calls = []
    def fake_post(endpoint, payload):
        calls.append((endpoint, payload))
        return {"ok": True}
    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    client.write_applied_commit("p1", "abc123")
    assert calls[0][0] == "update_page"
    assert calls[0][1]["page_id"] == "p1"
    assert calls[0][1]["properties"]["applied_commit"] == "abc123"
    assert calls[0][1]["properties"]["status"] == "applied"
```

- [ ] **Step 6.2: 跑测试确认失败**

Run: `python -m pytest tests/test_notion.py -v`
Expected: FAIL ModuleNotFoundError

- [ ] **Step 6.3: 写 garden_gardener/notion.py**

```python
from __future__ import annotations
from dataclasses import dataclass, asdict
import httpx

@dataclass
class Proposal:
    proposal_id: str
    risk: str
    action: str
    target: str
    sources: list[str]
    confidence: float
    diff: str

class NotionClient:
    def __init__(self, endpoint: str, proposal_db: str, projects_db: str,
                 *, post=None):
        self.endpoint = endpoint
        self.proposal_db = proposal_db
        self.projects_db = projects_db
        # post 可注入便于测试;默认用 httpx
        self._post = post or self._httpx_post

    def _httpx_post(self, tool: str, payload: dict) -> dict:
        r = httpx.post(f"{self.endpoint}/{tool}", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def create_proposal(self, p: Proposal) -> str:
        payload = {
            "database_id": self.proposal_db,
            "properties": {
                "proposal_id": p.proposal_id, "risk": p.risk, "action": p.action,
                "target": p.target, "sources": ",".join(p.sources),
                "confidence": p.confidence, "diff": p.diff, "status": "pending",
            },
        }
        resp = self._post("create_page", payload)
        return resp["id"]

    def poll_approved(self) -> list[dict]:
        resp = self._post("query_database", {
            "database_id": self.proposal_db,
            "filter": {"status": {"equals": "approved"}},
        })
        return resp.get("results", [])

    def write_applied_commit(self, page_id: str, commit_sha: str) -> None:
        self._post("update_page", {
            "page_id": page_id,
            "properties": {"status": "applied", "applied_commit": commit_sha},
        })

    def query_projects_activity(self) -> list[dict]:
        """交互③:只读查 Projects 本周状态变化。"""
        resp = self._post("query_database", {"database_id": self.projects_db})
        return resp.get("results", [])
```

- [ ] **Step 6.4: 跑测试确认通过**

Run: `python -m pytest tests/test_notion.py -v`
Expected: 3 passed

- [ ] **Step 6.5: Commit**

```bash
git add garden_gardener/notion.py tests/test_notion.py
git commit -m "feat(notion): MCP 客户端封装,提案/轮询/回写/查项目"
```

---

## Task 7: 只读审计逻辑

**Files:**
- Create: `garden_gardener/audit.py`
- Create: `tests/test_audit.py`

> 审计纯读,产出结构化报告 dict。基于 frontmatter `links` 字段 + 反向 grep 找孤岛;`last_reviewed_at` 找过时;`tags` 聚类找冲突候选(同 tag 多条 confidence 差异大)。

- [ ] **Step 7.1: 写失败测试 tests/test_audit.py**

```python
from datetime import date, timedelta
from garden_gardener.vault import Vault
from garden_gardener.frontmatter import dump
from garden_gardener.audit import audit, AuditReport

def _concept(vault, name, links=None, tags=None, reviewed=None, conf=0.8):
    fm = {"id": name, "type": "concept", "title": name, "links": links or [],
          "tags": tags or [], "confidence": conf, "last_reviewed_at": reviewed}
    Vault(vault).write(f"Concepts/{name}.md", dump(fm, "body"), risk_level="L2")

def test_find_orphans(vault, force_filesystem, monkeypatch):
    monkeypatch.setattr("garden_gardener.audit._today", lambda: date(2026, 6, 28))
    _concept(vault, "isolated", links=[], reviewed="2026-06-20")  # 无链+老
    _concept(vault, "linked", links=["[[other]]"], reviewed="2026-06-20")
    rep = audit(Vault(vault))
    assert "Concepts/isolated.md" in rep.orphans
    assert "Concepts/linked.md" not in rep.orphans

def test_find_stale(vault, force_filesystem, monkeypatch):
    monkeypatch.setattr("garden_gardener.audit._today", lambda: date(2026, 6, 28))
    old = (date(2026, 6, 28) - timedelta(days=100)).isoformat()
    _concept(vault, "old", links=["[[x]]"], reviewed=old)
    rep = audit(Vault(vault))
    assert "Concepts/old.md" in rep.stale

def test_inbox_pending(vault, force_filesystem):
    Vault(vault).write("_System/_Inbox/n1.md",
        dump({"id": "r1", "type": "raw", "status": "inbox"}, "raw"), risk_level="L0")
    rep = audit(Vault(vault))
    assert "_System/_Inbox/n1.md" in rep.inbox_pending
```

- [ ] **Step 7.2: 跑测试确认失败**

Run: `python -m pytest tests/test_audit.py -v`
Expected: FAIL ModuleNotFoundError

- [ ] **Step 7.3: 写 garden_gardener/audit.py**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from .vault import Vault
from .frontmatter import parse

def _today() -> date:
    return date.today()

@dataclass
class AuditReport:
    orphans: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)
    inbox_pending: list[str] = field(default_factory=list)

def audit(vault: Vault, *, orphan_age_days: int = 7, stale_days: int = 90) -> AuditReport:
    rep = AuditReport()
    today = _today()
    cutoff = today - timedelta(days=orphan_age_days)
    stale_cutoff = today - timedelta(days=stale_days)

    # 反向链接统计:收集所有 [[link]] 出现
    backlinks: dict[str, int] = {}
    evergreen: list[tuple[str, dict]] = []
    for p in vault.read_glob("Concepts/*.md") + vault.read_glob("Notes/*.md"):
        rel = p.relative_to(vault.root).as_posix()
        fm, body = parse(vault.read(rel))
        evergreen.append((rel, fm))
        for ln in fm.get("links", []) or []:
            # ln 形如 [[X]]
            name = ln.strip("[]")
            backlinks[name] = backlinks.get(name, 0) + 1

    for rel, fm in evergreen:
        links = fm.get("links", []) or []
        title = fm.get("title") or ""
        has_backlink = backlinks.get(title, 0) > 0
        # 孤岛:无 links 且无反向链接 且 创建/复核较老
        reviewed = fm.get("last_reviewed_at") or fm.get("created_at")
        is_old = _parse_date(reviewed) <= cutoff if reviewed else True
        if not links and not has_backlink and is_old:
            rep.orphans.append(rel)
        if reviewed and _parse_date(reviewed) <= stale_cutoff:
            rep.stale.append(rel)

    # Inbox 待处理
    for p in vault.read_glob("_System/_Inbox/*.md"):
        rel = p.relative_to(vault.root).as_posix()
        fm, _ = parse(vault.read(rel))
        if fm.get("status") == "inbox":
            rep.inbox_pending.append(rel)
    return rep

def _parse_date(s) -> date:
    if isinstance(s, date):
        return s
    return date.fromisoformat(str(s)[:10])
```

- [ ] **Step 7.4: 跑测试确认通过**

Run: `python -m pytest tests/test_audit.py -v`
Expected: 3 passed

- [ ] **Step 7.5: Commit**

```bash
git add garden_gardener/audit.py tests/test_audit.py
git commit -m "feat(audit): 只读审计,孤岛/过时/Inbox 待处理"
```

---

## Task 8: 提案生成 + 写 Notion(含降级暂存)

**Files:**
- Create: `garden_gardener/proposal.py`
- Create: `tests/test_proposal.py`

> 把审计结果转成提案,写 Notion;Notion 不可达则暂存 `_PendingProposals/`。**绝不直接 apply。**

- [ ] **Step 8.1: 写失败测试 tests/test_proposal.py**

```python
import json
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.audit import AuditReport
from garden_gardener.proposal import emit_proposals

def test_orphan_becomes_link_proposal(vault, force_filesystem):
    rep = AuditReport(orphans=["Concepts/isolated.md"])
    created = []
    def fake_post(tool, payload):
        created.append((tool, payload))
        return {"id": f"page-{len(created)}"}
    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    page_ids = emit_proposals(vault, client, rep, actor="manual_session")
    assert len(page_ids) == 1
    assert created[0][1]["properties"]["action"] == "link"
    assert created[0][1]["properties"]["risk"] == "L2"
    assert created[0][1]["properties"]["target"] == "Concepts/isolated.md"

def test_fallback_stores_locally_when_notion_fails(vault, force_filesystem):
    rep = AuditReport(orphans=["Concepts/x.md"])
    def fake_post(tool, payload):
        raise RuntimeError("notion down")
    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    page_ids = emit_proposals(vault, client, rep, actor="manual_session")
    assert page_ids == []  # 没成功入 Notion
    # 暂存到本地
    pending = list((vault.root / "_System/_PendingProposals").glob("*.json"))
    assert len(pending) == 1
    data = json.loads(pending[0].read_text(encoding="utf-8"))
    assert data["target"] == "Concepts/x.md"
```

- [ ] **Step 8.2: 跑测试确认失败**

Run: `python -m pytest tests/test_proposal.py -v`
Expected: FAIL ModuleNotFoundError

- [ ] **Step 8.3: 写 garden_gardener/proposal.py**

```python
from __future__ import annotations
import json
import time
from .vault import Vault
from .notion import NotionClient, Proposal
from .audit import AuditReport

def emit_proposals(vault: Vault, client: NotionClient, rep: AuditReport,
                   *, actor: str) -> list[str]:
    """把审计报告转成提案,写 Notion;失败暂存本地。返回成功入 Notion 的 page id。"""
    proposals = _from_audit(rep)
    page_ids: list[str] = []
    for prop in proposals:
        try:
            pid = client.create_proposal(prop)
            page_ids.append(pid)
        except Exception:
            _stash_locally(vault, prop)
    return page_ids

def _from_audit(rep: AuditReport) -> list[Proposal]:
    out: list[Proposal] = []
    ts = time.strftime("%Y-%m-%d")
    for i, target in enumerate(rep.orphans):
        out.append(Proposal(
            proposal_id=f"{ts}-{i+1:03d}", risk="L2", action="link",
            target=target, sources=[], confidence=0.5,
            diff="(建议补链:此笔记无链接,待智能匹配相关笔记)"))
    return out

def _stash_locally(vault: Vault, prop: Proposal) -> None:
    fname = f"{prop.proposal_id}-{prop.action}.json"
    path = vault.root / "_System/_PendingProposals" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prop.__dict__, ensure_ascii=False, indent=2),
                    encoding="utf-8")
```

- [ ] **Step 8.4: 跑测试确认通过**

Run: `python -m pytest tests/test_proposal.py -v`
Expected: 2 passed

- [ ] **Step 8.5: Commit**

```bash
git add garden_gardener/proposal.py tests/test_proposal.py
git commit -m "feat(proposal): 审计转提案,写 Notion 失败降级暂存"
```

---

## Task 9: Apply 编排(集成核心——轮询 approved → 写 → commit → 回写)

**Files:**
- Create: `garden_gardener/apply.py`
- Create: `tests/test_apply.py`

> 这是授权模型的执行端:只 apply Notion `approved` 的提案;每次 apply 经 risk.decide 校验;commit 带 notion-id;回写 applied_commit。无凭证写 = BLOCKED。

- [ ] **Step 9.1: 写失败测试 tests/test_apply.py**

```python
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.gitutil import Git
from garden_gardener.config import Config
from garden_gardener.apply import apply_approved, ApplyResult

def _cfg() -> Config:
    from garden_gardener.config import Config
    return Config(raw={}, risk_levels={
        "L0": {"auto": True}, "L1": {"auto": True},
        "L2": {"auto": False}, "L3": {"auto": False}},
        operations={"append_raw": "L0", "create_evergreen": "L2", "add_wikilink": "L1"},
        actors={"manual_session": ["L0","L1","L2","L3"], "scheduled_run": ["L0","L1"]},
        hard_disabled=[{"unsanctioned": "create_evergreen"}],
        thresholds={}, access={}, notion={})

def test_apply_create_writes_and_commits_and_writeback(vault, force_filesystem):
    # 模拟 Notion 返回一条 approved 的 create 提案
    def fake_post(tool, payload):
        if tool == "query_database":
            return {"results": [{
                "id": "p1",
                "properties": {"proposal_id": "001", "risk": "L2", "action": "create",
                               "target": "Concepts/New.md", "sources": "",
                               "confidence": 0.9, "diff": "# New\nbody",
                               "status": "approved"}}]}
        if tool == "update_page":
            return {"ok": True}
        return {}
    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    git = Git(vault)
    result = apply_approved(_cfg(), vault, client, git, actor="manual_session")
    assert result.applied == ["p1"]
    assert vault.exists("Concepts/New.md")
    # commit 带 notion proposal id
    import subprocess
    msg = subprocess.run(["git","log","-1","--pretty=%B"], cwd=vault,
                         capture_output=True, text=True).stdout
    assert "approved 001" in msg

def test_apply_blocked_when_unsanctioned(vault, force_filesystem):
    # 一条 create 提案但风险档在 scheduled actor 下:approved=True 但... 实际 sanctioned
    # 来自 Notion status=approved,故 sanctioned=True。改测:delete 在 scheduled 下 BLOCKED
    def fake_post(tool, payload):
        if tool == "query_database":
            return {"results": [{
                "id": "p1",
                "properties": {"proposal_id": "009", "risk": "L3", "action": "delete",
                               "target": "Concepts/X.md", "diff": "", "status": "approved"}}]}
        return {}
    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    git = Git(vault)
    result = apply_approved(_cfg(), vault, client, git, actor="scheduled_run")
    # scheduled actor 能力上限无 L3 → BLOCKED
    assert result.blocked == ["p1"]
    assert result.applied == []
```

- [ ] **Step 9.2: 跑测试确认失败**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL ModuleNotFoundError

- [ ] **Step 9.3: 写 garden_gardener/apply.py**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from .config import Config
from .vault import Vault
from .notion import NotionClient
from .gitutil import Git
from .risk import decide, Decision, Actor
from .frontmatter import dump

# action → 内部 operation 名(映射到 config.operations)
_ACTION_TO_OP = {
    "link": "add_wikilink",
    "create": "create_evergreen",
    "update": "update_conclusion",
    "delete": "delete_evergreen",
    "move": "move_evergreen",
    "rename": "rename_evergreen",
}

@dataclass
class ApplyResult:
    applied: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)

def apply_approved(cfg: Config, vault: Vault, client: NotionClient, git: Git,
                   *, actor: str) -> ApplyResult:
    res = ApplyResult()
    actor_enum = Actor(actor)
    approved = client.poll_approved()
    for item in approved:
        props = item["properties"]
        action = props.get("action")
        op = _ACTION_TO_OP.get(action, action)
        # sanctioned=True,因为来自 Notion status=approved
        d = decide(cfg, actor_enum, op, sanctioned=True)
        if d == Decision.BLOCKED:
            res.blocked.append(item["id"])
            continue
        # 执行写入(简化:create 写 diff 全文;link 暂记 needs desktop review)
        target = props["target"]
        if action == "create":
            fm = {"id": props.get("proposal_id"), "type": "concept",
                  "title": target, "status": "evergreen",
                  "sources": props.get("sources", "").split(",") if props.get("sources") else [],
                  "confidence": props.get("confidence", 0.5)}
            vault.write(target, dump(fm, props.get("diff", "")), risk_level="L2")
        sha = git.commit_all(cfg.risk_of(op), f"{action} {target}",
                             notion_id=props.get("proposal_id"))
        client.write_applied_commit(item["id"], sha)
        res.applied.append(item["id"])
    return res
```

- [ ] **Step 9.4: 跑测试确认通过**

Run: `python -m pytest tests/test_apply.py -v`
Expected: 2 passed

- [ ] **Step 9.5: Commit**

```bash
git add garden_gardener/apply.py tests/test_apply.py
git commit -m "feat(apply): 轮询 approved→写→commit→回写,无凭证/超能力硬禁"
```

---

## Task 10: CLI 入口 + SKILL.md

**Files:**
- Create: `garden_gardener/cli_entry.py`
- Create: `SKILL.md`

> 薄壳:解析子命令 → 组装 config/vault/notion/git → 调对应模块。SKILL.md 告诉 Agent 宿主各入口怎么调。

- [ ] **Step 10.1: 写 garden_gardener/cli_entry.py**

```python
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .config import load_config
from .vault import Vault
from .notion import NotionClient
from .gitutil import Git
from .audit import audit
from .proposal import emit_proposals
from .apply import apply_approved

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="garden")
    p.add_argument("--config", default="_Config/gardener.config.yaml")
    p.add_argument("--vault", default=".")
    p.add_argument("--actor", default="manual_session",
                   choices=["manual_session", "scheduled_run"])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("weekly-audit")
    sub.add_parser("apply-approved")
    sub.add_parser("triage-inbox")

    args = p.parse_args(argv)
    cfg = load_config(Path(args.config))
    vault = Vault(Path(args.vault))
    git = Git(Path(args.vault))
    client = NotionClient(
        cfg.notion["mcp_endpoint"],
        cfg.notion["proposal_database_id"],
        cfg.notion["projects_database_id"],
    )

    if args.cmd == "weekly-audit":
        if not git.pull():
            print("ABORT: git pull failed; 不基于脏数据跑", file=sys.stderr)
            return 2
        rep = audit(vault, orphan_age_days=cfg.thresholds["orphan_age_days"],
                    stale_days=cfg.thresholds.get("stale_review_days", 90))
        emit_proposals(vault, client, rep, actor=args.actor)
        # L1 自动 apply 略(一期可选,见 SKILL.md)
        print(f"audit done: {len(rep.orphans)} orphans, {len(rep.stale)} stale, "
              f"{len(rep.inbox_pending)} inbox")
        return 0

    if args.cmd == "apply-approved":
        if not git.pull():
            print("ABORT: git pull failed", file=sys.stderr)
            return 2
        res = apply_approved(cfg, vault, client, git, actor=args.actor)
        print(f"applied {len(res.applied)}, blocked {len(res.blocked)}")
        return 0

    if args.cmd == "triage-inbox":
        rep = audit(vault)
        print(f"{len(rep.inbox_pending)} inbox items pending triage")
        return 0
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 10.2: 写 SKILL.md**

```markdown
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
所有入口经 `python -m garden_gardener.cli_entry`(或装后的 `garden`)。

### weekly-audit
只读审计 vault(孤岛/过时/Inbox),生成提案写入 Notion「待审核提案」库。
`garden --config <vault>/_Config/gardener.config.yaml --vault <vault> weekly-audit`
**不写 Evergreen**(只产提案)。L1 自动 apply 可选开启。

### apply-approved
轮询 Notion `status=approved` 的提案,apply 到 Evergreen + git commit(带 notion-id)+ 回写 applied_commit。
`garden ... --actor scheduled_run apply-approved`
定时场景用 `--actor scheduled_run`(能力受限)。

### triage-inbox
列出 `_System/_Inbox/` 待处理 Raw。

## 红线(不可违反)
- 无 Notion `approved` 凭证绝不写 Evergreen L2+ 操作(create/update/delete/move/rename)。
- Notion 删除操作任何情况禁用。
- git pull 失败必须中止本轮,不基于脏数据跑。

## 授权模型
见 `gardener.config.yaml` 的 operations/actors/hard_disabled。风险档 L0-L3,详见 `docs/knowledge-garden-design.md` §4。
```

- [ ] **Step 10.3: 冒烟测试 CLI(用临时 vault + mock notion 不现实,改为 import 测试)**

Run: `python -c "from garden_gardener.cli_entry import main; print('import ok')"`
Expected: `import ok`

- [ ] **Step 10.4: Commit**

```bash
git add garden_gardener/cli_entry.py SKILL.md
git commit -m "feat(cli+skill): CLI 入口动词 + SKILL.md 说明"
```

---

## Task 11: 全量测试 + 文档收尾

- [ ] **Step 11.1: 跑全量测试**

Run: `python -m pytest -v`
Expected: 所有 test_*.py 全 passed(config 2 + risk 6 + frontmatter 3 + vault 3 + gitutil 3 + notion 3 + audit 3 + proposal 2 + apply 2 = 27 passed)

- [ ] **Step 11.2: 更新 README 加运行说明**

在 `README.md` 末尾追加:
```markdown
## 运行

```bash
pip install -e .
# 审计(在 vault 根目录)
garden --config _Config/gardener.config.yaml --vault . weekly-audit
# 应用已批准提案
garden --config _Config/gardener.config.yaml --vault . apply-approved
```

测试:`python -m pytest -v`
```

- [ ] **Step 11.3: Commit**

```bash
git add README.md
git commit -m "docs: README 加运行与测试说明"
```

---

## Self-Review 自审

**1. Spec coverage(对照 design 各节)**:
- §2.2 风险分级 → Task 2 ✅
- §2.3 异步审批循环 → Task 8(写提案)+ Task 9(apply)+ Task 10(weekly-audit/apply-approved)✅
- §3.3 frontmatter schema → Task 3 ✅
- §4 权限三维 → Task 2(risk)+ Task 9(apply 编排校验)✅
- §5.4 降级访问层 → Task 4 ✅
- §5.6 跨系统审计链 → Task 5(git commit 带 notion-id)+ Task 9(回写 applied_commit)✅
- §5.7 失败处理(git pull 失败中止)→ Task 10 weekly-audit/apply-approved 入口 ✅
- §6.2 阶段 0 地基 → Task 0 ✅
- §6.3 阶段 1 → Task 1-11 ✅

**已知未覆盖(二期/可选,记于此供后续)**:
- L1 自动 apply 批量(Task 10 weekly-audit 里标"可选")——一期可由 apply-approved 手动触发替代
- 周报生成入 Notion 周报队列——Task 8 仅写提案,周报队列待二期或单独 task
- 冲突检测(audit.conflicts 未实现算法)——Task 7 留了字段未填,标注后续
- Smart Connections 语义检索接入——filesystem 降级下未用,待编辑节点集成

**2. Placeholder scan**:无 TBD/TODO;Step 11.2 README 片段完整。✅

**3. Type consistency**:
- `Proposal` 在 notion.py 定义,proposal.py/apply.py 用同一 dataclass ✅
- `decide()` 签名 `(cfg, actor, operation, sanctioned)` 在 risk.py 定义,test_risk 与 apply.py 调用一致 ✅
- `apply_approved` 签名 `(cfg, vault, client, git, *, actor)` 一致 ✅
- `_ACTION_TO_OP` 映射覆盖 audit 产出的 action(link/create)✅

无修复项。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-28-knowledge-garden-mvp.md`. Two execution options:

**1. Subagent-Driven (recommended)** - 每个 Task 派一个新 subagent 实现,任务间两阶段 review,快速迭代。

**2. Inline Execution** - 在当前会话用 executing-plans 批量执行,带检查点 review。

Which approach?
