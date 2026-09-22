"""NotionClient REST 传输契约测试:锁死与 Notion API v1 的 wire 格式。

send 注入 fake,断言方法/path/类型化属性(2022-06-28 版 payload 形状)。
"""
import httpx
import pytest
from garden_gardener.notion import (
    NotionClient, NotionAPIError, NotionConfigError, Proposal,
    flatten_properties,
)


# ---------- Notion 形状构造 helper ----------

def sel(name):
    return {"select": {"name": name}}


def rt(s):
    return {"rich_text": [{"text": {"content": s}, "plain_text": s,
                           "type": "text"}]}


def ttl(s):
    return {"title": [{"text": {"content": s}, "plain_text": s,
                       "type": "text"}]}


def num(n):
    return {"number": n}


def dt(s):
    return {"date": {"start": s}}


def _mkclient(**kw):
    send = kw.pop("send", None)
    return NotionClient(proposal_db="db-1", projects_db="db-2", send=send, **kw)


# ---------- create_proposal ----------

def test_create_proposal_posts_typed_properties():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "page-1", "url": "https://notion.so/page-1"}

    client = _mkclient(send=fake_send)
    p = Proposal(
        proposal_id="2026-06-28-001", risk="L2", action="create",
        target="Concepts/X.md", sources=["raw-1", "raw-2"],
        confidence=0.8, diff="+ new",
        detail="【现状】《X》是孤岛。\n【建议】补链:[[Y]]")
    pid = client.create_proposal(p)
    assert pid == "page-1"
    method, path, payload = calls[0]
    assert (method, path) == ("POST", "/pages")
    assert payload["parent"] == {"database_id": "db-1"}
    props = payload["properties"]
    # 标题人类可读:【action】目标名(proposal_id),id 尾部保留可追溯
    assert props["proposal_id"]["title"][0]["text"]["content"] == \
        "【新建】X(2026-06-28-001)"
    assert props["risk"] == {"select": {"name": "L2"}}
    assert props["action"] == {"select": {"name": "create"}}
    assert props["status"] == {"select": {"name": "pending"}}  # 新提案必为 pending
    assert props["confidence"] == {"number": 0.8}
    assert props["sources"]["rich_text"][0]["text"]["content"] == "raw-1,raw-2"
    # detail 写入页面正文(移动端点开即知审什么)
    blocks = payload.get("children", [])
    assert [b["paragraph"]["rich_text"][0]["text"]["content"] for b in blocks] == \
        ["【现状】《X》是孤岛。", "【建议】补链:[[Y]]"]


def test_create_proposal_without_detail_has_no_children():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "page-2"}

    client = _mkclient(send=fake_send)
    client.create_proposal(Proposal(
        proposal_id="001", risk="L2", action="link", target="Concepts/Y.md",
        sources=[], confidence=0.5, diff="d"))
    assert "children" not in calls[0][2]


def test_archive_page_patches_archived_flag():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "p1"}

    client = _mkclient(send=fake_send)
    client.archive_page("p1")
    assert calls[0] == ("PATCH", "/pages/p1", {"archived": True})


# ---------- poll_approved ----------

def test_poll_approved_queries_with_select_filter_and_normalizes():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        assert path == "/databases/db-1/query"
        return {"results": [
            {"id": "p1", "properties": {
                "proposal_id": ttl("001"), "status": sel("approved"),
                "action": sel("create"), "target": rt("Concepts/X.md"),
                "confidence": num(0.9), "diff": rt("d1")}},
            {"id": "p2", "properties": {"status": sel("pending")}},
        ]}

    client = _mkclient(send=fake_send)
    approved = client.poll_approved()
    # filter 用 select equals(自定义 select 属性,不是原生 status 类型)
    assert calls[0][2]["filter"] == {
        "property": "status", "select": {"equals": "approved"}}
    # 客户端二次过滤 + 扁平归一化
    assert [a["id"] for a in approved] == ["p1"]
    props = approved[0]["properties"]
    assert props["status"] == "approved"
    assert props["proposal_id"] == "001"
    assert props["action"] == "create"
    assert props["confidence"] == 0.9
    assert props["target"] == "Concepts/X.md"


def test_poll_approved_defensive_filter_drops_non_approved():
    """纵深防御:服务端 filter 失效返回 pending,客户端也绝不放行。"""
    def fake_send(method, path, json=None):
        return {"results": [{"id": "p2", "properties": {"status": sel("pending")}}]}

    client = _mkclient(send=fake_send)
    assert client.poll_approved() == []


# ---------- write_applied_commit ----------

def test_write_applied_commit_patches_typed_properties():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "p1"}

    client = _mkclient(send=fake_send)
    client.write_applied_commit("p1", "abc123")
    assert calls[0][0] == "PATCH"
    assert calls[0][1] == "/pages/p1"
    props = calls[0][2]["properties"]
    assert props["status"] == {"select": {"name": "applied"}}
    assert props["applied_commit"]["rich_text"][0]["text"]["content"] == "abc123"


# ---------- query_projects_activity ----------

def test_query_projects_returns_flattened():
    def fake_send(method, path, json=None):
        assert (method, path) == ("POST", "/databases/db-2/query")
        return {"results": [{"id": "proj-1", "properties": {
            "Name": ttl("读 RAG 论文"), "Status": sel("进行中")}}]}

    client = _mkclient(send=fake_send)
    rows = client.query_projects_activity()
    assert rows[0]["properties"]["Name"] == "读 RAG 论文"
    assert rows[0]["properties"]["Status"] == "进行中"


