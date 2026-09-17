import subprocess
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.gitutil import Git
from garden_gardener.config import Config
from garden_gardener.apply import apply_approved
from garden_gardener.frontmatter import parse, dump


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


def _sel(name):
    return {"select": {"name": name}}


def _rt(s):
    return {"rich_text": [{"text": {"content": s}, "plain_text": s}]}


def _ttl(s):
    return {"title": [{"text": {"content": s}, "plain_text": s}]}


def test_apply_create_writes_and_commits_and_writeback(vault, force_filesystem):
    # 模拟 Notion 返回一条 approved 的 create 提案(Notion 原生类型化属性)
    def fake_send(method, path, json=None):
        if path == "/databases/db-1/query":
            return {"results": [{
                "id": "p1",
                "properties": {"proposal_id": _ttl("001"), "risk": _sel("L2"),
                               "action": _sel("create"),
                               "target": _rt("Concepts/New.md"), "sources": _rt(""),
                               "confidence": {"number": 0.9},
                               "diff": _rt("# New\nbody"),
                               "status": _sel("approved")}}]}
        return {"id": "p1"}

    client = NotionClient(proposal_db="db-1", projects_db="db-2", send=fake_send)
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
    def fake_send(method, path, json=None):
        if path == "/databases/db-1/query":
            return {"results": [{
                "id": "p1",
                "properties": {"proposal_id": _ttl("009"), "risk": _sel("L3"),
                               "action": _sel("delete"),
                               "target": _rt("Concepts/X.md"),
                               "diff": _rt(""), "status": _sel("approved")}}]}
        return {}

    client = NotionClient(proposal_db="db-1", projects_db="db-2", send=fake_send)
    v = Vault(vault)
    git = Git(vault)
    result = apply_approved(_cfg(), v, client, git, actor="scheduled_run")
    assert result.blocked == ["p1"]
    assert result.applied == []
    assert not v.exists("Concepts/X.md")  # 没写


def test_apply_link_writes_suggested_links(vault, force_filesystem):
    """批准 link 提案 → diff 里的建议 [[ ]] 真正写进笔记(fm.links + 正文)。"""
    from garden_gardener.frontmatter import parse

    def fake_send(method, path, json=None):
        if path == "/databases/db-1/query":
            return {"results": [{
                "id": "p1",
                "properties": {"proposal_id": _ttl("003"), "risk": _sel("L2"),
                               "action": _sel("link"),
                               "target": _rt("Notes/lonely.md"),
                               "diff": _rt("建议补链:[[RAG]]、[[Retrieval]]"),
                               "status": _sel("approved")}}]}
        return {"id": "p1"}

    v = Vault(vault)
    v.write("Notes/lonely.md", dump({"title": "lonely", "links": []},
            "讲 RAG 与 Retrieval 的关系"), risk_level="L2")
    v.write("Concepts/RAG.md", dump({"title": "RAG"}, "b"), risk_level="L2")
    client = NotionClient(proposal_db="db-1", projects_db="db-2", send=fake_send)
    result = apply_approved(_cfg(), v, client, Git(vault), actor="manual_session")
    assert result.applied == ["p1"]
    fm, body = parse(v.read("Notes/lonely.md"))
    assert "[[RAG]]" in fm.get("links", [])
    assert "[[Retrieval]]" in fm.get("links", [])
    assert "[[RAG]]" in body  # 正文首处也替换
