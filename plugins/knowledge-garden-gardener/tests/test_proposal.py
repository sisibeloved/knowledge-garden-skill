import json
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.audit import AuditReport
from garden_gardener.frontmatter import dump
from garden_gardener.proposal import emit_proposals


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


def test_orphan_proposal_carries_suggested_links(vault, force_filesystem):
    """提案正文必须可读:孤岛正文命中其它笔记标题 → 建议写进 diff + detail。"""
    v = Vault(vault)
    v.write("Concepts/RAG.md", dump({"title": "RAG"}, "RAG 是检索增强生成"),
            risk_level="L2")
    v.write("Notes/isolated.md",
            dump({"title": "孤岛笔记", "links": []}, "本文讨论 RAG 的应用场景"),
            risk_level="L2")
    rep = AuditReport(orphans=["Notes/isolated.md"])

    calls = []
    page_ids = emit_proposals(v, _mkclient(calls), rep, actor="manual_session")
    assert len(page_ids) == 1
    payload = _create_payload(calls)
    props = payload["properties"]
    assert props["action"] == {"select": {"name": "link"}}
    assert props["target"]["rich_text"][0]["text"]["content"] == "Notes/isolated.md"
    # 具体建议链接进 diff(与 L1 add_wikilink 同一套匹配)
    assert "[[RAG]]" in props["diff"]["rich_text"][0]["text"]["content"]
    # 标题可读:【补链】目标名(id)
    assert props["proposal_id"]["title"][0]["text"]["content"].startswith("【补链】孤岛笔记")
    # detail 段落块:现状/建议/摘录
    blocks = [b["paragraph"]["rich_text"][0]["text"]["content"]
              for b in payload["children"]]
    assert any("【现状】" in b for b in blocks)
    assert any("【建议】" in b for b in blocks)


def test_orphan_without_match_gets_low_confidence(vault, force_filesystem):
    """无匹配建议:diff 明说需人工判断,confidence 降档。"""
    v = Vault(vault)
    v.write("Notes/lonely.md", dump({"title": "Lonely"}, " unrelated content "),
            risk_level="L2")
    rep = AuditReport(orphans=["Notes/lonely.md"])
    calls = []
    emit_proposals(v, _mkclient(calls), rep, actor="manual_session")
    payload = _create_payload(calls)
    diff = payload["properties"]["diff"]["rich_text"][0]["text"]["content"]
    assert "需人工判断" in diff
    assert payload["properties"]["confidence"] == {"number": 0.4}


def test_missing_orphan_file_degrades_gracefully(vault, force_filesystem):
    """审计目标文件读不了 → 提案仍生成(空建议),不抛。"""
    rep = AuditReport(orphans=["Concepts/gone.md"])
    calls = []
    page_ids = emit_proposals(Vault(vault), _mkclient(calls), rep,
                              actor="manual_session")
    assert len(page_ids) == 1
    assert "需人工判断" in \
        _create_payload(calls)["properties"]["diff"]["rich_text"][0]["text"]["content"]


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


# ---------- replay_pending(暂存回放,设计承诺的"下轮补写") ----------

def _stash(v, target, proposal_id="2026-01-01-001"):
    import json as _json
    d = v.root / "_System/_PendingProposals"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{proposal_id}-link.json"
    p.write_text(_json.dumps({
        "proposal_id": proposal_id, "risk": "L2", "action": "link",
        "target": target, "sources": [], "confidence": 0.6,
        "diff": "建议补链:[[X]]", "detail": "", "display": ""}, ensure_ascii=False),
        encoding="utf-8")
    return p


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


def test_replay_flushes_stashed_proposal(vault, force_filesystem):
    from garden_gardener.proposal import replay_pending
    v = Vault(vault)
    p = _stash(v, "Notes/old-target.md")
    calls = []
    n = replay_pending(v, _replay_client(calls))
    assert n == 1
    assert not p.exists()  # 写成功 → 本地副本删除


def test_replay_skips_current_round_targets(vault, force_filesystem):
    """本轮要新生成的目标:暂存副本直接清掉,不回放(防重复)。"""
    from garden_gardener.proposal import replay_pending
    v = Vault(vault)
    p = _stash(v, "Notes/this-round.md")
    calls = []
    n = replay_pending(v, _replay_client(calls), skip_targets={"Notes/this-round.md"})
    assert n == 0  # 没回放
    assert not p.exists()  # 但副本也清了(马上由本轮新提案取代)
    creates = [c for c in calls if c[1] == "/pages"]
    assert creates == []


def test_replay_skips_existing_pending_in_notion(vault, force_filesystem):
    """库里已有同目标 pending:跳过回放,本地副本清掉。"""
    from garden_gardener.proposal import replay_pending
    v = Vault(vault)
    p = _stash(v, "Notes/dup.md")
    calls = []
    n = replay_pending(v, _replay_client(calls, pending_targets=("Notes/dup.md",)))
    assert n == 0
    assert not p.exists()


def test_replay_keeps_stash_when_notion_unreachable(vault, force_filesystem):
    from garden_gardener.proposal import replay_pending
    v = Vault(vault)
    p = _stash(v, "Notes/x.md")

    def down(method, path, json=None):
        raise RuntimeError("net down")

    client = NotionClient(proposal_db="db-1", projects_db="db-2", send=down)
    assert replay_pending(v, client) == 0
    assert p.exists()  # 暂存保留待下轮


def test_emit_proposals_replays_before_generating(vault, force_filesystem):
    """emit 先回放非本轮目标,再生成新提案。"""
    v = Vault(vault)
    v.write("Notes/isolated.md", dump({"title": "孤岛", "links": []}, "body"),
            risk_level="L2")
    _stash(v, "Notes/history-target.md")  # 上历史轮的暂存,不在本轮 orphans
    calls = []
    page_ids = emit_proposals(v, _replay_client(calls), AuditReport(orphans=["Notes/isolated.md"]),
                              actor="manual_session")
    # 回放 1 条(不计入返回)+ 新生成 1 条(返回);暂存清空
    assert len(page_ids) == 1
    creates = [c for c in calls if c[1] == "/pages"]
    assert len(creates) == 2  # 回放 + 新生成各一次 POST
    assert not list((v.root / "_System/_PendingProposals").glob("*.json"))


def test_emit_skips_orphans_already_pending_in_notion(vault, force_filesystem):
    """防重复:库里已有 pending 提案的孤岛,本轮不再生成。"""
    v = Vault(vault)
    v.write("Notes/isolated.md", dump({"title": "孤岛", "links": []}, "body"),
            risk_level="L2")
    calls = []
    client = _replay_client(calls, pending_targets=("Notes/isolated.md",))
    page_ids = emit_proposals(v, client, AuditReport(orphans=["Notes/isolated.md"]),
                              actor="manual_session")
    assert page_ids == []
    creates = [c for c in calls if c[1] == "/pages"]
    assert creates == []
    # 且没落暂存(不是失败,是明确跳过)
    assert not list((v.root / "_System/_PendingProposals").glob("*.json"))
