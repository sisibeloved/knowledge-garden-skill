from __future__ import annotations
from dataclasses import dataclass
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


class NotionClient:
    """Notion 官方 MCP 客户端封装。post 可注入便于测试(默认用 httpx)。

    四类操作:建提案、轮询 approved、回写 applied_commit、查 Projects 状态(交互③只读)。
    """

    def __init__(self, endpoint: str, proposal_db: str, projects_db: str, *, post=None):
        self.endpoint = endpoint
        self.proposal_db = proposal_db
        self.projects_db = projects_db
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
