"""triage-inbox 的归类建议:扫 _System/_Inbox,为每条 Raw 给出 next step。

纯只读建议,不写。建议类型:
- task_candidate(从 capture Task 路径降级来的)→ 建议提升为 Notion Task
- 含 URL 的 Raw                → 建议晋升为 Reference(出处)
- 普通概念性 Raw               → 建议提炼为 Evergreen 概念笔记
"""
from __future__ import annotations
import re
from dataclasses import dataclass

from .vault import Vault
from .frontmatter import parse

_INBOX_GLOB = "_System/_Inbox/*.md"
_URL_RE = re.compile(r"https?://\S+")


@dataclass
class TriageSuggestion:
    inbox_rel: str
    action: str       # promote_to_task | promote_to_reference | promote_to_evergreen | review
    suggestion: str   # 人读的建议文本


def suggest(vault: Vault) -> list[TriageSuggestion]:
    """对每个 inbox(status=inbox)项给出归类建议。"""
    out: list[TriageSuggestion] = []
    for p in vault.read_glob(_INBOX_GLOB):
        rel = p.relative_to(vault.root).as_posix()
        try:
            fm, body = parse(vault.read(rel))
        except Exception:
            continue
        if fm.get("status") != "inbox":
            continue
        out.append(_classify(rel, fm, body))
    return out


def _classify(rel: str, fm: dict, body: str) -> TriageSuggestion:
    raw_type = fm.get("type", "raw")
    if raw_type == "task_candidate":
        return TriageSuggestion(rel, "promote_to_task",
                                "标记为任务候选 → 建议提升为 Notion Task")
    if _URL_RE.search(body):
        return TriageSuggestion(rel, "promote_to_reference",
                                "含出处链接 → 建议晋升为 Reference(出处资料)")
    return TriageSuggestion(rel, "promote_to_evergreen",
                            "概念性内容 → 建议提炼为 Evergreen 概念笔记")
