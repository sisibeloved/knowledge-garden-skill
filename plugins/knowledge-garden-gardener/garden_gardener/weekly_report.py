"""周报生成:审计数据 + Projects 活动 → markdown 报告 → 双写(本地 + Notion 队列)。

设计 §5.5:周报是 Notion 移动端"本周知识摘要"交互队列。本地 _Reports/weekly-report.md
留 Git 留底可 diff;Notion 周报库(若配置)入移动端队列。Notion 不可达/db 未配置时
仅写本地,不阻断 weekly-audit。
"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from datetime import date
import httpx

from .vault import Vault
from .notion import NotionClient, NotionConfigError
from .audit import AuditReport
from .frontmatter import parse

_REPORT_PATH = "_System/_Reports/weekly-report.md"


@dataclass
class WeeklyStats:
    week: str                   # ISO 周,如 "2026-W32"
    markdown: str               # 完整 markdown 报告
    orphans_count: int
    stale_count: int
    new_evergreen_count: int
    inbox_count: int
    conflicts: str              # 冲突摘要(供 Notion conflicts 字段)


def summarize(vault: Vault, rep: AuditReport,
              projects_activity: list[dict]) -> WeeklyStats:
    """汇总审计 + Projects 活动 → WeeklyStats(含 markdown + counts)。"""
    week = _week_str()
    new_count = _count_new_this_week(vault)
    conflicts_text = _format_conflicts(rep.conflicts)

    md = _build_markdown(
        week=week,
        rep=rep,
        new_count=new_count,
        conflicts_text=conflicts_text,
        projects_activity=projects_activity,
    )
    return WeeklyStats(
        week=week, markdown=md,
        orphans_count=len(rep.orphans), stale_count=len(rep.stale),
        new_evergreen_count=new_count, inbox_count=len(rep.inbox_pending),
        conflicts=conflicts_text,
    )


def publish(vault: Vault, client: NotionClient, stats: WeeklyStats) -> None:
    """双写周报。本地 _Reports 副本始终写;Notion 队列不可达/未配置时降级。

    任何 Notion 侧异常都不阻断本地写入与 weekly-audit 主流程。
    """
    # 1. 本地副本(始终写,入 Git 可 diff/多机同步)
    vault.write(_REPORT_PATH, stats.markdown, risk_level="L0")

    # 2. Notion 周报队列(可选,失败降级为 stderr 警告)
    notion_stats = {
        "orphans_count": stats.orphans_count,
        "stale_count": stats.stale_count,
        "new_evergreen_count": stats.new_evergreen_count,
        "conflicts": stats.conflicts,
    }
    try:
        client.write_weekly_report(stats.week, stats.markdown, notion_stats)
    except NotionConfigError as e:
        # db 未配置 → 静默降级(本地已写)
        print(f"warn: 周报未入 Notion 队列({e})", file=sys.stderr)
    except (httpx.HTTPError, httpx.RequestError) as e:
        # 服务不可达 → 降级,本地已写,下轮再推
        print(f"warn: 周报入 Notion 失败,本地副本已写({e})", file=sys.stderr)


def _build_markdown(*, week, rep: AuditReport, new_count: int,
                    conflicts_text: str, projects_activity: list[dict]) -> str:
    lines = [
        f"# 知识周报 {week}",
        "",
        f"生成于 {date.today().isoformat()}",
        "",
        "## 概览",
        f"- 本周新增 Evergreen: {new_count}",
        f"- 孤岛笔记: {len(rep.orphans)}",
        f"- 过期待复核: {len(rep.stale)}",
        f"- Inbox 待处理: {len(rep.inbox_pending)}",
        "",
    ]
    lines += _section("孤岛清单", rep.orphans)
    lines += _section("过时清单", rep.stale)
    lines += _section("Inbox 待处理", rep.inbox_pending)
    lines += ["## 冲突", conflicts_text or "（无）", ""]
    lines += _projects_section(projects_activity)
    return "\n".join(lines)


def _section(title: str, items: list[str]) -> list[str]:
    if not items:
        return [f"## {title}", "（无）", ""]
    out = [f"## {title}"]
    out += [f"- {i}" for i in items]
    out.append("")
    return out


def _projects_section(projects_activity: list[dict]) -> list[str]:
    out = ["## Projects 活动"]
    if not projects_activity:
        out.append("（无）")
        out.append("")
        return out
    for p in projects_activity:
        props = p.get("properties", {}) if isinstance(p, dict) else {}
        name = _extract(props, ["Name", "title"]) or "(未命名)"
        status = _extract(props, ["Status", "status"]) or ""
        out.append(f"- {name}" + (f" — {status}" if status else ""))
    out.append("")
    return out


def _extract(props: dict, keys: list[str]) -> str:
    """从 Notion properties 里取标量值(容忍多种 schema)。"""
    for k in keys:
        v = props.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _format_conflicts(conflicts) -> str:
    """conflicts 是 list[tuple[str, str]](设计预留,当前 audit 不产出)。"""
    if not conflicts:
        return ""
    return "; ".join(f"{a} ⇄ {b}" for a, b in conflicts)


def _count_new_this_week(vault: Vault) -> int:
    """扫 Evergreen created_at,数本周(ISO 周)新增。"""
    week = _week_str()
    count = 0
    for pat in ("Concepts/**/*.md", "Notes/**/*.md"):  # 递归:支持多级子目录分类
        for p in vault.read_glob(pat):
            rel = p.relative_to(vault.root).as_posix()
            try:
                fm, _ = parse(vault.read(rel))
            except Exception:
                continue
            created = fm.get("created_at")
            if created and _iso_week_of(created) == week:
                count += 1
    return count


def _week_str() -> str:
    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _iso_week_of(s) -> str:
    """把 created_at(可能含时间)转成 ISO 周串。"""
    try:
        return f"{date.fromisoformat(str(s)[:10]).isocalendar().year}-W" \
               f"{date.fromisoformat(str(s)[:10]).isocalendar().week:02d}"
    except Exception:
        return ""
