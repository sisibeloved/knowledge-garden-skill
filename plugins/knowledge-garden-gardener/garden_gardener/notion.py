"""Notion 官方 REST API 客户端(transport 层)。

协议:Notion REST API v1(NOTION_VERSION 2022-06-28),internal integration
token 认证(Bearer)。业务方法(create_proposal/poll_approved/...)对上层保持
"扁平属性"契约——Notion 的类型化属性对象(select/rich_text/...)在本层归一化,
apply.py 等业务代码不感知 wire 格式。

token 解析:显式 token 参数 > 环境变量 token_env(默认 NOTION_TOKEN)。
secret 走环境变量而非 config 文本,vault 里的 config 可安全入 Git。

send 注入点:send(method, path, json) -> dict,测试用它锁 REST 契约。
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import date
import httpx

API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_TOKEN_ENV = "NOTION_TOKEN"

# Notion rich_text 单值上限 2000 字符,超长截断防 API 拒收
_RICH_TEXT_MAX = 2000


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
    detail: str = ""     # 给园主看的说明(写入 Notion 页面正文)
    display: str = ""    # 展示名(缺省用 target 文件名;提案标题用)


# 提案标题的 action 中文标签(移动端列表一眼可读)
_ACTION_LABELS = {
    "link": "补链", "create": "新建", "update": "改结论",
    "delete": "删除", "move": "移动", "rename": "重命名",
}


def proposal_title(p: "Proposal") -> str:
    """提案在 Notion 列表里的展示标题:【补链】昇腾产品线 (2026-09-17-001)。

    proposal_id 保留在尾部,apply 的审计链(commit message/fm id)仍可追溯。
    """
    from pathlib import PurePosixPath
    stem = p.display or (PurePosixPath(p.target).stem or p.target)
    label = _ACTION_LABELS.get(p.action, p.action)
    return f"【{label}】{stem}({p.proposal_id})"


class NotionConfigError(Exception):
    """Notion 侧配置缺失(如 tasks/weekly 库 id 未填),调用方据此优雅降级。

    与网络异常区分:这是"能力未配置",不是"服务不可达"。
    """


class NotionAPIError(httpx.HTTPError):
    """Notion REST API 返回 4xx/5xx。携带 status + 服务端 message。

    继承 httpx.HTTPError:cli_entry/proposal/weekly_report 现有的
    `except (httpx.HTTPError, httpx.RequestError)` 降级路径无需改动。
    """

    def __init__(self, status: int, message: str):
        super().__init__(f"Notion API {status}: {message}")
        self.status = status
        self.message = message


# ---------- 属性值构造(业务侧扁平值 → Notion 类型化属性) ----------

def title_value(s: str) -> dict:
    return {"title": [{"text": {"content": s}}]}


def rich_text_value(s: str) -> dict:
    return {"rich_text": [{"text": {"content": (s or "")[:_RICH_TEXT_MAX]}}]}


def select_value(name: str) -> dict:
    return {"select": {"name": name}}


def number_value(n) -> dict:
    return {"number": n}


def date_value(d: str | None) -> dict:
    return {"date": {"start": d} if d else None}


def url_value(u: str) -> dict:
    return {"url": u}


def _para(text: str) -> dict:
    """Notion 段落块(页面正文 children 用)。"""
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": (text or "")[:2000]}}]}}


# ---------- 属性值归一化(Notion 类型化属性 → 业务侧扁平值) ----------

# property 对象里恰好含一个"值类型"键;按它提取标量
_VALUE_KEYS = ("title", "rich_text", "number", "select", "multi_select",
               "status", "date", "url", "checkbox", "email", "phone_number",
               "created_time", "last_edited_time")


def _scalar(value: object, kind: str):
    if kind in ("title", "rich_text"):
        return "".join(seg.get("plain_text", "") for seg in value or [])
    if kind in ("select", "status"):
        return (value or {}).get("name", "")
    if kind == "multi_select":
        return ",".join(o.get("name", "") for o in value or [])
    if kind == "number":
        return value
    if kind == "date":
        return (value or {}).get("start", "") if value else ""
    if kind == "url":
        return value or ""
    return value


def flatten_properties(props: dict) -> dict:
    """把 Notion page 的 properties(类型化对象)归一化为扁平标量 dict。"""
    flat: dict = {}
    for name, obj in (props or {}).items():
        if not isinstance(obj, dict):
            flat[name] = obj
            continue
        for kind in _VALUE_KEYS:
            if kind in obj:
                flat[name] = _scalar(obj[kind], kind)
                break
        else:
            flat[name] = obj  # 未知类型(people/relation/...),原样保留
    return flat


class NotionClient:
    """Notion REST API 客户端。

    操作:建提案、轮询 approved、回写 applied_commit、查 Projects 状态(交互③只读)、
    建 Task(capture 路由)、写周报、建库(init)。tasks_db/weekly_db 可选——缺失时
    对应方法抛 NotionConfigError,由调用方 catch 降级(不阻断其它动词)。
    """

    def __init__(self, *, proposal_db: str = "", projects_db: str = "",
                 tasks_db: str = "", weekly_db: str = "",
                 api_base: str = API_BASE, token: str | None = None,
                 token_env: str = DEFAULT_TOKEN_ENV, send=None):
        self.api_base = api_base.rstrip("/")
        self.proposal_db = proposal_db
        self.projects_db = projects_db
        self.tasks_db = tasks_db
        self.weekly_db = weekly_db
        self.token = token if token is not None else os.environ.get(token_env, "")
        self.token_env = token_env
        self._send = send or self._httpx_send

    # ---- transport ----

    def _httpx_send(self, method: str, path: str, json: dict | None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        r = httpx.request(method, f"{self.api_base}{path}",
                          json=json, headers=headers, timeout=30)
        if r.status_code >= 400:
            try:
                message = r.json().get("message", r.text)
            except Exception:
                message = r.text
            raise NotionAPIError(r.status_code, message)
        return r.json()

    def me(self) -> dict:
        """GET /users/me —— token 有效性 + 连通性检查(init 第一步)。"""
        return self._send("GET", "/users/me", None)

    def create_database(self, payload: dict) -> dict:
        """POST /databases —— 在 parent page 下建库(init 用)。"""
        return self._send("POST", "/databases", payload)

    # ---- 业务操作(扁平属性进出) ----

    def create_proposal(self, p: Proposal) -> str:
        """新建一条 pending 提案,返回 Notion page id。

        标题用人类可读格式(proposal_title);detail 写入页面正文段落块,
        移动端点开即知要审什么(现状/建议/摘录),不用回 vault 翻文件。
        """
        props = {
            "proposal_id": title_value(proposal_title(p)),
            "created_at": date_value(date.today().isoformat()),
            "status": select_value("pending"),
            "risk": select_value(p.risk),
            "action": select_value(p.action),
            "target": rich_text_value(p.target),
            "sources": rich_text_value(",".join(p.sources)),
            "confidence": number_value(p.confidence),
            "diff": rich_text_value(p.diff),
        }
        payload = {
            "parent": {"database_id": self.proposal_db},
            "properties": props,
        }
        if p.detail:
            payload["children"] = [_para(line) for line in
                                   p.detail.splitlines() if line.strip()]
        resp = self._send("POST", "/pages", payload)
        return resp["id"]

    def archive_page(self, page_id: str) -> None:
        """归档页面(红线:Notion 侧永不删除,清理一律用归档)。"""
        self._send("PATCH", f"/pages/{page_id}", {"archived": True})

    def poll_approved(self) -> list[dict]:
        """轮询 status=approved 的提案,返回 [{id, properties(扁平)}]。

        服务端按 filter 过滤,但客户端再防御性过滤一次(status != approved 的绝不
        返回)——"绝不 apply 未审批写"红线的一道纵深防御。
        """
        resp = self._send("POST", f"/databases/{self.proposal_db}/query", {
            "filter": {"property": "status", "select": {"equals": "approved"}},
        })
        out: list[dict] = []
        for r in resp.get("results", []):
            flat = flatten_properties(r.get("properties", {}))
            if flat.get("status") == "approved":
                out.append({"id": r["id"], "properties": flat})
        return out

    def write_applied_commit(self, page_id: str, commit_sha: str) -> None:
        """回写:提案 status=applied + applied_commit=sha(跨系统审计链)。"""
        self._send("PATCH", f"/pages/{page_id}", {
            "properties": {
                "status": select_value("applied"),
                "applied_commit": rich_text_value(commit_sha),
            },
        })

    def query_projects_activity(self) -> list[dict]:
        """交互③:只读查 Projects 近期状态(供周报)。"""
        resp = self._send("POST", f"/databases/{self.projects_db}/query",
                          {"page_size": 100})
        return [{"id": r.get("id"),
                 "properties": flatten_properties(r.get("properties", {}))}
                for r in resp.get("results", [])]

    def create_task(self, title: str, *, due: str | None = None,
                    priority: str = "中", source_ref: str = "") -> str:
        """capture 路由判定为"任务"时,在 Tasks 库建一条待办,返回 page id。

        due/priority/source_ref 均可选(手机随手记通常只有标题)。
        tasks_db 未配置时抛 NotionConfigError(调用方降级落 Raw Inbox)。
        """
        if not self.tasks_db:
            raise NotionConfigError("tasks_database_id 未配置,capture 无法建 Task")
        props: dict = {
            "Name": title_value(title),
            "Status": select_value("待办"),
            "Priority": select_value(priority),
        }
        if due:
            props["Due"] = date_value(due)
        if source_ref:
            props["source_ref"] = url_value(source_ref)
        resp = self._send("POST", "/pages", {
            "parent": {"database_id": self.tasks_db},
            "properties": props,
        })
        return resp["id"]

    def write_weekly_report(self, week: str, summary: str, stats: dict) -> str:
        """把周报写入 Notion 周报队列(独立交互库),返回 page id。

        week 形如 "2026-W32";summary 是 markdown 文本(超 2000 字符截断——
        Notion rich_text 限制);stats 含 orphans_count/stale_count/new_evergreen_count/conflicts。
        weekly_db 未配置时抛 NotionConfigError(调用方降级为仅本地 _Reports 副本)。
        """
        if not self.weekly_db:
            raise NotionConfigError("weekly_database_id 未配置,周报无法入 Notion 队列")
        props = {
            "Name": title_value(f"{week} 知识周报"),
            "week": rich_text_value(week),
            "summary": rich_text_value(summary),
            "orphans_count": number_value(stats.get("orphans_count", 0)),
            "stale_count": number_value(stats.get("stale_count", 0)),
            "new_evergreen_count": number_value(stats.get("new_evergreen_count", 0)),
            "conflicts": rich_text_value(stats.get("conflicts", "")),
            "generated_at": date_value(date.today().isoformat()),
        }
        resp = self._send("POST", "/pages", {
            "parent": {"database_id": self.weekly_db},
            "properties": props,
        })
        return resp["id"]
