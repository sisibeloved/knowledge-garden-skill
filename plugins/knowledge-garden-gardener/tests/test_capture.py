"""capture 动词测试:路由判定 + 落地( Raw / Task / 降级)。"""
import httpx
from garden_gardener.vault import Vault
from garden_gardener.notion import NotionClient
from garden_gardener.frontmatter import parse
from garden_gardener.capture import route, run_capture, capture_to_raw


# ---------- route(纯函数) ----------

def test_route_task_keywords():
    assert route("记得明天开会") == "task"
    assert route("todo: 写周报") == "task"
    assert route("下周要完成 RAG 综述") == "task"
    assert route("deadline 周五") == "task"


def test_route_raw_when_no_task_signal():
    assert route("RAG 是检索增强生成") == "raw"
    assert route("双链是 Obsidian 的核心机制") == "raw"
    assert route("https://example.com/paper.pdf") == "raw"


# ---------- run_capture: raw 路径 ----------

def test_capture_raw_writes_inbox_with_frontmatter(vault, force_filesystem):
    res = run_capture(Vault(vault), "RAG 是检索增强", source="manual", client=None)
    assert res.destination == "raw"
    assert res.path_or_id.startswith("_System/_Inbox/raw-")
    fm, body = parse(Vault(vault).read(res.path_or_id))
    assert fm["type"] == "raw"
    assert fm["status"] == "inbox"
    assert fm["source"] == "manual"
    assert fm["needs_review"] is False
    assert body == "RAG 是检索增强"


# ---------- run_capture: task 路径 ----------

def test_capture_task_creates_notion_task(vault, force_filesystem):
    calls = []

    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "task-99"}

    client = NotionClient(proposal_db="p", projects_db="proj",
                          tasks_db="t-db", send=fake_send)
    res = run_capture(Vault(vault), "明天要完成周报", client=client)
    assert res.destination == "task"
    assert res.path_or_id == "task-99"
    # POST /pages,parent 指向 tasks 库
    method, path, payload = calls[0]
    assert (method, path) == ("POST", "/pages")
    assert payload["parent"] == {"database_id": "t-db"}
    assert payload["properties"]["Name"]["title"][0]["text"]["content"] == "明天要完成周报"
    # 没写 Raw
    assert not Vault(vault).exists("_System/_Inbox") or \
        not any(Vault(vault).read_glob("_System/_Inbox/*.md"))


def test_capture_task_falls_back_to_raw_when_no_client(vault, force_filesystem):
    # client=None(离线/无 config)→ task 降级 Raw,type=task_candidate
    res = run_capture(Vault(vault), "明天要完成周报", client=None)
    assert res.destination == "raw_fallback"
    assert "task_candidate" in res.note
    fm, _ = parse(Vault(vault).read(res.path_or_id))
    assert fm["type"] == "task_candidate"
    assert fm["needs_review"] is True  # 待下轮 triage 提升


def test_capture_task_falls_back_on_notion_unreachable(vault, force_filesystem):
    def fake_send(method, path, json=None):
        raise httpx.ConnectError("down")

    client = NotionClient(proposal_db="p", projects_db="proj",
                          tasks_db="t-db", send=fake_send)
    res = run_capture(Vault(vault), "明天要完成周报", client=client)
    assert res.destination == "raw_fallback"
    fm, _ = parse(Vault(vault).read(res.path_or_id))
    assert fm["type"] == "task_candidate"


def test_capture_raw_id_unique_for_different_text(vault, force_filesystem):
    capture_to_raw(Vault(vault), "内容一", "manual")
    capture_to_raw(Vault(vault), "内容二", "manual")
    files = Vault(vault).read_glob("_System/_Inbox/*.md")
    assert len(files) == 2  # 不同文本 → 不同文件名
