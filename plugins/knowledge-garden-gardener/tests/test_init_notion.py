from garden_gardener.init_notion import NOTION_DATABASES, create_all_databases, NotionBootstrapError


def _fake_post_factory(calls):
    def fake_post(tool, payload):
        calls.append((tool, payload))
        if tool == "create_database":
            # 返回带 id 的伪 database 对象
            return {"id": f"db-{payload['title']}", "title": payload["title"]}
        return {}
    return fake_post


def test_database_schemas_defined():
    # 5 个库 + 各自带必要属性
    names = {d["title"] for d in NOTION_DATABASES}
    assert "Projects" in names
    assert "Tasks" in names
    assert "Habits" in names
    assert "待审核提案" in names
    assert "周报" in names  # §5.5 周报交互队列
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


def test_create_all_returns_id_map_including_weekly(tmp_path):
    from garden_gardener.notion import NotionClient
    calls = []
    client = NotionClient("http://mcp", "x", "x", post=_fake_post_factory(calls))
    ids = create_all_databases(client, parent_page_id="root-page")
    # 5 个库都有 id
    assert ids["Projects"].startswith("db-")
    assert ids["Tasks"].startswith("db-")
    assert ids["周报"].startswith("db-")
    assert ids["待审核提案"].startswith("db-")


def test_create_all_returns_id_map(tmp_path):
    from garden_gardener.notion import NotionClient
    calls = []
    client = NotionClient("http://mcp", "x", "x", post=_fake_post_factory(calls))
    ids = create_all_databases(client, parent_page_id="root-page")
    assert ids["Projects"].startswith("db-")
    assert ids["待审核提案"].startswith("db-")
    # 每个 create_database 都带了 parent
    for tool, payload in calls:
        if tool == "create_database":
            assert payload["parent"]["page_id"] == "root-page"


def test_create_all_raises_on_failure():
    from garden_gardener.notion import NotionClient

    def failing_post(tool, payload):
        raise RuntimeError("notion down")

    client = NotionClient("http://mcp", "x", "x", post=failing_post)
    try:
        create_all_databases(client, parent_page_id="root-page")
        assert False, "should raise"
    except NotionBootstrapError as e:
        assert "notion down" in str(e) or "失败" in str(e)
