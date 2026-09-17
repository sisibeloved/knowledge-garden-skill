from __future__ import annotations
import re
from dataclasses import dataclass, field
from .config import Config
from .vault import Vault
from .notion import NotionClient
from .gitutil import Git
from .risk import decide, Decision, Actor
from .frontmatter import dump
from .l1_apply import apply_wikilinks

# Notion 提案的 action → 内部 operation 名(映射到 config.operations)
_ACTION_TO_OP = {
    "link": "add_wikilink",
    "create": "create_evergreen",
    "update": "update_conclusion",
    "delete": "delete_evergreen",
    "move": "move_evergreen",
    "rename": "rename_evergreen",
}


@dataclass
class ApplyResult:
    applied: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


def apply_approved(cfg: Config, vault: Vault, client: NotionClient, git: Git,
                   *, actor: str) -> ApplyResult:
    """轮询 Notion status=approved 的提案 → 经 risk.decide 校验 → 写 Evergreen
    + git commit(带 notion-id)+ 回写 applied_commit。

    授权凭证 = Notion status=approved(sanctioned=True)。无凭证/超能力的写硬禁(BLOCKED)。
    """
    res = ApplyResult()
    actor_enum = Actor(actor)
    approved = client.poll_approved()
    for item in approved:
        props = item.get("properties", {})
        action = props.get("action")
        op = _ACTION_TO_OP.get(action, action)
        # sanctioned=True:来自 Notion status=approved
        d = decide(cfg, actor_enum, op, sanctioned=True)
        if d == Decision.BLOCKED:
            res.blocked.append(item["id"])
            continue
        # 执行写入:create → 写 diff 全文;link → 把 diff 里的建议 [[ ]] 落进笔记
        target = props.get("target", "")
        if action == "create":
            fm = {
                "id": props.get("proposal_id"),
                "type": "concept",
                "title": target,
                "status": "evergreen",
                "sources": [s for s in (props.get("sources", "") or "").split(",") if s],
                "confidence": props.get("confidence", 0.5),
            }
            vault.write(target, dump(fm, props.get("diff", "")), risk_level="L2")
        elif action == "link":
            suggested = re.findall(r"\[\[([^\]|#]+?)\]\]",
                                   props.get("diff", "") or "")
            apply_wikilinks(vault, target, [s.strip() for s in suggested])
        sha = git.commit_all(
            cfg.risk_of(op), f"{action} {target}",
            notion_id=props.get("proposal_id"),
        )
        client.write_applied_commit(item["id"], sha)
        res.applied.append(item["id"])
    return res
