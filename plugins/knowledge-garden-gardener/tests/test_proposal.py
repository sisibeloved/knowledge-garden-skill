import json
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.audit import AuditReport
from garden_gardener.proposal import emit_proposals


def test_orphan_becomes_link_proposal(vault, force_filesystem):
    rep = AuditReport(orphans=["Concepts/isolated.md"])
    created = []

    def fake_post(tool, payload):
        created.append((tool, payload))
        return {"id": f"page-{len(created)}"}

    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    page_ids = emit_proposals(Vault(vault), client, rep, actor="manual_session")
    assert len(page_ids) == 1
    assert created[0][1]["properties"]["action"] == "link"
    assert created[0][1]["properties"]["risk"] == "L2"
    assert created[0][1]["properties"]["target"] == "Concepts/isolated.md"


def test_fallback_stores_locally_when_notion_fails(vault, force_filesystem):
    rep = AuditReport(orphans=["Concepts/x.md"])

    def fake_post(tool, payload):
        raise RuntimeError("notion down")

    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    v = Vault(vault)
    page_ids = emit_proposals(v, client, rep, actor="manual_session")
    assert page_ids == []  # 没成功入 Notion
    # 暂存到本地 _PendingProposals/
    pending = list((v.root / "_System/_PendingProposals").glob("*.json"))
    assert len(pending) == 1
    data = json.loads(pending[0].read_text(encoding="utf-8"))
    assert data["target"] == "Concepts/x.md"
