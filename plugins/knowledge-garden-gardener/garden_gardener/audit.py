from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from .vault import Vault
from .frontmatter import parse


def _today() -> date:
    return date.today()


@dataclass
class AuditReport:
    orphans: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)
    inbox_pending: list[str] = field(default_factory=list)
    broken: list[tuple[str, str]] = field(default_factory=list)
    # broken = (引用方笔记, 断链名):links 指向的笔记已不存在(如被手动删除)


def audit(vault: Vault, *, orphan_age_days: int = 7, stale_days: int = 90) -> AuditReport:
    """只读审计:找孤岛/过时/Inbox 待处理。纯读,零写入 Evergreen。"""
    rep = AuditReport()
    today = _today()
    orphan_cutoff = today - timedelta(days=orphan_age_days)
    stale_cutoff = today - timedelta(days=stale_days)

    # 收集所有 Evergreen 笔记 + 反向链接统计
    backlinks: dict[str, int] = {}
    all_titles: set[str] = set()
    evergreen: list[tuple[str, dict]] = []
    for glob_pat in ("Concepts/**/*.md", "Notes/**/*.md"):  # 递归:支持多级子目录分类
        for p in vault.read_glob(glob_pat):
            rel = p.relative_to(vault.root).as_posix()
            fm, _body = parse(vault.read(rel))
            evergreen.append((rel, fm))
            if fm.get("title"):
                all_titles.add(fm["title"])
            for ln in fm.get("links", []) or []:
                name = ln.strip("[]")
                backlinks[name] = backlinks.get(name, 0) + 1

    for rel, fm in evergreen:
        links = fm.get("links", []) or []
        title = fm.get("title") or ""
        stem = Path(rel).stem
        # 反链按 title 或文件名匹配(双链常用文件名,未必等于 title)
        has_backlink = backlinks.get(title, 0) > 0 or backlinks.get(stem, 0) > 0
        reviewed = fm.get("last_reviewed_at") or fm.get("created_at")
        is_old = _parse_date(reviewed) <= orphan_cutoff if reviewed else True
        # 孤岛:无 links 且无反向链接 且 较老
        if not links and not has_backlink and is_old:
            rep.orphans.append(rel)
        # 过时:有复核日期且超过阈值
        if reviewed and _parse_date(reviewed) <= stale_cutoff:
            rep.stale.append(rel)

    # 断链:links 指向的笔记不存在(手动删除后遗留)。
    # 存在性按"任意文件名/去扩展名 stem + 任意笔记 title"判定:含 Index/MOC
    # 等非 Evergreen,也含 _attachments/ 图片(链接常带扩展名,stem 不带)。
    existing = set(all_titles)
    for p in vault.root.rglob("*"):
        if p.is_file() and not any(part.startswith(".") for part in p.parts):
            existing.add(p.name)
            existing.add(p.stem)
    for rel, fm in evergreen:
        for ln in fm.get("links", []) or []:
            # rstrip("\\"):表格内别名链接 [[X\|alias]] 的 X 尾带转义管道的 "\"
            name = str(ln).strip().strip("[]").strip().rstrip("\\").strip()
            if name and name not in existing:
                rep.broken.append((rel, name))

    # Inbox 待处理
    for p in vault.read_glob("_System/_Inbox/*.md"):
        rel = p.relative_to(vault.root).as_posix()
        fm, _ = parse(vault.read(rel))
        if fm.get("status") == "inbox":
            rep.inbox_pending.append(rel)
    return rep


def _parse_date(s) -> date:
    if isinstance(s, date):
        return s
    return date.fromisoformat(str(s)[:10])
