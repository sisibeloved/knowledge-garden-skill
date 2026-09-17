"""L1 自动 apply 引擎:weekly-audit 本轮自动执行的低风险写入(无需 Notion 凭证)。

三类 L1 操作(对应 config.operations 里的 L1 档):
- backfill_frontmatter: 补缺失的 id/created_at/updated_at/status
- add_wikilink:         正文命中其它 Evergreen 标题 → frontmatter links + 正文首处 [[ ]]
- add_tag:              英文高频词补 tags(仅 tags 为空时;中文分词待二期)

每类操作经 risk.decide 校验(L1 必返 AUTO)、各自一个 git commit(可整类 revert),
受 batch_l1_max 截断。filesystem 模式下补链退化为关键词(设计 §5.4)。
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from .config import Config
from .vault import Vault
from .gitutil import Git
from .frontmatter import parse, dump
from .risk import decide, Decision, Actor

# 正文 [[ ]] 注入上限:单篇最多补这么多链,避免满屏链接
_MAX_LINKS_PER_NOTE = 5
# add_tag 的英文停用词(避免把 the/and 当 tag)
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "will", "can", "not", "but", "you", "all", "any", "has", "have", "had",
}


@dataclass
class L1Result:
    backfilled: int = 0
    linked: int = 0      # 被补链的笔记数(非链数)
    tagged: int = 0
    commits: list[str] = field(default_factory=list)


def apply_l1(cfg: Config, vault: Vault, git: Git, *,
             actor: str, batch_max: int) -> L1Result:
    """本轮自动执行 L1 操作。每类一个 commit,返回统计 + commit sha 列表。

    任一类 decide 非 AUTO(如 config 把 L1 关了)则跳过该类。batch_max 截断每类处理量。
    """
    res = L1Result()
    actor_enum = Actor(actor)

    # 一次性读入所有 Evergreen(内存 dict 可变,三类操作串行更新同一对象)
    notes = _load_evergreen(vault)

    # --- backfill_frontmatter ---
    if decide(cfg, actor_enum, "backfill_frontmatter", sanctioned=False) == Decision.AUTO:
        changed = []
        for rel, fm, body in notes[:batch_max]:
            if _backfill_one(fm):
                vault.write(rel, dump(fm, body), risk_level="L1")
                changed.append(rel)
        if changed:
            sha = git.commit_all(
                "L1", f"backfill frontmatter on {len(changed)} notes")
            res.backfilled = len(changed)
            res.commits.append(sha)

    # --- add_wikilink ---
    if decide(cfg, actor_enum, "add_wikilink", sanctioned=False) == Decision.AUTO:
        titles = {fm.get("title") for _, fm, _ in notes if fm.get("title")}
        changed = []
        for rel, fm, body in notes[:batch_max]:
            new_links = _find_links(body, fm.get("title"), titles,
                                    fm.get("links", []))
            if new_links:
                body = _apply_links(fm, body, new_links)
                vault.write(rel, dump(fm, body), risk_level="L1")
                changed.append(rel)
        if changed:
            sha = git.commit_all(
                "L1", f"add wikilinks on {len(changed)} notes")
            res.linked = len(changed)
            res.commits.append(sha)

    # --- add_tag ---
    if decide(cfg, actor_enum, "add_tag", sanctioned=False) == Decision.AUTO:
        changed = []
        for rel, fm, body in notes[:batch_max]:
            if fm.get("tags"):  # 已有人工/既有 tags → 不覆盖
                continue
            tags = _extract_tags(body)
            if tags:
                fm["tags"] = tags
                vault.write(rel, dump(fm, body), risk_level="L1")
                changed.append(rel)
        if changed:
            sha = git.commit_all(
                "L1", f"auto-tag on {len(changed)} notes")
            res.tagged = len(changed)
            res.commits.append(sha)

    return res


def _load_evergreen(vault: Vault) -> list[tuple[str, dict, str]]:
    """读入 Concepts/*.md + Notes/*.md,返回 [(rel, fm, body)]。"""
    out = []
    for pat in ("Concepts/**/*.md", "Notes/**/*.md"):  # 递归:支持多级子目录分类
        for p in vault.read_glob(pat):
            rel = p.relative_to(vault.root).as_posix()
            fm, body = parse(vault.read(rel))
            out.append((rel, fm, body))
    return out


def _backfill_one(fm: dict) -> bool:
    """补缺失的 id/created_at/updated_at/status。返回是否改了。

    id 从 title slugify;日期缺则今天;status 缺则 evergreen。
    """
    changed = False
    if not fm.get("id"):
        fm["id"] = "evergreen-" + _slugify(fm.get("title") or "note")
        changed = True
    today = _today_iso()
    if not fm.get("created_at"):
        fm["created_at"] = today
        changed = True
    if not fm.get("updated_at"):
        fm["updated_at"] = today
        changed = True
    if not fm.get("status"):
        fm["status"] = "evergreen"
        changed = True
    return changed


