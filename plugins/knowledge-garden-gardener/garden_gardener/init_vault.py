from __future__ import annotations
from pathlib import Path

# §3.1 vault 目录骨架
VAULT_DIRS = [
    "_System/_Inbox", "_System/_AgentDrafts", "_System/_PendingProposals",
    "_System/_Reports", "_System/_Archive",
    "Concepts", "Notes", "References", "Index", "_Templates", "_Config",
]

# §3.6 .gitignore 内容
GITIGNORE_BODY = """\
# Obsidian 本地状态(不进 Git,避免多机冲突)
.obsidian/workspace*.json
.obsidian/plugins/*/data.json
*.cache
_Trash/
"""


def init_vault_skeleton(root: Path) -> None:
    """建 vault 目录骨架 + .gitignore + 各目录 .gitkeep。幂等:已存在的不覆盖。

    不做 git init(由 init 编排层决定,便于测试隔离)。
    """
    root = Path(root)
    # 目录
    for rel in VAULT_DIRS:
        d = root / rel
        d.mkdir(parents=True, exist_ok=True)
        # .gitkeep 让空目录能被 git 跟踪
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.touch()
    # .gitignore:已存在则不覆盖(用户可能有自定义)
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE_BODY, encoding="utf-8")
