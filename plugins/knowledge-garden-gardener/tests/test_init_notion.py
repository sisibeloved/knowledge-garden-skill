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
    # 4 个库 + 各自带必要属性
    names = {d["title"] for d in NOTION_DATABASES}
    assert "Projects" in names
    assert "Tasks" in names
    assert "Habits" in names
    assert "待审核提案" in names
    # 待审核提案必须有 status / risk / action / target / applied_commit
    proposal = next(d for d in NOTION_DATABASES if d["title"] == "待审核提案")
    prop_names = {p["name"] for p in proposal["properties"]}
    for required in ["status", "risk", "action", "target", "applied_commit", "diff"]:
        assert required in prop_names, f"proposal missing {required}"


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