def _slugify(text: str) -> str:
    """标题 → slug(保留中文/字母数字,空格转连字符,小写)。"""
    s = re.sub(r"\s+", "-", (text or "").strip().lower())
    s = re.sub(r"[^\w\u4e00-\u9fff-]", "", s)
    return s or "note"


def _find_links(body: str, current_title, titles: set,
                existing_links) -> list[str]:
    """找出 body 命中、且尚未关联的 Evergreen 标题(排除自引用)。

    用正则边界匹配(避免"检索"误中"检索系统")。最多 _MAX_LINKS_PER_NOTE 条。
    """
    already = {_strip_link(l) for l in (existing_links or [])}
    if current_title:
        already.add(_strip_link(current_title))
    new = []
    for title in titles:
        if not title or title in already or len(title) < 2:
            continue
        if _word_in_body(body, title):
            new.append(title)
            already.add(title)
            if len(new) >= _MAX_LINKS_PER_NOTE:
                break
    return new


def _strip_link(l) -> str:
    return str(l).strip().strip("[]").strip()


def suggest_wikilinks(body: str, title: str, titles: set[str],
                      existing_links=None) -> list[str]:
    """公开补链建议:正文命中哪些 Evergreen 标题(提案生成复用同一套匹配)。

    与 apply_l1 的 add_wikilink 走同一个 _find_links,保证"提案里建议的
    链接"与"批准后自动补的链接"一致。
    """
    return _find_links(body, title, titles, existing_links or [])


def apply_wikilinks(vault: Vault, rel: str, titles: list[str]) -> bool:
    """把 [[titles]] 写入笔记(frontmatter links + 正文首处),返回是否有改动。

    供 apply.py 用:园主批准 link 提案后,把 diff 里的建议链接落到笔记。
    与 L1 add_wikilink 落盘行为一致(同一 _apply_links)。
    """
    if not titles:
        return False
    fm, body = parse(vault.read(rel))
    before = list(fm.get("links") or [])
    body = _apply_links(fm, body, titles)
    if list(fm.get("links") or []) == before:
        return False  # 全部已存在,无改动
    vault.write(rel, dump(fm, body), risk_level="L2")
    return True


def archive_expired_inbox(vault: Vault, git: Git) -> int:
    """归档已过期的随手记:_System/_Inbox 里 expires_at 早于今天的 → _Archive/_Inbox。

    capture --ttl N 写入 expires_at;过期 Raw 移入 _System/_Archive/_Inbox/
    (不删除,归档可翻)。一个 L1 commit,返回归档条数。
    """
    from datetime import date
    import shutil
    today = date.today()
    moved: list[str] = []
    for p in vault.read_glob("_System/_Inbox/*.md"):
        rel = p.relative_to(vault.root).as_posix()
        try:
            fm, _ = parse(vault.read(rel))
        except Exception:
            continue
        exp = fm.get("expires_at")
        if not exp:
            continue
        try:
            if date.fromisoformat(str(exp)[:10]) >= today:
                continue
        except ValueError:
            continue
        dst = vault.root / "_System/_Archive/_Inbox" / p.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dst))
        moved.append(rel)
    if moved:
        git.commit_all("L1", f"archive {len(moved)} expired inbox items")
    return len(moved)


def _word_in_body(body: str, title: str) -> bool:
    """边界匹配:title 前后不是字母数字/中文(避免子串误中)。"""
    # \w 含字母数字下划线;额外排除中文邻接(用负 lookahead/lookbehind)
    pat = rf"(?<![\w\u4e00-\u9fff]){re.escape(title)}(?![\w\u4e00-\u9fff])"
    return re.search(pat, body) is not None


def _apply_links(fm: dict, body: str, new_links: list[str]) -> str:
    """把补链落到 frontmatter links + 正文首处 [[ ]],返回更新后的 body。"""
    existing = fm.get("links") or []
    if isinstance(existing, str):
        existing = [existing]
    merged = list(existing)
    for t in new_links:
        val = f"[[{t}]]"
        if val not in merged:
            merged.append(val)
    fm["links"] = merged
    # 正文:每个标题替换第一处出现为 [[标题]](有限增强,不全替换)
    for t in new_links:
        body = re.sub(
            rf"(?<![\w\u4e00-\u9fff]){re.escape(t)}(?![\w\u4e00-\u9fff])",
            f"[[{t}]]", body, count=1)
    return body


def _extract_tags(body: str, max_tags: int = 3) -> list[str]:
    """从正文提英文高频词作 tags(长度≥3,至少出现 2 次)。

    中文不分词(待二期 A-Mem/分词)。仅 tags 为空时调用(见 apply_l1)。
    """
    words = re.findall(r"[A-Za-z][a-z]{2,}", body)
    freq: dict[str, int] = {}
    for w in words:
        wl = w.lower()
        if wl in _STOPWORDS:
            continue
        freq[wl] = freq.get(wl, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, c in ranked if c >= 2][:max_tags]


def _today_iso() -> str:
    from datetime import date
    return date.today().isoformat()
