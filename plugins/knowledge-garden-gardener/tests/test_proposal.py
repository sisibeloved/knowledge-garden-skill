import json
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.audit import AuditReport
from garden_gardener.frontmatter import dump
from garden_gardener.proposal import emit_proposals, replay_pending


def _create_payload(calls):
    """取 create_proposal 的 /pages 调用 payload(前面可能有 /query 查询)。"""
    for m, p, j in calls:
        if p == "/pages":
            return j
    raise AssertionError("no /pages call")


def _mkclient(calls):
    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": f"page-{len(calls)}"}
    return NotionClient(proposal_db="db-1", projects_db="db-2", send=fake_send)


def _replay_client(calls, pending_targets=()):
    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        if path.endswith("/query"):
            rt = [{"text": {"content": t}, "plain_text": t} for t in pending_targets]
            return {"results": [
                {"id": "existing", "properties": {"target": {"rich_text": rt}}}
                for _ in pending_targets]}
        return {"id": f"replayed-{len(calls)}"}
    return NotionClient(proposal_db="db-1", projects_db="db-2", send=fake_send)


# ---------- 队列准入:默认零提案(标题匹配归 L1,孤岛清单看周报) ----------

def test_no_proposals_by_default(vault, force_filesystem):
    """无 semantic 建议:孤岛不进审批队列(L1 同源匹配会自动补,入队即噪音)。"""
    v = Vault(vault)
    v.write("Notes/isolated.md", dump({"title": "孤岛", "links": []}, "RAG 内容"),
            risk_level="L2")
    calls = []
    page_ids = emit_proposals(v, _mkclient(calls), AuditReport(orphans=["Notes/isolated.md"]),
                              actor="manual_session")
    assert page_ids == []
    assert [c for c in calls if c[1] == "/pages"] == []
    assert not list((v.root / "_System/_PendingProposals").glob("*.json"))


def test_semantic_suggestions_become_proposals(vault, force_filesystem):
    """semantic 建议(L1 做不了的语义匹配)→ 入队,带建议链接 + 批准后动作说明。"""
    v = Vault(vault)
    v.write("Notes/isolated.md", dump({"title": "孤岛", "links": []}, "正文"),
            risk_level="L2")
    v.write("Concepts/related.md", dump({"title": "Related"}, "b"), risk_level="L2")
    calls = []
    page_ids = emit_proposals(
        v, _mkclient(calls), AuditReport(orphans=["Notes/isolated.md"]),
        actor="manual_session",
        semantic={"Notes/isolated.md": ["Related"]})
    assert len(page_ids) == 1
    payload = _create_payload(calls)
    props = payload["properties"]
    assert props["action"] == {"select": {"name": "link"}}
    assert "[[Related]]" in props["diff"]["rich_text"][0]["text"]["content"]
    assert props["proposal_id"]["title"][0]["text"]["content"].startswith("【补链】孤岛")
    blocks = [b["paragraph"]["rich_text"][0]["text"]["content"]
              for b in payload["children"]]
    assert any("【批准后动作】" in b for b in blocks)


def test_semantic_unknown_title_filtered(vault, force_filesystem):
    """semantic 建议里不是 Evergreen 标题的过滤掉;全被过滤 → 不入队。"""
    v = Vault(vault)
    v.write("Notes/isolated.md", dump({"title": "孤岛", "links": []}, "b"),
            risk_level="L2")
    calls = []
    page_ids = emit_proposals(
        v, _mkclient(calls), AuditReport(orphans=["Notes/isolated.md"]),
        actor="manual_session",
        semantic={"Notes/isolated.md": ["不存在的笔记"]})
    assert page_ids == []


def test_emit_skips_orphans_already_pending_in_notion(vault, force_filesystem):
    """防重复:库里已有 pending 提案的孤岛,本轮不再生成。"""
    v = Vault(vault)
    v.write("Notes/isolated.md", dump({"title": "孤岛", "links": []}, "b"),
            risk_level="L2")
    v.write("Concepts/related.md", dump({"title": "Related"}, "b"), risk_level="L2")
    calls = []
    client = _replay_client(calls, pending_targets=("Notes/isolated.md",))
    page_ids = emit_proposals(
        v, client, AuditReport(orphans=["Notes/isolated.md"]),
        actor="manual_session",
        semantic={"Notes/isolated.md": ["Related"]})
    assert page_ids == []
    assert [c for c in calls if c[1] == "/pages"] == []
    assert not list((v.root / "_System/_PendingProposals").glob("*.json"))


def test_fallback_stores_locally_when_notion_fails(vault, force_filesystem):
    v = Vault(vault)
    v.write("Notes/x.md", dump({"title": "X", "links": []}, "b"), risk_level="L2")
    v.write("Concepts/related.md", dump({"title": "Related"}, "b"), risk_level="L2")

    def fake_send(method, path, json=None):
        raise RuntimeError("notion down")

    client = NotionClient(proposal_db="db-1", projects_db="db-2", send=fake_send)
    page_ids = emit_proposals(
        Vault(vault), client, AuditReport(orphans=["Notes/x.md"]),
        actor="manual_session",
        semantic={"Notes/x.md": ["Related"]})
    assert page_ids == []  # 没成功入 Notion
    pending = list((Vault(vault).root / "_System/_PendingProposals").glob("*.json"))
    assert len(pending) == 1
    data = json.loads(pending[0].read_text(encoding="utf-8"))
    assert data["target"] == "Notes/x.md"


# ---------- replay_pending(暂存回放,设计承诺的"下轮补写") ----------

def _stash(v, target, proposal_id="2026-01-01-001"):
    d = v.root / "_System/_PendingProposals"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{proposal_id}-link.json"
    p.write_text(json.dumps({
        "proposal_id": proposal_id, "risk": "L2", "action": "link",
        "target": target, "sources": [], "confidence": 0.6,
        "diff": "建议补链:[[X]]", "detail": "", "display": ""}, ensure_ascii=False),
        encoding="utf-8")
    return p


def test_replay_flushes_stashed_proposal(vault, force_filesystem):
    v = Vault(vault)
    p = _stash(v, "Notes/old-target.md")
    calls = []
    n = replay_pending(v, _replay_client(calls))
    assert n == 1
    assert not p.exists()  # 写成功 → 本地副本删除


def test_replay_skips_current_round_targets(vault, force_filesystem):
    """本轮要新生成的目标:暂存副本直接清掉,不回放(防重复)。"""
    v = Vault(vault)
    p = _stash(v, "Notes/this-round.md")
    calls = []
    n = replay_pending(v, _replay_client(calls), skip_targets={"Notes/this-round.md"})
    assert n == 0
    assert not p.exists()
    assert [c for c in calls if c[1] == "/pages"] == []


def test_replay_skips_existing_pending_in_notion(vault, force_filesystem):
    v = Vault(vault)
    p = _stash(v, "Notes/dup.md")
    calls = []
    n = replay_pending(v, _replay_client(calls, pending_targets=("Notes/dup.md",)))
    assert n == 0
    assert not p.exists()


def test_replay_keeps_stash_when_notion_unreachable(vault, force_filesystem):
    v = Vault(vault)
    p = _stash(v, "Notes/x.md")

    def down(method, path, json=None):
        raise RuntimeError("net down")

    client = NotionClient(proposal_db="db-1", projects_db="db-2", send=down)
    assert replay_pending(v, client) == 0
    assert p.exists()  # 暂存保留待下轮
