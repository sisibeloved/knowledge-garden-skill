from __future__ import annotations
from .notion import NotionClient

# 属性类型简写:Notion API 的 property schema。init 时用这些定义建库。
def _prop(name, ptype, **extra):
    d = {"name": name, "type": ptype}
    d.update(extra)
    return d


def _select(name, options):
    return _prop(name, "select", options=[{"name": o} for o in options])


def _multi(name, options):
    return _prop(name, "multi_select", options=[{"name": o} for o in options])


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
            _prop("Project", "relation"),  # relation 到 Projects(运行时补)
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


def create_all_databases(client: NotionClient, *, parent_page_id: str) -> dict[str, str]:
    """在指定 parent page 下创建 5 个库,返回 {库名: database_id}。

    失败抛 NotionBootstrapError(不部分建——保持原子性,调用方可清理后重试)。
    """
    id_map: dict[str, str] = {}
    try:
        for spec in NOTION_DATABASES:
            resp = client._post("create_database", {
                "parent": {"page_id": parent_page_id},
                "title": spec["title"],
                "properties": {p["name"]: {"type": p["type"]} for p in spec["properties"]},
            })
            id_map[spec["title"]] = resp["id"]
    except Exception as e:
        raise NotionBootstrapError(f"创建 Notion 库失败(已建 {list(id_map)}): {e}") from e
    return id_map
