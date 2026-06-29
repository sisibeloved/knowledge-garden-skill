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
