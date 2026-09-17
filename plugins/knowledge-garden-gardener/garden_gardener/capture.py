"""capture 动词:接收手机/手动随手记 → 路由到 Obsidian Raw 或 Notion Task。

路由是二元判定(§4.5.5):明显是"做什么/任务/计划"的 → Task;其余 → Raw。
References/Concepts 是 Evergreen(L2 需审批),capture 是 L0 自由写,不能直接落
Evergreen,所以"出处/资料/不确定"一律先落 Raw Inbox,下轮 triage 提升(§5.5)。

降级:route 到 Task 但 Notion 不可达/db 未配置/client 缺失 → 落 Raw 并标
type=task_candidate(下轮 triage 提示提升)。capture 离线也能落 Raw。
"""
from __future__ import annotations
import hashlib
import time
from dataclasses import dataclass
import httpx

from .vault import Vault
from .notion import NotionClient, NotionConfigError
from .frontmatter import dump

# 任务关键词(短语优先,避免单字误判)。"做什么/计划/进度/截止"类语义。
_TASK_PATTERNS = [
    "任务", "待办", "计划", "完成", "进度", "截止", "deadline", "todo",
    "提醒", "记得", "安排", "要做", "需要做", "应该", "明天", "下周",
    "本周", "due", "finish", "plan",
]

_INBOX_DIR = "_System/_Inbox"


@dataclass
class CaptureResult:
    destination: str       # "task" | "raw" | "raw_fallback"
    path_or_id: str        # Raw 的 vault 相对路径 或 Task 的 Notion page id
    note: str = ""         # 降级/说明文本


def route(text: str) -> str:
    """关键词规则树:含任务语义 → "task",否则 "raw"。纯函数,易测。

    不引入 LLM(依赖最小化);误判由下轮 triage 修正(task_candidate 标记)。
    """
    low = text.lower()
    for kw in _TASK_PATTERNS:
        if kw in low:
            return "task"
    return "raw"


def run_capture(vault: Vault, text: str, *,
                source: str = "manual",
                client: NotionClient | None = None,
                ttl_days: int | None = None) -> CaptureResult:
    """编排:route → 落地。Task 路径失败降级为 Raw(task_candidate)。

    client=None(无 config/离线)时,task 路径直接降级 Raw。capture 始终能落 Raw。
    ttl_days:随手记有效期(天);过期的 Raw 由 weekly-audit 自动归档到
    _System/_Archive/_Inbox/,不删除。
    """
    dest = route(text)

    if dest == "task" and client is not None:
        try:
            pid = client.create_task(text)
            return CaptureResult("task", pid)
        except (NotionConfigError, httpx.HTTPError, httpx.RequestError):
            pass  # 落到下面的降级分支

    if dest == "task":
        # client 不可用/失败 → 降级 Raw,标 task_candidate 待下轮提升
        path = capture_to_raw(vault, text, source, raw_type="task_candidate")
        return CaptureResult("raw_fallback", path,
                             "Task 不可用,落 Inbox(type=task_candidate)待下轮提升")

    path = capture_to_raw(vault, text, source, ttl_days=ttl_days)
    return CaptureResult("raw", path)


def capture_to_raw(vault: Vault, text: str, source: str,
                   *, raw_type: str = "raw", ttl_days: int | None = None) -> str:
    """写一条 Raw 到 _System/_Inbox,返回 vault 相对路径。

    raw_type: "raw"(普通)或 "task_candidate"(从 Task 降级,下轮 triage 提升)。
    ttl_days: 有效期;到期后 weekly-audit 归档(随手记不堆积)。
    frontmatter 遵循设计 §3.3 Raw schema。
    """
    from datetime import date, timedelta
    raw_id = _raw_id(text)
    rel = f"{_INBOX_DIR}/{raw_id}.md"
    fm = {
        "id": raw_id,
        "type": raw_type,
        "source": source,
        "source_url": None,
        "captured_at": _now_iso(),
        "status": "inbox",
        "generated_by": None,
        "needs_review": raw_type == "task_candidate",
        "tags": [],
    }
    if ttl_days is not None and ttl_days > 0:
        fm["expires_at"] = (date.today() + timedelta(days=ttl_days)).isoformat()
    vault.write(rel, dump(fm, text), risk_level="L0")
    return rel


def _raw_id(text: str) -> str:
    ts = time.strftime("%Y-%m-%d-%H%M%S")
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:4]
    return f"raw-{ts}-{h}"


def _now_iso() -> str:
    # 含时区偏移的本地时间(设计示例 captured_at 带时区)
    offset = time.strftime("%z")
    tz = f"{offset[:3]}:{offset[3:]}" if offset else ""
    return time.strftime(f"%Y-%m-%dT%H:%M:%S{tz}")
