from garden_gardener.notion import NotionClient, Proposal, NotionConfigError


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


# ---------- create_task (capture 路由用) ----------

def test_create_task_calls_mcp_with_minimal_fields():
    calls = []

    def fake_post(tool, payload):
        calls.append((tool, payload))
        return {"id": "task-1", "url": "http://n/task-1"}

    client = NotionClient("http://mcp", "p", "proj", post=fake_post, tasks_db="tasks-db")
    tid = client.create_task("读完 RAG 综述")
    assert tid == "task-1"
    assert calls[0][0] == "create_page"
    assert calls[0][1]["database_id"] == "tasks-db"
    props = calls[0][1]["properties"]
    assert props["Name"] == "读完 RAG 综述"
    assert props["Status"] == "待办"
    assert props["Priority"] == "中"
    # 可选字段未传时不写入
    assert "Due" not in props
    assert "source_ref" not in props


def test_create_task_passes_optional_fields():
    captured = {}

    def fake_post(tool, payload):
        captured.update(payload)
        return {"id": "task-2"}

    client = NotionClient("http://mcp", "p", "proj", post=fake_post, tasks_db="tasks-db")
    client.create_task("写周报", due="2026-08-15", priority="高",
                       source_ref="obsidian://open?vault=Garden&file=X")
    props = captured["properties"]
    assert props["Due"] == "2026-08-15"
    assert props["Priority"] == "高"
    assert props["source_ref"].startswith("obsidian://")


def test_create_task_raises_when_no_tasks_db():
    # tasks_db 未配置 → NotionConfigError(调用方据此降级落 Raw)
    client = NotionClient("http://mcp", "p", "proj", post=lambda *_: {})
    try:
        client.create_task("anything")
        assert False, "should raise NotionConfigError"
    except NotionConfigError:
        pass


# ---------- write_weekly_report ----------

def test_write_weekly_report_calls_mcp():
    captured = {}

    def fake_post(tool, payload):
        captured.update(payload)
        return {"id": "wk-1"}

    client = NotionClient("http://mcp", "p", "proj", post=fake_post, weekly_db="wk-db")
    pid = client.write_weekly_report(
        "2026-W32", "# 摘要\n3 条孤岛",
        {"orphans_count": 3, "stale_count": 1, "new_evergreen_count": 5, "conflicts": ""},
    )
    assert pid == "wk-1"
    assert captured["database_id"] == "wk-db"
    props = captured["properties"]
    assert props["Name"] == "2026-W32 知识周报"
    assert props["week"] == "2026-W32"
    assert props["summary"] == "# 摘要\n3 条孤岛"
    assert props["orphans_count"] == 3
    assert props["stale_count"] == 1
    assert props["new_evergreen_count"] == 5
    # generated_at 是今天(ISO 日期)
    from datetime import date
    assert props["generated_at"] == date.today().isoformat()


def test_write_weekly_report_truncates_long_summary():
    captured = {}

    def fake_post(tool, payload):
        captured.update(payload)
        return {"id": "wk-2"}

    client = NotionClient("http://mcp", "p", "proj", post=fake_post, weekly_db="wk-db")
    long_summary = "x" * 3000
    client.write_weekly_report("2026-W32", long_summary, {})
    # Notion rich_text 上限 2000
    assert len(captured["properties"]["summary"]) == 2000


def test_write_weekly_report_raises_when_no_weekly_db():
    client = NotionClient("http://mcp", "p", "proj", post=lambda *_: {})
    try:
        client.write_weekly_report("2026-W32", "s", {})
        assert False, "should raise NotionConfigError"
    except NotionConfigError:
        pass


def test_client_accepts_tasks_and_weekly_db_as_kwargs():
    # 老 config(无 tasks/weekly id)构造不破坏;新字段默认空
    c = NotionClient("http://mcp", "p", "proj", post=lambda *_: {})
    assert c.tasks_db == ""
    assert c.weekly_db == ""
    c2 = NotionClient("http://mcp", "p", "proj", post=lambda *_: {},
                      tasks_db="t", weekly_db="w")
    assert c2.tasks_db == "t" and c2.weekly_db == "w"
