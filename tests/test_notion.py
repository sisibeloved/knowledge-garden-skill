from garden_gardener.notion import NotionClient, Proposal


def test_create_proposal_calls_mcp():
    calls = []

    def fake_post(tool, payload):
        calls.append(payload)
        return {"id": "page-1", "url": "http://n/page-1"}

    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    pid = client.create_proposal(Proposal(
        proposal_id="2026-06-28-001", risk="L2", action="create",
        target="Concepts/X.md", sources=["raw-1"], confidence=0.8, diff="+ new"))
    assert pid == "page-1"
    assert calls[0]["database_id"] == "db-1"
    assert calls[0]["properties"]["risk"] == "L2"


def test_poll_approved_returns_only_approved():
    def fake_post(tool, payload):
        return {"results": [
            {"id": "p1", "properties": {"status": "approved", "proposal_id": "001"}},
            {"id": "p2", "properties": {"status": "pending", "proposal_id": "002"}},
        ]}

    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    approved = client.poll_approved()
    assert [a["id"] for a in approved] == ["p1"]


def test_write_applied_commit_updates_status():
    calls = []

    def fake_post(tool, payload):
        calls.append((tool, payload))
        return {"ok": True}

    client = NotionClient("http://mcp", "db-1", "db-2", post=fake_post)
    client.write_applied_commit("p1", "abc123")
    assert calls[0][0] == "update_page"
    assert calls[0][1]["page_id"] == "p1"
    assert calls[0][1]["properties"]["applied_commit"] == "abc123"
    assert calls[0][1]["properties"]["status"] == "applied"
