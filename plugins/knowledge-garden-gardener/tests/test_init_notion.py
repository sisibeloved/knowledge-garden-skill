"""init_notion 测试:REST create_database payload 形状 + 失败语义。"""
from garden_gardener.init_notion import (
    NOTION_DATABASES, create_all_databases, check_connection,
    NotionBootstrapError,
)
from garden_gardener.notion import NotionClient, NotionAPIError


def _fake_send_factory(calls, *, fail_on=None, status=401, message="x"):
    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        if fail_on and path == fail_on:
            raise NotionAPIError(status, message)
        if path == "/users/me":
            return {"object": "bot", "bot": {"owner": {"type": "user"}}}
        if path == "/databases":
            title = json["title"][0]["text"]["content"]
            return {"id": f"db-{title}", "title": json["title"]}
        return {}
    return fake_send


def test_database_schemas_defined():
    # 5 个库 + 各自带必要属性
    names = {d["title"] for d in NOTION_DATABASES}
    assert {"Projects", "Tasks", "Habits", "待审核提案", "周报"} <= names
    # 待审核提案必须有 status / risk / action / target / applied_commit
    proposal = next(d for d in NOTION_DATABASES if d["title"] == "待审核提案")
    prop_names = {p["name"] for p in proposal["properties"]}
    for required in ["status", "risk", "action", "target", "applied_commit", "diff"]:
        assert required in prop_names, f"proposal missing {required}"
    # 周报库必须有 Name(title)/week/summary/各 count
    weekly = next(d for d in NOTION_DATABASES if d["title"] == "周报")
    w_names = {p["name"] for p in weekly["properties"]}
    for required in ["Name", "week", "summary", "orphans_count",
                     "stale_count", "new_evergreen_count", "generated_at"]:
        assert required in w_names, f"weekly missing {required}"


def test_create_all_builds_rest_payload_shape():
    calls = []
    client = NotionClient(send=_fake_send_factory(calls))
    ids = create_all_databases(client, parent_page_id="root-page")

    # 5 个库都有 id(从 title rich-text 数组回读)
    for name in ("Projects", "Tasks", "Habits", "待审核提案", "周报"):
        assert ids[name] == f"db-{name}"

    db_posts = [(p, j) for (m, p, j) in calls if p == "/databases"]
    assert len(db_posts) == 5
    for _, payload in db_posts:
        # REST 契约:parent 带 type、title 是 rich_text 数组
        assert payload["parent"] == {"type": "page_id", "page_id": "root-page"}
        assert isinstance(payload["title"], list)
        assert payload["title"][0]["text"]["content"]

    # 先建的 Projects,其 select options 完整下发
    projects = next(j for _, j in db_posts if j["title"][0]["text"]["content"] == "Projects")
    assert projects["properties"]["Status"] == {"select": {"options": [
        {"name": "计划中"}, {"name": "进行中"}, {"name": "完成"}, {"name": "搁置"}]}}
    assert projects["properties"]["Name"] == {"title": {}}

    # Tasks 的 Project relation 指向已建的 Projects 库 id
    tasks = next(j for _, j in db_posts if j["title"][0]["text"]["content"] == "Tasks")
    assert tasks["properties"]["Project"] == {"relation": {
        "database_id": "db-Projects",
        "type": "single_property", "single_property": {}}}

    # 提案库 status 选项(审批闭环依赖 pending/approved/applied)
    proposal = next(j for _, j in db_posts
                    if j["title"][0]["text"]["content"] == "待审核提案")
    status_opts = [o["name"] for o in proposal["properties"]["status"]["select"]["options"]]
    assert {"pending", "approved", "applied"} <= set(status_opts)


def test_check_connection_401_gives_token_hint():
    def fake_send(method, path, json=None):
        raise NotionAPIError(401, "API token is invalid.")

    client = NotionClient(send=fake_send)
    try:
        check_connection(client)
        assert False, "should raise"
    except NotionBootstrapError as e:
        assert "NOTION_TOKEN" in str(e)


def test_create_all_404_hints_page_share():
    calls = []
    client = NotionClient(send=_fake_send_factory(calls, fail_on="/databases",
                                                  status=404,
                                                  message="Could not find page"))
    try:
        create_all_databases(client, parent_page_id="root-page")
        assert False, "should raise"
    except NotionBootstrapError as e:
        assert "Connections" in str(e)  # 指引:页面分享给 integration


def test_create_all_raises_on_failure():
    def failing_send(method, path, json=None):
        raise RuntimeError("notion down")

    client = NotionClient(send=failing_send)
    try:
        create_all_databases(client, parent_page_id="root-page")
        assert False, "should raise"
    except NotionBootstrapError as e:
        assert "notion down" in str(e) or "失败" in str(e)
