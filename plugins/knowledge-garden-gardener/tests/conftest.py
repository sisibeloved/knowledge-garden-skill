import subprocess
from pathlib import Path
import pytest


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """一个空的临时 vault 目录,含 §3.1 骨架,并 git init 便于 apply 测试。"""
    for sub in [
        "_System/_Inbox", "_System/_AgentDrafts", "_System/_PendingProposals",
        "_System/_Reports", "_System/_Archive",
        "Concepts", "Notes", "References", "Index", "_Templates", "_Config",
    ]:
        (tmp_path / sub).mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def force_filesystem(monkeypatch):
    """强制 vault 走 filesystem 模式(不探测 Obsidian CLI)。"""
    from garden_gardener import vault as v
    monkeypatch.setattr(v, "_cli_available", lambda *a, **k: False)
