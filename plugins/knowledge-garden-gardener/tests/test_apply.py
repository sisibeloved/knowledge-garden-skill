import subprocess
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.gitutil import Git
from garden_gardener.config import Config
from garden_gardener.apply import apply_approved


def _cfg() -> Config:
    return Config(
        raw={},
        risk_levels={
            "L0": {"auto": True}, "L1": {"auto": True},
            "L2": {"auto": False}, "L3": {"auto": False},
        },
        operations={"append_raw": "L0", "create_evergreen": "L2",
                    "add_wikilink": "L1", "delete_evergreen": "L3"},
        actors={"manual_session": ["L0", "L1", "L2", "L3"],
                "scheduled_run": ["L0", "L1"]},
        hard_disabled=[{"unsanctioned": "create_evergreen"},
                       {"any": "notion_delete"}],
        thresholds={}, access={}, notion={},
    )


def test_apply_create_writes_and_commits_and_writeback(vault, force_filesystem):
    # 模拟 Notion 返回一条 approved 的 create 提案
    def fake_post(tool, payload):
        if tool == "query_database":
            return {"results": [{
                "id": "p1",
                "properties": {"proposal_id": "001", "risk": "L2", "action": "create",
                               "target": "Concepts/New.md", "sources": "",
                               "confidence": 0.9, "diff": "# New\nbody",
                               "status": "approved"}}]}
        if tool == "update_page":
            return {"ok": True}
        return {}

    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    v = Vault(vault)
    git = Git(vault)
    result = apply_approved(_cfg(), v, client, git, actor="manual_session")
    assert result.applied == ["p1"]
    assert v.exists("Concepts/New.md")
    # commit 带 notion proposal id
    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=vault,
                         capture_output=True, text=True).stdout
    assert "approved 001" in msg


def test_apply_blocked_when_l3_on_scheduled(vault, force_filesystem):
    # delete(L3) 即便 sanctioned,在 scheduled actor 下也 BLOCKED(破坏性需人在场)
    def fake_post(tool, payload):
        if tool == "query_database":
            return {"results": [{
                "id": "p1",
                "properties": {"proposal_id": "009", "risk": "L3", "action": "delete",
                               "target": "Concepts/X.md", "diff": "",
                               "status": "approved"}}]}
        return {}

    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    v = Vault(vault)
    git = Git(vault)
    result = apply_approved(_cfg(), v, client, git, actor="scheduled_run")
    assert result.blocked == ["p1"]
    assert result.applied == []
    assert not v.exists("Concepts/X.md")  # 没写
