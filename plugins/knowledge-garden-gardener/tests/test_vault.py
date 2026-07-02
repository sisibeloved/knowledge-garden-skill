from pathlib import Path
from garden_gardener.vault import Vault


def test_filesystem_read_write(vault: Path, force_filesystem):
    v = Vault(vault)
    v.write("Concepts/foo.md", "---\nid: foo\n---\nhi", risk_level="L2")
    assert v.read("Concepts/foo.md") == "---\nid: foo\n---\nhi"


def test_filesystem_append_creates_if_missing(vault: Path, force_filesystem):
    v = Vault(vault)
    v.append("_System/_Inbox/n.md", "first\n", risk_level="L0")
    v.append("_System/_Inbox/n.md", "second\n", risk_level="L0")
    assert v.read("_System/_Inbox/n.md") == "first\nsecond\n"


def test_read_glob_lists_paths(vault: Path, force_filesystem):
    v = Vault(vault)
    v.write("Concepts/a.md", "x", risk_level="L2")
    v.write("Concepts/b.md", "y", risk_level="L2")
    paths = sorted(p.relative_to(v.root).as_posix() for p in v.read_glob("Concepts/*.md"))
    assert paths == ["Concepts/a.md", "Concepts/b.md"]


def test_write_rejects_path_escape(vault: Path, force_filesystem):
    v = Vault(vault)
    import pytest
    with pytest.raises(ValueError):
        v.write("../../etc/evil.md", "x", risk_level="L0")
