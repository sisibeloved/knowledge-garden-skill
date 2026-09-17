from __future__ import annotations
from .notion import NotionClient, NotionAPIError

# 属性类型简写:Notion database schema 定义。init 时用这些定义建库。
def _prop(name, ptype, **extra):
    d = {"name": name, "type": ptype}
    d.update(extra)
    return d


def _select(name, options):
    return _prop(name, "select", options=[{"name": o} for o in options])


def _multi(name, options):
    return _prop(name, "multi_select", options=[{"name": o} for o in options])


def _relation(name, target_title):
    return _prop(name, "relation", relation_to=target_title)


# 5 个 Notion 库的 schema(对应 design §3.3 待审核提案 + §4.5.2 Projects/Tasks/Habits
# + §5.5 周报交互队列)。init 时用这些定义建库。
NOTION_DATABASES = [
    {
        "title": "Projects",
        "properties": [
            _prop("Name", "title"),
            _select("Type", ["阅读", "工作", "生活"]),
            _select("Status", ["计划中", "进行中", "完成", "搁置"]),
            _prop("Start", "date"),
            _prop("Due", "date"),
            _prop("notion_ref", "url"),  # 指向 Obsidian 的链接
            _prop("Owner", "rich_text"),
        ],
    },
    {
        "title": "Tasks",
        "properties": [
            _prop("Name", "title"),
            _relation("Project", "Projects"),
            _select("Status", ["待办", "进行中", "完成"]),
            _prop("Due", "date"),
            _select("Priority", ["低", "中", "高"]),
            _prop("source_ref", "url"),  # 指向 Obsidian 的链接
        ],
    },
    {
        "title": "Habits",
        "properties": [
            _prop("Name", "title"),
            _select("Type", ["习惯", "待办"]),
            _select("Frequency", ["每日", "每周"]),
            _prop("Streak", "number"),
            _prop("Last_done", "date"),
            _prop("History", "rich_text"),
        ],
    },
    {
        "title": "待审核提案",
        "properties": [
            _prop("proposal_id", "title"),
            _prop("created_at", "date"),
            _select("status", ["pending", "approved", "rejected", "applied", "reverted"]),
            _select("risk", ["L0", "L1", "L2", "L3"]),
            _select("action", ["create", "update", "delete", "move", "rename", "link"]),
            _prop("target", "rich_text"),
            _prop("sources", "rich_text"),
            _prop("confidence", "number"),
            _prop("diff", "rich_text"),
            _prop("review_decision", "rich_text"),
            _prop("reviewed_at", "date"),
            _prop("applied_commit", "rich_text"),  # 跨系统审计链
        ],
    },
    {
        # §5.5 周报交互队列:移动端随手读的"本周知识摘要"。
        # 与 Projects/Tasks/Habits(项目执行面)是独立的一组交互库。
        "title": "周报",
        "properties": [
            _prop("Name", "title"),
            _prop("week", "rich_text"),         # 形如 2026-W32
            _prop("summary", "rich_text"),      # markdown 摘要(≤2000 字符)
            _prop("orphans_count", "number"),
            _prop("stale_count", "number"),
            _prop("new_evergreen_count", "number"),
            _prop("conflicts", "rich_text"),
            _prop("generated_at", "date"),
        ],
    },
]


class NotionBootstrapError(Exception):
    """Notion 库引导失败。"""


# 属性 spec → Notion REST create_database 的 properties schema 片段
def _rest_schema(p: dict, id_map: dict[str, str]) -> dict | None:
    t = p["type"]
    if t == "title":
        return {"title": {}}
    if t == "select":
        return {"select": {"options": p["options"]}}
    if t == "multi_select":
        return {"multi_select": {"options": p["options"]}}
    if t == "rich_text":
        return {"rich_text": {}}
    if t == "date":
        return {"date": {}}
    if t == "number":
        return {"number": {}}
    if t == "url":
        return {"url": {}}
    if t == "relation":
        target = p.get("relation_to", "")
        if target not in id_map:
            # 目标库还没建(顺序错)——跳过该属性而不是让整次 init 失败
            return None
        return {"relation": {"database_id": id_map[target],
                             "type": "single_property", "single_property": {}}}
    raise NotionBootstrapError(f"未知属性类型:{t}({p['name']})")


def check_connection(client: NotionClient) -> None:
    """token 有效性 + 连通性预检。失败抛 NotionBootstrapError(带人话诊断)。"""
    try:
        client.me()
    except NotionAPIError as e:
        if e.status == 401:
            raise NotionBootstrapError(
                f"Notion token 无效或未配置(401)。检查 NOTION_TOKEN 环境变量"
                f"是否为 integration 的 Internal Token:{e.message}") from e
        raise NotionBootstrapError(f"Notion API 不可达({e})") from e
    except Exception as e:
        raise NotionBootstrapError(f"Notion API 不可达:{e}") from e


def create_all_databases(client: NotionClient, *, parent_page_id: str) -> dict[str, str]:
    """在指定 parent page 下创建 5 个库,返回 {库名: database_id}。

    失败抛 NotionBootstrapError(不部分建——保持原子性,调用方可清理后重试)。
    404 object_not_found 最常见原因是父页面没分享给 integration。
    """
    check_connection(client)
    id_map: dict[str, str] = {}
    try:
        for spec in NOTION_DATABASES:
            props: dict[str, dict] = {}
            for p in spec["properties"]:
                schema = _rest_schema(p, id_map)
                if schema is not None:
                    props[p["name"]] = schema
            payload = {
                "parent": {"type": "page_id", "page_id": parent_page_id},
                # REST 要求 title 是 rich_text 数组,不是裸字符串
                "title": [{"type": "text", "text": {"content": spec["title"]}}],
                "properties": props,
            }
            resp = client.create_database(payload)
            id_map[spec["title"]] = resp["id"]
    except NotionAPIError as e:
        hint = ""
        if e.status == 404:
            hint = ("(最常见原因:父页面没有分享给 integration——"
                    "在 Notion 页面 ··· → Connections 里添加)")
        raise NotionBootstrapError(
            f"创建 Notion 库失败(已建 {list(id_map)}): {e}{hint}") from e
    except Exception as e:
        raise NotionBootstrapError(
            f"创建 Notion 库失败(已建 {list(id_map)}): {e}") from e
    return id_map
