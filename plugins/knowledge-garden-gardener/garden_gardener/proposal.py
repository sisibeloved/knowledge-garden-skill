from __future__ import annotations
import json
import time
from .vault import Vault
from .notion import NotionClient, Proposal
from .audit import AuditReport
from .frontmatter import parse
from .l1_apply import suggest_wikilinks


def _pending_targets(client: NotionClient) -> set[str] | None:
    """查询库里 pending 提案的 target 集合;Notion 不可达返回 None。"""
    try:
        resp = client._send("POST", f"/databases/{client.proposal_db}/query", {
            "filter": {"property": "status", "select": {"equals": "pending"}},
            "page_size": 100,
        })
    except Exception:
        return None
    targets: set[str] = set()
    for r in resp.get("results", []):
        rt = r.get("properties", {}).get("target", {}).get("rich_text", [])
        targets.add("".join(s.get("plain_text", "") for s in rt))
    return targets


def replay_pending(vault: Vault, client: NotionClient,
                   *, skip_targets: set[str] = set(),
                   pending_targets: set[str] | None = None) -> int:
    """把本地暂存的提案补写进 Notion(设计 §错误恢复承诺的"下轮补写")。

    去重两层:skip_targets(本轮即将新生成的目标,暂存副本直接清掉)+
    库里现有 pending 提案的 target(已存在的跳过)。pending_targets 可由
    调用方预先查好传入(emit_proposals 复用,免二次查询)。
    写成功的本地 json 删除;失败保留待下轮。Notion 不可达时返回 0(原地保留)。
    """
    stash_dir = vault.root / "_System/_PendingProposals"
    stashed = sorted(stash_dir.glob("*.json")) if stash_dir.exists() else []
    if not stashed:
        return 0
    if pending_targets is None:
        pending_targets = _pending_targets(client)
        if pending_targets is None:
            return 0  # 不可达 → 留在暂存,下轮再试
    flushed = 0
    for path in stashed:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            prop = Proposal(**data)
        except Exception:
            continue
        # 本轮将新生成同目标提案,或库里已有 pending → 本地副本清掉不回放
        if prop.target in skip_targets or prop.target in pending_targets:
            path.unlink()
            continue
        try:
            client.create_proposal(prop)
        except Exception:
            continue
        path.unlink()
        flushed += 1
    return flushed


def emit_proposals(vault: Vault, client: NotionClient, rep: AuditReport,
                   *, actor: str) -> list[str]:
    """把审计报告转成提案,写 Notion;失败暂存本地 _PendingProposals/。

    防重复:先查库里 pending 的 target——已有 pending 提案的孤岛本轮跳过
    (否则每周 audit 都会给同一批未审批孤岛堆新提案)。Notion 不可达时
    照常生成(失败暂存,下轮 replay 去重)。
    返回成功入 Notion 的 page id 列表。绝不直接 apply(apply 在 apply.py,需 Notion approved)。
    """
    pending = _pending_targets(client)
    replay_pending(vault, client, skip_targets=set(rep.orphans),
                   pending_targets=pending)
    if pending is None:
        orphans = list(rep.orphans)
    else:
        orphans = [o for o in rep.orphans if o not in pending]
    proposals = _from_audit(vault, AuditReport(orphans=orphans))
    page_ids: list[str] = []
    for prop in proposals:
        try:
            pid = client.create_proposal(prop)
            page_ids.append(pid)
        except Exception:
            _stash_locally(vault, prop)
    return page_ids


def _evergreen_titles(vault: Vault) -> set[str]:
    """全部 Evergreen 笔记的 title 集合(补链建议的候选池)。"""
    titles: set[str] = set()
    for pat in ("Concepts/**/*.md", "Notes/**/*.md"):
        for p in vault.read_glob(pat):
            rel = p.relative_to(vault.root).as_posix()
            try:
                fm, _ = parse(vault.read(rel))
            except Exception:
                continue
            if fm.get("title"):
                titles.add(fm["title"])
    return titles


def _from_audit(vault: Vault, rep: AuditReport) -> list[Proposal]:
    """把审计结果转成提案。孤岛 → 补链提案(L2),附具体建议链接。

    建议链接用与 L1 add_wikilink 同一套匹配(suggest_wikilinks):正文命中
    其它 Evergreen 标题。提案 detail 写"现状 + 建议 + 摘录",园主在手机上
    不打开 vault 也能判断批不批。
    """
    titles = _evergreen_titles(vault)
    out: list[Proposal] = []
    ts = time.strftime("%Y-%m-%d")
    for i, target in enumerate(rep.orphans):
        title, body, suggestions, existing = _read_orphan(vault, target, titles)
        if suggestions:
            diff = "建议补链:" + "、".join(f"[[{s}]]" for s in suggestions)
            confidence = 0.6
        else:
            diff = "无自动匹配(正文未命中其它笔记标题),需人工判断相关笔记"
            confidence = 0.4
        detail_lines = [
            f"【现状】《{title or target}》是孤岛笔记:无 links 且无反向链接。",
            f"【建议】{diff}",
            f"【摘录】{_excerpt(body)}",
        ]
        out.append(Proposal(
            proposal_id=f"{ts}-{i+1:03d}", risk="L2", action="link",
            target=target, sources=[], confidence=confidence,
            diff=diff,
            detail="\n".join(detail_lines),
            display=title or "",
        ))
    return out


def _read_orphan(vault: Vault, rel: str, titles: set[str]) -> tuple[str, str, list[str], list[str]]:
    """读孤岛笔记,返回 (title, body, 建议链接, 既有 links)。读不了给空值。"""
    try:
        fm, body = parse(vault.read(rel))
    except Exception:
        return "", "", [], []
    title = fm.get("title") or ""
    suggestions = suggest_wikilinks(body, title, titles, fm.get("links", []))
    return title, body, suggestions, fm.get("links", []) or []


def _excerpt(body: str, limit: int = 160) -> str:
    """正文首段非空文本,截断。"""
    for line in (body or "").splitlines():
        s = line.strip().lstrip("#>").strip()
        if s:
            return s[:limit] + ("…" if len(s) > limit else "")
    return "(空)"


def _stash_locally(vault: Vault, prop: Proposal) -> None:
    """Notion 不可达时,把提案暂存为本地 json,待下轮补写 Notion。"""
    fname = f"{prop.proposal_id}-{prop.action}.json"
    path = vault.root / "_System/_PendingProposals" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(prop.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
