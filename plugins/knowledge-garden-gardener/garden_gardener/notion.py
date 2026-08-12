from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import httpx


@dataclass
class Proposal:
    """Notion「待审核提案」库的一条提案。"""
    proposal_id: str
    risk: str
    action: str          # create | update | delete | move | rename | link
    target: str          # 目标 vault 相对路径
    sources: list[str]   # 来源 Raw id 列表
    confidence: float
    diff: str


class NotionConfigError(Exception):
    """Notion 侧配置缺失(如 tasks/weekly 库 id 未填),调用方据此优雅降级。

    与 httpx 网络异常区分:这是“能力未配置”,不是“服务不可达”。
    """


class NotionClient:
    """Notion 官方 MCP 客户端封装。post 可注入便于测试(默认用 httpx)。

    操作:建提案、轮询 approved、回写 applied_commit、查 Projects 状态(交互③只读)、
    建 Task(capture 路由)、写周报。tasks_db/weekly_db 可选——缺失时对应方法抛
    NotionConfigError,由调用方 catch 降级(不阻断其它动词,对老 config 不硬破坏)。
    """

    def __init__(self, endpoint: str, proposal_db: str, projects_db: str,
                 *, post=None, tasks_db: str = "", weekly_db: str = ""):
        self.endpoint = endpoint
        self.proposal_db = proposal_db
        self.projects_db = projects_db
        self.tasks_db = tasks_db
        self.weekly_db = weekly_db
        self._post = post or self._httpx_post

    def _httpx_post(self, tool: str, payload: dict) -> dict:
        r = httpx.post(f"{self.endpoint}/{tool}", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def create_proposal(self, p: Proposal) -> str:
        """新建一条 pending 提案,返回 Notion page id。"""
        payload = {
            "database_id": self.proposal_db,
            "properties": {
                "proposal_id": p.proposal_id, "risk": p.risk, "action": p.action,
                "target": p.target, "sources": ",".join(p.sources),
                "confidence": p.confidence, "diff": p.diff, "status": "pending",
            },
        }
        resp = self._post("create_page", payload)
        return resp["id"]

    def poll_approved(self) -> list[dict]:
        """轮询 status=approved 的提案,返回结果列表。

        服务端按 filter 过滤,但客户端再防御性过滤一次(status != approved 的绝不返回),
        这是“绝不 apply 未审批写”红线的一道纵深防御。
        """
        resp = self._post("query_database", {
            "database_id": self.proposal_db,
            "filter": {"status": {"equals": "approved"}},
        })
        results = resp.get("results", [])
        return [r for r in results
                if r.get("properties", {}).get("status") == "approved"]

    def write_applied_commit(self, page_id: str, commit_sha: str) -> None:
        """回写:提案 status=applied + applied_commit=sha(跨系统审计链)。"""
        self._post("update_page", {
            "page_id": page_id,
            "properties": {"status": "applied", "applied_commit": commit_sha},
        })

    def query_projects_activity(self) -> list[dict]:
        """交互③:只读查 Projects 本周状态变化(供周报)。"""
        resp = self._post("query_database", {"database_id": self.projects_db})
        return resp.get("results", [])

    def create_task(self, title: str, *, due: str | None = None,
                    priority: str = "中", source_ref: str = "") -> str:
        """capture 路由判定为"任务"时,在 Tasks 库建一条待办,返回 page id。

        due/priority/source_ref 均可选(手机随手记通常只有标题)。
        tasks_db 未配置时抛 NotionConfigError(调用方降级落 Raw Inbox)。
        """
        if not self.tasks_db:
            raise NotionConfigError("tasks_database_id 未配置,capture 无法建 Task")
        props: dict = {"Name": title, "Status": "待办", "Priority": priority}
        if due:
            props["Due"] = due
        if source_ref:
            props["source_ref"] = source_ref
        resp = self._post("create_page", {"database_id": self.tasks_db, "properties": props})
        return resp["id"]

    def write_weekly_report(self, week: str, summary: str, stats: dict) -> str:
        """把周报写入 Notion 周报队列(独立交互库),返回 page id。

        week 形如 "2026-W32";summary 是 markdown 文本(超 2000 字符截断——Notion
        rich_text 限制);stats 含 orphans_count/stale_count/new_evergreen_count/conflicts。
        weekly_db 未配置时抛 NotionConfigError(调用方降级为仅本地 _Reports 副本)。
        """
        if not self.weekly_db:
            raise NotionConfigError("weekly_database_id 未配置,周报无法入 Notion 队列")
        props = {
            "Name": f"{week} 知识周报",
            "week": week,
            # Notion rich_text 单值上限 2000 字符,截断防 API 拒收
            "summary": summary[:2000],
            "orphans_count": stats.get("orphans_count", 0),
            "stale_count": stats.get("stale_count", 0),
            "new_evergreen_count": stats.get("new_evergreen_count", 0),
            "conflicts": stats.get("conflicts", "")[:2000],
            "generated_at": date.today().isoformat(),
        }
        resp = self._post("create_page", {"database_id": self.weekly_db, "properties": props})
        return resp["id"]
