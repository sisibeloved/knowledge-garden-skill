"""验证插件 marketplace 结构完整性。

防止重构后目录结构被意外破坏。参考 cpython-optimize-skill 的 validate_skill_layout.py 模式。
"""
import json
from pathlib import Path

# 仓库根(从 tests/test_layout.py 上溯 4 层:tests → plugin → plugins → repo root)
ROOT = Path(__file__).resolve().parents[3]


def test_claude_marketplace_exists():
    p = ROOT / ".claude-plugin" / "marketplace.json"
    assert p.exists(), f"missing Claude Code marketplace: {p}"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["name"], "marketplace.json missing name"
    assert len(data["plugins"]) >= 1
    assert data["plugins"][0]["name"] == "knowledge-garden-gardener"


def test_codex_marketplace_exists():
    p = ROOT / ".agents" / "plugins" / "marketplace.json"
    assert p.exists(), f"missing Codex marketplace: {p}"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["name"], "marketplace.json missing name"
    assert len(data["plugins"]) >= 1


def test_plugin_layout():
    base = ROOT / "plugins" / "knowledge-garden-gardener"
    # 双宿主元数据
    assert (base / ".claude-plugin" / "plugin.json").exists()
    assert (base / ".codex-plugin" / "plugin.json").exists()
    # package.json
    assert (base / "package.json").exists()
    # 入口 router skill
    assert (base / "skills" / "using-garden" / "SKILL.md").exists()
    # Python CLI 主体
    assert (base / "garden_gardener" / "cli_entry.py").exists()
    # 配置模板
    assert (base / "templates" / "gardener.config.yaml").exists()
    # CHANGELOG
    assert (base / "CHANGELOG.md").exists()


def test_versions_aligned():
    """plugin.json / package.json / CHANGELOG 版本应对齐。"""
    base = ROOT / "plugins" / "knowledge-garden-gardener"
    cc = json.loads((base / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    cx = json.loads((base / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    pkg = json.loads((base / "package.json").read_text(encoding="utf-8"))
    assert cc["version"] == cx["version"] == pkg["version"], "version misaligned"
    # CHANGELOG 最新版本号应匹配
    log = (base / "CHANGELOG.md").read_text(encoding="utf-8")
    assert cc["version"] in log, f"version {cc['version']} not in CHANGELOG"


def test_repo_docs_present():
    """仓库级文档应在根 docs/。"""
    assert (ROOT / "docs" / "knowledge-garden-design.md").exists()
    assert (ROOT / "docs" / "agent-adapters.md").exists()
