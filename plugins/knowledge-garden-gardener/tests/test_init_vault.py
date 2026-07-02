from pathlib import Path
from garden_gardener.init_vault import init_vault_skeleton, VAULT_DIRS, GITIGNORE_BODY

REQUIRED_DIRS = [
    "_System/_Inbox", "_System/_AgentDrafts", "_System/_PendingProposals",
    "_System/_Reports", "_System/_Archive",
    "Concepts", "Notes", "References", "Index", "_Templates", "_Config",
]


def test_creates_all_directories(tmp_path: Path):
    init_vault_skeleton(tmp_path)
    for d in REQUIRED_DIRS:
        assert (tmp_path / d).is_dir(), f"missing {d}"


def test_writes_gitignore(tmp_path: Path):
    init_vault_skeleton(tmp_path)
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "workspace*.json" in gi
    assert "_Trash/" in gi


def test_writes_keepfiles_so_dirs_tracked_by_git(tmp_path: Path):
    init_vault_skeleton(tmp_path)
    for d in REQUIRED_DIRS:
        assert (tmp_path / d / ".gitkeep").exists(), f"no .gitkeep in {d}"


def test_idempotent_rerun_does_not_error(tmp_path: Path):
    init_vault_skeleton(tmp_path)
    # 第二次跑不应抛错,且不破坏已有内容
    (tmp_path / "Concepts" / "existing.md").write_text("keep me")
    init_vault_skeleton(tmp_path)
    assert (tmp_path / "Concepts" / "existing.md").read_text() == "keep me"


def test_does_not_overwrite_existing_gitignore(tmp_path: Path):
    # 用户已有自定义 .gitignore → 不覆盖
    (tmp_path / ".gitignore").write_text("my-custom-rule\n")
    init_vault_skeleton(tmp_path)
    assert "my-custom-rule" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
