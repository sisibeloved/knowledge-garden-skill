from __future__ import annotations
import json
from pathlib import Path

# 园丁依赖的社区插件(官方 CLI 不支持 plugin:install,故只能生成启用清单 +
# 指引;实际安装仍需在 Obsidian GUI 内,这是 Obsidian 的硬约束,非本方案限制)。
REQUIRED_PLUGINS = [
    {
        "id": "obsidian-git",
        "name": "Obsidian Git",
        "purpose": "多机同步(Git),自动 commit/pull",
    },
    {
        "id": "smart-connections",
        "name": " Smart Connections",
        "purpose": "本地 embedding 语义检索,供园丁找相关笔记",
    },
]
# 注意:Web Clipper 是 Obsidian 官方核心插件(非社区插件),在 GUI 内单独启用,
# 不进 community-plugins.json。

ENABLE_LIST_REL = ".obsidian/community-plugins.json"


def write_plugin_enable_list(vault_root: Path) -> Path:
    """生成/合并 .obsidian/community-plugins.json 启用清单。幂等:合并已有清单。"""
    obs = Path(vault_root) / ".obsidian"
    obs.mkdir(parents=True, exist_ok=True)
    cfg = obs / "community-plugins.json"

    existing: list[str] = []
    if cfg.exists():
        try:
            existing = json.loads(cfg.read_text(encoding="utf-8")) or []
        except (json.JSONDecodeError, ValueError):
            existing = []

    wanted = {p["id"] for p in REQUIRED_PLUGINS}
    merged = list(dict.fromkeys(existing + sorted(wanted)))  # 去重保序
    cfg.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def install_instructions(vault_root: Path) -> str:
    """返回人类可读的安装指引(因 CLI 无法装插件,这步必须人工在 GUI 完成)。"""
    return (
        "插件启用清单已写入 .obsidian/community-plugins.json。\n"
        "但 Obsidian 官方 CLI 不支持安装插件,需手动完成:\n"
        "  1. 打开 Obsidian → 设置 → 第三方插件(Community plugins)\n"
        "  2. 关闭“安全模式”,依次浏览安装:Obsidian Git、Smart Connections\n"
        "  3. Web Clipper 是官方核心插件:设置 → 核心插件 → 启用 Web Clipper\n"
        "  4. 安装后重启 Obsidian,清单里的插件会自动启用\n"
        f"清单内容:{[p['id'] for p in REQUIRED_PLUGINS]}"
    )
