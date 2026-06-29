import json
from pathlib import Path
from garden_gardener.init_plugins import (
    REQUIRED_PLUGINS, write_plugin_enable_list, install_instructions
)


def test_required_plugins_cover_core_needs():
    names = {p["id"] for p in REQUIRED_PLUGINS}
    # 三大核心:同步、剪藏、语义检索
    assert "obsidian-git" in names
    assert "smart-connections" in names
    # web-clipper 是官方核心,不在 community-plugins.json,单独处理


def test_write_enable_list_creates_obsidian_config(tmp_path: Path):
    write_plugin_enable_list(tmp_path)
    cfg = tmp_path / ".obsidian" / "community-plugins.json"
    assert cfg.exists()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert "obsidian-git" in data
    assert "smart-connections" in data


def test_write_enable_list_idempotent_merges(tmp_path: Path):
    # 用户已启用了别的插件 → 合并不覆盖
    obs = tmp_path / ".obsidian"
    obs.mkdir()
    (obs / "community-plugins.json").write_text(json.dumps(["my-existing-plugin"]))
    write_plugin_enable_list(tmp_path)
    data = json.loads((obs / "community-plugins.json").read_text(encoding="utf-8"))
    assert "my-existing-plugin" in data
    assert "obsidian-git" in data


def test_install_instructions_mention_manual_step(tmp_path: Path):
    # 因为 CLI 不能装插件,说明里必须提示用户:清单已生成,需在 Obsidian 内实际安装
    text = install_instructions(tmp_path)
    assert "Obsidian" in text  # 提示在 Obsidian 内操作
    assert "community-plugins" in text or "第三方插件" in text
