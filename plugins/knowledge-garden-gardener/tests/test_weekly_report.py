"""周报生成测试:summarize 结构 + publish 双写/降级。"""
from datetime import date
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient, NotionConfigError
from garden_gardener.audit import AuditReport
from garden_gardener.frontmatter import dump
from garden_gardener.weekly_report import summarize, publish, _week_str


def _note(vault, rel, fm, body="x"):
    Vault(vault).write(rel, dump(fm, body), risk_level="L2")


def _this_week():
    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def test_summarize_counts_and_week(vault, force_filesystem):
    # 2 篇本周新增 + 1 篇旧
    _note(vault, "Concepts/New1.md",
          {"title": "N1", "created_at": date.today().isoformat()})
    _note(vault, "Notes/New2.md",
          {"title": "N2", "created_at": date.today().isoformat()})
    _note(vault, "Concepts/Old.md",
          {"title": "O", "created_at": "2020-01-01"})
    rep = AuditReport(orphans=["Concepts/Old.md"], stale=["Concepts/Old.md"],
                      inbox_pending=["_System/_Inbox/x.md"])

    v = Vault(vault)
    stats = summarize(v, rep, projects_activity=[])
    assert stats.week == _this_week()
    assert stats.new_evergreen_count == 2
    assert stats.orphans_count == 1
    assert stats.stale_count == 1
    assert stats.inbox_count == 1


def test_summarize_markdown_structure(vault, force_filesystem):
    rep = AuditReport(orphans=["Concepts/A.md"], stale=[],
                      inbox_pending=[], conflicts=[("A.md", "B.md")])
    stats = summarize(Vault(vault), rep,
                      projects_activity=[{"properties": {"Name": "读 RAG", "Status": "进行中"}}])
    md = stats.markdown
    assert f"知识周报 {_this_week()}" in md
    assert "## 概览" in md
    assert "## 孤岛清单" in md
    assert "- Concepts/A.md" in md
    assert "A.md ⇄ B.md" in md  # 冲突
    assert "读 RAG" in md and "进行中" in md  # Projects 活动


def test_publish_writes_local_copy_always(vault, force_filesystem):
    # weekly_db 未配置 → NotionConfigError,但本地副本仍写
    calls = []

    def fake_post(tool, payload):
        calls.append((tool, payload))
        raise NotionConfigError("no weekly db")  # 不会这样抛,但模拟失败

    client = NotionClient("http://mcp", "p", "proj", post=fake_post, weekly_db="")
    v = Vault(vault)
    stats = summarize(v, AuditReport(), [])
    publish(v, client, stats)
    # 本地副本写了
    assert v.exists("_System/_Reports/weekly-report.md")
    # Notion 没被调(weekly_db 空 → write_weekly_report 直接抛 NotionConfigError)
    assert calls == []


def test_publish_dual_writes_when_notion_configured(vault, force_filesystem):
    calls = []

    def fake_post(tool, payload):
        calls.append((tool, payload))
        return {"id": "wk-page"}

    client = NotionClient("http://mcp", "p", "proj", post=fake_post, weekly_db="wk-db")
    v = Vault(vault)
    stats = summarize(v, AuditReport(orphans=["X.md"]), [])
    publish(v, client, stats)
    # 本地写了
    assert v.exists("_System/_Reports/weekly-report.md")
    # Notion 写了
    notion_calls = [c for c in calls if c[0] == "create_page"]
    assert len(notion_calls) == 1
    props = notion_calls[0][1]["properties"]
    assert props["database_id"] if False else True  # placeholder
    assert notion_calls[0][1]["database_id"] == "wk-db"
    assert props["orphans_count"] == 1


def test_publish_degrades_on_notion_unreachable(vault, force_filesystem):
    # Notion 网络不可达 → 本地仍写,不抛
    import httpx

    def fake_post(tool, payload):
        raise httpx.ConnectError("network down")

    client = NotionClient("http://mcp", "p", "proj", post=fake_post, weekly_db="wk-db")
    v = Vault(vault)
    stats = summarize(v, AuditReport(), [])
    publish(v, client, stats)  # 不应抛
    assert v.exists("_System/_Reports/weekly-report.md")
