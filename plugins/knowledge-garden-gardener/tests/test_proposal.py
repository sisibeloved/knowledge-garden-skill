import json
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.audit import AuditReport
from garden_gardener.proposal import emit_proposals


def test_orphan_becomes_link_proposal(vault, force_filesystem):
    rep = AuditReport(orphans=["Concepts/isolated.md"])
    created = []

    def fake_send(method, path, json=None):
        created.append((method, path, json))
        return {"id": f"page-{len(created)}"}

    client = NotionClient(proposal_db="db-1", projects_db="db-2", send=fake_send)
    page_ids = emit_proposals(Vault(vault), client, rep, actor="manual_session")
    assert len(page_ids) == 1
    payload = created[0][2]
    assert payload["parent"] == {"database_id": "db-1"}
    props = payload["properties"]
    # 类型化属性:select.name / rich_text.content
    assert props["action"] == {"select": {"name": "link"}}
    assert props["risk"] == {"select": {"name": "L2"}}
    assert props["target"]["rich_text"][0]["text"]["content"] == "Concepts/isolated.md"


def test_fallback_stores_locally_when_notion_fails(vault, force_filesystem):
    rep = AuditReport(orphans=["Concepts/x.md"])

    def fake_send(method, path, json=None):
        raise RuntimeError("notion down")

    client = NotionClient(proposal_db="db-1", projects_db="db-2", send=fake_send)
    v = Vault(vault)
    page_ids = emit_proposals(v, client, rep, actor="manual_session")
    assert page_ids == []  # 没成功入 Notion
    # 暂存到本地 _PendingProposals/
    pending = list((v.root / "_System/_PendingProposals").glob("*.json"))
    assert len(pending) == 1
    data = json.loads(pending[0].read_text(encoding="utf-8"))
    assert data["target"] == "Concepts/x.md"
