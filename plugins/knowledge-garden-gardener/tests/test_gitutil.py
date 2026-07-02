import subprocess
from garden_gardener.gitutil import Git


def test_commit_with_gardener_prefix(vault):
    g = Git(vault)
    (vault / "a.md").write_text("x")
    g.commit_all("L1", "backfill source on 2 notes")
    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=vault,
                         capture_output=True, text=True).stdout.strip()
    assert msg.startswith("gardener(L1)")
    assert "backfill source on 2 notes" in msg


def test_commit_includes_notion_id(vault):
    g = Git(vault)
    (vault / "a.md").write_text("y")
    g.commit_all("L2", "create Concepts/X", notion_id="2026-06-28-001")
    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=vault,
                         capture_output=True, text=True).stdout
    assert "approved 2026-06-28-001" in msg


def test_revert_undoes_last_commit(vault):
    g = Git(vault)
    (vault / "a.md").write_text("v1")
    sha = g.commit_all("L2", "create X", notion_id="n1")
    assert (vault / "a.md").read_text() == "v1"
    g.revert(sha)
    # revert 后该 commit 引入的内容被反向应用,a.md 回到不存在
    assert not (vault / "a.md").exists()
