from __future__ import annotations
import json
import time
from .vault import Vault
from .notion import NotionClient, Proposal
from .audit import AuditReport


def emit_proposals(vault: Vault, client: NotionClient, rep: AuditReport,
                   *, actor: str) -> list[str]:
    """把审计报告转成提案,写 Notion;失败暂存本地 _PendingProposals/。

    返回成功入 Notion 的 page id 列表。绝不直接 apply(apply 在 apply.py,需 Notion approved)。
    """
    proposals = _from_audit(rep)
    page_ids: list[str] = []
    for prop in proposals:
        try:
            pid = client.create_proposal(prop)
            page_ids.append(pid)
        except Exception:
            _stash_locally(vault, prop)
    return page_ids


def _from_audit(rep: AuditReport) -> list[Proposal]:
    """把审计结果转成提案。孤岛 → 补链提案(L2)。"""
    out: list[Proposal] = []
    ts = time.strftime("%Y-%m-%d")
    for i, target in enumerate(rep.orphans):
        out.append(Proposal(
            proposal_id=f"{ts}-{i+1:03d}", risk="L2", action="link",
            target=target, sources=[], confidence=0.5,
            diff="(建议补链:此笔记无链接,待智能匹配相关笔记)",
        ))
    return out


def _stash_locally(vault: Vault, prop: Proposal) -> None:
    """Notion 不可达时,把提案暂存为本地 json,待下轮补写 Notion。"""
    fname = f"{prop.proposal_id}-{prop.action}.json"
    path = vault.root / "_System/_PendingProposals" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(prop.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
