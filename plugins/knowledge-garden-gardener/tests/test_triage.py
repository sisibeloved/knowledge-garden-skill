"""triage-inbox 归类建议测试。"""
from garden_gardener.vault import Vault
from garden_gardener.frontmatter import dump
from garden_gardener.triage import suggest


def _inbox(vault, name, fm, body="x"):
    Vault(vault).write(f"_System/_Inbox/{name}", dump(fm, body), risk_level="L0")


def test_suggest_task_candidate(vault, force_filesystem):
    _inbox(vault, "a.md", {"type": "task_candidate", "status": "inbox"},
           "明天开会")
    s = suggest(Vault(vault))
    assert len(s) == 1
    assert s[0].action == "promote_to_task"
    assert "Notion Task" in s[0].suggestion


def test_suggest_reference_when_url(vault, force_filesystem):
    _inbox(vault, "b.md", {"type": "raw", "status": "inbox"},
           "见 https://arxiv.org/xxx")
    s = suggest(Vault(vault))
    assert s[0].action == "promote_to_reference"


def test_suggest_evergreen_for_concept(vault, force_filesystem):
    _inbox(vault, "c.md", {"type": "raw", "status": "inbox"}, "RAG 检索增强")
    s = suggest(Vault(vault))
    assert s[0].action == "promote_to_evergreen"


def test_suggest_skips_non_inbox_status(vault, force_filesystem):
    _inbox(vault, "d.md", {"type": "raw", "status": "processed"}, "x")
    _inbox(vault, "e.md", {"type": "raw", "status": "inbox"}, "y")
    s = suggest(Vault(vault))
    assert len(s) == 1  # 只列 status=inbox 的
    assert s[0].inbox_rel.endswith("e.md")


def test_suggest_empty_when_no_inbox(vault, force_filesystem):
    assert suggest(Vault(vault)) == []