# ---------- create_task ----------

def test_create_task_minimal_fields():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "task-1"}

    client = _mkclient(send=fake_send, tasks_db="tasks-db")
    tid = client.create_task("读完 RAG 综述")
    assert tid == "task-1"
    method, path, payload = calls[0]
    assert (method, path) == ("POST", "/pages")
    assert payload["parent"] == {"database_id": "tasks-db"}
    props = payload["properties"]
    assert props["Name"]["title"][0]["text"]["content"] == "读完 RAG 综述"
    assert props["Status"] == {"select": {"name": "待办"}}
    assert props["Priority"] == {"select": {"name": "中"}}
    assert "Due" not in props and "source_ref" not in props  # 可选字段缺省不发


def test_create_task_with_due_and_source_ref():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "task-2"}

    client = _mkclient(send=fake_send, tasks_db="tasks-db")
    client.create_task("交周报", due="2026-09-20", source_ref="obsidian://x")
    props = calls[0][2]["properties"]
    assert props["Due"] == {"date": {"start": "2026-09-20"}}
    assert props["source_ref"] == {"url": "obsidian://x"}


def test_create_task_raises_when_tasks_db_missing():
    client = _mkclient()
    with pytest.raises(NotionConfigError):
        client.create_task("x")


# ---------- write_weekly_report ----------

def test_write_weekly_report_posts_counts():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "wk-1"}

    client = _mkclient(send=fake_send, weekly_db="wk-db")
    pid = client.write_weekly_report("2026-W32", "# 摘要", {
        "orphans_count": 2, "stale_count": 1, "new_evergreen_count": 3,
        "conflicts": "A ⇄ B"})
    assert pid == "wk-1"
    method, path, payload = calls[0]
    assert (method, path) == ("POST", "/pages")
    assert payload["parent"] == {"database_id": "wk-db"}
    props = payload["properties"]
    assert props["Name"]["title"][0]["text"]["content"] == "2026-W32 知识周报"
    assert props["orphans_count"] == {"number": 2}
    assert props["generated_at"]["date"]["start"]  # ISO 日期


def test_write_weekly_report_truncates_summary_to_2000():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "wk-2"}

    client = _mkclient(send=fake_send, weekly_db="wk-db")
    client.write_weekly_report("2026-W32", "x" * 5000, {})
    content = calls[0][2]["properties"]["summary"]["rich_text"][0]["text"]["content"]
    assert len(content) == 2000


def test_write_weekly_report_raises_when_weekly_db_missing():
    client = _mkclient()
    with pytest.raises(NotionConfigError):
        client.write_weekly_report("2026-W32", "s", {})


# ---------- flatten_properties 归一化 ----------

def test_flatten_properties_handles_all_scalar_kinds():
    flat = flatten_properties({
        "Name": ttl("标题"),
        "Tags": {"multi_select": [{"name": "a"}, {"name": "b"}]},
        "Done": {"checkbox": True},
        "Link": {"url": "https://x"},
        "When": dt("2026-09-17"),
        "Owner": {"people": [{"name": "me"}]},  # 未知 kind → 原样
    })
    assert flat["Name"] == "标题"
    assert flat["Tags"] == "a,b"
    assert flat["Done"] is True
    assert flat["Link"] == "https://x"
    assert flat["When"] == "2026-09-17"
    assert flat["Owner"] == {"people": [{"name": "me"}]}


# ---------- 错误语义 ----------

def test_api_error_raised_on_4xx_and_is_httpx_subclass():
    def fake_send(method, path, json=None):
        raise NotionAPIError(401, "API token is invalid.")

    client = _mkclient(send=fake_send)
    with pytest.raises(NotionAPIError) as ei:
        client.me()
    assert ei.value.status == 401
    # 必须能被现有 `except httpx.HTTPError` 降级路径捕获
    assert isinstance(ei.value, httpx.HTTPError)


def test_httpx_send_builds_auth_headers(monkeypatch):
    captured = {}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        captured.update(method=method, url=url, headers=headers)
        class R:
            status_code = 200
            def json(self):
                return {"object": "bot"}
        return R()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = NotionClient(proposal_db="p", projects_db="q",
                          token="ntn-secret", api_base="https://api.notion.com/v1/")
    client.me()
    assert captured["url"] == "https://api.notion.com/v1/users/me"
    assert captured["headers"]["Authorization"] == "Bearer ntn-secret"
    assert captured["headers"]["Notion-Version"] == "2022-06-28"


def test_token_resolved_from_env(monkeypatch):
    monkeypatch.setenv("MY_NOTION_TOKEN", "ntn-env")
    c1 = NotionClient(token_env="MY_NOTION_TOKEN")
    assert c1.token == "ntn-env"
    # 显式 token 优先于环境变量
    c2 = NotionClient(token="ntn-explicit", token_env="MY_NOTION_TOKEN")
    assert c2.token == "ntn-explicit"


def test_write_reverted_patches_status_and_reason():
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "p1"}

    client = _mkclient(send=fake_send)
    client.write_reverted("p1", "目标笔记已不存在")
    assert calls[0][0] == "PATCH"
    props = calls[0][2]["properties"]
    assert props["status"] == {"select": {"name": "reverted"}}
    assert props["review_decision"]["rich_text"][0]["text"]["content"] == "目标笔记已不存在"
