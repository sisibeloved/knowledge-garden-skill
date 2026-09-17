from datetime import date, timedelta
from garden_gardener.vault import Vault
from garden_gardener.frontmatter import dump
from garden_gardener.audit import audit


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


def test_nested_subdir_notes_are_audited(vault, force_filesystem, monkeypatch):
    """多级分类:Concepts/子目录/ 下的笔记同样被审计(递归 glob)。"""
    monkeypatch.setattr("garden_gardener.audit._today", lambda: date(2026, 6, 28))
    v = Vault(vault)
    fm = {"id": "x", "type": "concept", "title": "嵌套孤岛", "links": [],
          "last_reviewed_at": "2026-06-20"}
    v.write("Concepts/Kunpeng/芯片概念/嵌套孤岛.md", dump(fm, "body"), risk_level="L2")
    v.write("Notes/工作/嵌套笔记.md",
            dump({"title": "嵌套笔记", "links": ["[[x]]"],
                  "last_reviewed_at": "2026-06-20"}, "b"), risk_level="L2")
    rep = audit(v)
    assert "Concepts/Kunpeng/芯片概念/嵌套孤岛.md" in rep.orphans
    assert "Notes/工作/嵌套笔记.md" in {o for o in rep.orphans} or \
        "Notes/工作/嵌套笔记.md" not in rep.orphans  # 有 links → 非 orphan
    assert "Notes/工作/嵌套笔记.md" not in rep.orphans


def test_backlink_matched_by_filename_stem(vault, force_filesystem, monkeypatch):
    """双链用文件名(≠title)指向时,被指向笔记不算孤岛。"""
    monkeypatch.setattr("garden_gardener.audit._today", lambda: date(2026, 6, 28))
    v = Vault(vault)
    # linker 以文件名链到 refinement.md
    v.write("Concepts/linker.md",
            dump({"title": "linker", "links": ["[[refinement]]"],
                  "last_reviewed_at": "2026-06-20"}, "b"), risk_level="L2")
    # target 的 title 与文件名不同;无自身 links
    v.write("Concepts/refinement.md",
            dump({"title": "类型精化(refinement)", "links": [],
                  "last_reviewed_at": "2026-06-20"}, "b"), risk_level="L2")
    rep = audit(v)
    assert "Concepts/refinement.md" not in rep.orphans  # 文件名反链命中
    assert "Concepts/linker.md" not in rep.orphans
