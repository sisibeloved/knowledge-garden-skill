from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
import httpx
from .config import load_config
from .vault import Vault
from .notion import NotionClient, API_BASE, DEFAULT_TOKEN_ENV
from .gitutil import Git
from .audit import audit
from .proposal import emit_proposals
from .apply import apply_approved
from .l1_apply import apply_l1
from .weekly_report import summarize as summarize_report, publish as publish_report
from .capture import run_capture
from .triage import suggest as triage_suggestions
from .init_orchestrator import run_init, COMPLETED, NEEDS_OAUTH
from .init_notion import NotionBootstrapError
from .init_plugins import install_instructions


def parse_page_ref(ref: str) -> str:
    """接受 Notion 页面 URL / 带/不带连字符的 page id,返回 32-hex id。

    URL 形如 https://www.notion.so/Page-Title-<32hex>?v=<view-id>;
    ?v= 是 view id 不是 page id,必须丢弃。
    """
    s = (ref or "").strip()
    if not s:
        raise ValueError("parent page 为空")
    seg = s.split("?")[0].split("#")[0].rstrip("/").split("/")[-1]
    m = re.search(r"([0-9a-fA-F]{32})$", seg)
    if m:
        return m.group(1).lower()
    compact = re.sub(r"[^0-9a-fA-F]", "", s)
    if len(compact) == 32:
        return compact.lower()
    raise ValueError(f"无法从 {ref!r} 解析出 page id(粘贴页面完整链接,或 32 位 id)")


def _client_from_config(cfg, *, with_weekly: bool = True) -> NotionClient:
    """从 config notion 段构造 client。

    api_base 兼容旧 key mcp_endpoint(旧 config 不破坏;其值原样当 REST base 用)。
    """
    n = cfg.notion
    api_base = n.get("api_base") or n.get("mcp_endpoint") or API_BASE
    return NotionClient(
        proposal_db=n["proposal_database_id"],
        projects_db=n["projects_database_id"],
        tasks_db=n.get("tasks_database_id", ""),
        weekly_db=n.get("weekly_database_id", "") if with_weekly else "",
        api_base=api_base,
        token_env=n.get("token_env", DEFAULT_TOKEN_ENV),
    )


def _init_config_path(args) -> Path:
    """init 的 config 输出路径:显式 --config 用之,否则 <vault>/_Config/。

    不能用 argparse default 相对路径——它相对 CWD 解析,init 会把 config
    写到调用者所在目录而不是 vault 里。
    """
    if args.config:
        return Path(args.config)
    return Path(args.vault) / "_Config" / "gardener.config.yaml"


def _cmd_init(args) -> int:
    """garden init: 引导整个知识花园(vault + Notion + 插件清单)。

    授权是唯一人工断点(建 integration + 设 token + 分享页面):首次跑返回
    NEEDS_OAUTH(exit 3),打印指引;完成后带 --auth-done 重跑即可续。
    Notion 不可达时返回 exit 4 + 友好消息(不抛栈),checkpoint 保留可续跑。
    """
    try:
        parent_page = parse_page_ref(args.parent_page)
    except ValueError as e:
        print(f"--parent-page 参数错误:{e}", file=sys.stderr)
        return 1
    client = NotionClient(api_base=args.api_base, token_env=args.token_env)
    try:
        result = run_init(
            vault_root=Path(args.vault),
            config_path=_init_config_path(args),
            checkpoint=Path(args.vault) / ".garden-init.json",
            client=client,
            parent_page_id=parent_page,
            oauth_already_done=args.auth_done,
        )
    except NotionBootstrapError as e:
        print("=" * 60, file=sys.stderr)
        print("Notion 连接失败,无法建库。", file=sys.stderr)
        print(f"原因:{e}", file=sys.stderr)
        print("已完成的步骤已保存,修复后重新运行同样的命令即可续跑(不会重头)。", file=sys.stderr)
        print("常见原因:NOTION_TOKEN 未设置/token 无效、父页面未分享给 integration、网络不通。", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return 4
    if result == NEEDS_OAUTH:
        print("=" * 60)
        print("需要完成 Notion 授权(唯一人工步骤,integration token 方式):")
        print("  1. 打开 https://www.notion.so/my-integrations → New integration")
        print("     (类型 Internal, capability 勾 Insert content + Update content)")
        print("  2. 复制 Internal Token(ntn_ 开头),设置环境变量:")
        print(f"       {args.token_env}=ntn-xxxx")
        print("  3. 在 Notion 里打开父页面 → 右上 ··· → Connections →")
        print("     添加刚建的 integration(只授权这一个页面,scope 最小化)")
        print("  4. 完成后重新运行(带 --auth-done):")
        print(f"       garden init --vault {args.vault} \\")
        print(f"         --parent-page {args.parent_page} --auth-done")
        print("=" * 60)
        return 3
    print("init 完成。", install_instructions(Path(args.vault)))
    print("\n下一步:在 Obsidian 内打开此 vault,装好插件后即可运行 weekly-audit。")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="garden")
    # --config 默认 None;子命令执行时再 fallback 到 <vault>/_Config/gardener.config.yaml。
    # 这样无 Notion 业务依赖的命令(triage-inbox)在不传 config 时也能跑。
    p.add_argument("--config", default=None)
    p.add_argument("--vault", default=".")
    p.add_argument("--actor", default="manual_session",
                   choices=["manual_session", "scheduled_run"])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("weekly-audit")
    sub.add_parser("apply-approved")
    sub.add_parser("triage-inbox")
    sub.add_parser("review-orphans")
    cap_p = sub.add_parser("capture", help="手机/手动随手记 → 路由 Raw 或 Notion Task")
    cap_p.add_argument("--text", required=True, help="随手记文本")
    cap_p.add_argument("--source", default="manual", help="来源(manual/web/...)")

    init_p = sub.add_parser("init", help="引导知识花园(vault+Notion+插件清单)")
    # init 有独立的 --vault/--config(init 是创建 config,不读取),故在此子命令重新声明
    init_p.add_argument("--vault", default=".",
                        help="vault 根目录(init 会在此建骨架+config)")
    init_p.add_argument("--config", default=None,
                        help="config 输出路径(默认 <vault>/_Config/gardener.config.yaml)")
    init_p.add_argument("--parent-page", required=True,
                        help="Notion 父页面 URL 或 page id,5 个库建在其下")
    init_p.add_argument("--api-base", default=API_BASE,
                        help="Notion REST API base(默认官方 https://api.notion.com/v1)")
    init_p.add_argument("--token-env", default=DEFAULT_TOKEN_ENV,
                        help="读 token 的环境变量名(默认 NOTION_TOKEN)")
    init_p.add_argument("--auth-done", action="store_true",
                        help="已完成 integration token 配置 + 父页面分享(首次跑不要带)")
    init_p.add_argument("--oauth-done", action="store_true",
                        help="已废弃,--auth-done 的别名(兼容旧脚本)")

    args = p.parse_args(argv)

    def _resolve_config_path() -> Path:
        """优先用 --config 显式值,否则回落到 <vault>/_Config/gardener.config.yaml。

        注意:即使业务上不需要 config(如 triage-inbox),argparse 也已注册了 --config,
        在 main() 顶端调用此函数来统一处理,避免空字符串或相对 CWD 的默认值让业务 hang。
        """
        if args.config:
            return Path(args.config)
        return Path(args.vault) / "_Config" / "gardener.config.yaml"

    if args.cmd == "init":
        # --oauth-done 是 --auth-done 的废弃别名
        args.auth_done = args.auth_done or args.oauth_done
        return _cmd_init(args)

    vault = Vault(Path(args.vault))
    git = Git(Path(args.vault))
    # 仅有 Notion 依赖的命令(weekly-audit / apply-approved)才需要 config。
    # triage-inbox 是纯本地读 vault,不读 config——早期让它必须依赖 config 是设计误差。
    config_path = _resolve_config_path()

    if args.cmd == "triage-inbox":
        rep = audit(vault)
        suggestions = triage_suggestions(vault)
        print(f"{len(rep.inbox_pending)} inbox items pending triage:")
        for s in suggestions:
            print(f"  [{s.action}] {s.inbox_rel} — {s.suggestion}")
        return 0

    if args.cmd == "capture":
        # capture 不强制 config(离线可落 Raw);有 config 才建 client 供 Task 路径。
        # 与 weekly-audit/apply-approved 不同:config 缺失不阻断,降级为仅 Raw。
        cap_client = None
        try:
            cap_cfg = load_config(config_path)
            cap_client = _client_from_config(cap_cfg, with_weekly=False)
        except FileNotFoundError:
            pass  # 无 config → 只落 Raw(正常路径,不警告)
        except Exception as e:
            print(f"warn: config 加载失败,capture 仅落 Raw({e})", file=sys.stderr)
        res = run_capture(vault, args.text, source=args.source, client=cap_client)
        line = f"captured → {res.destination}: {res.path_or_id}"
        if res.note:
            line += f" ({res.note})"
        print(line)
        return 0

    # weekly-audit / apply-approved 路径:必须先 load_config
    try:
        cfg = load_config(config_path)
    except FileNotFoundError:
        print("=" * 60, file=sys.stderr)
        print(f"找不到 config:{config_path}", file=sys.stderr)
        print("若 vault 是首次搭建,请先跑 `garden init --vault <vault>`。", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return 5
    client = _client_from_config(cfg)

    if args.cmd == "weekly-audit":
        if not git.pull():
            print("ABORT: git pull failed; 不基于脏数据跑", file=sys.stderr)
            return 2
        rep = audit(
            vault,
            orphan_age_days=cfg.thresholds["orphan_age_days"],
            stale_days=cfg.thresholds.get("stale_review_days", 90),
        )
        try:
            emit_proposals(vault, client, rep, actor=args.actor)
        except (httpx.HTTPError, httpx.RequestError) as e:
            # Notion 不可达时 weekly-audit 必须优雅降级而不是挂掉:
            # proposal.py 里已经各自 _stash_locally,但万一 init 连接时直接挂
            # (endpoint 完全不可达 → SSL/Protocol/Timeout 异常),必须 catch 住。
            print(f"warn: Notion 不可达(weekly-audit 降级本地暂存): {e}", file=sys.stderr)
        # L1 自动 apply(本轮自动,无需 Notion 凭证;写 Evergreen + commit)
        l1 = apply_l1(cfg, vault, git, actor=args.actor,
                      batch_max=cfg.thresholds.get("batch_l1_max", 50))
        # 周报(本地 _Reports 始终写 + Notion 周报队列,失败降级)
        try:
            projects = client.query_projects_activity()
        except (httpx.HTTPError, httpx.RequestError) as e:
            print(f"warn: Projects 活动查询失败,周报用空数据({e})", file=sys.stderr)
            projects = []
        stats = summarize_report(vault, rep, projects)
        publish_report(vault, client, stats)
        print(f"audit done: {len(rep.orphans)} orphans, {len(rep.stale)} stale, "
              f"{len(rep.inbox_pending)} inbox; L1 backfill={l1.backfilled} "
              f"link={l1.linked} tag={l1.tagged}; 周报 {stats.week}")
        return 0

    if args.cmd == "apply-approved":
        if not git.pull():
            print("ABORT: git pull failed", file=sys.stderr)
            return 2
        try:
            res = apply_approved(cfg, vault, client, git, actor=args.actor)
        except (httpx.HTTPError, httpx.RequestError) as e:
            print("=" * 60, file=sys.stderr)
            print("Notion 不可达,无法轮询 approved 提案。", file=sys.stderr)
            print(f"原因:{e}", file=sys.stderr)
            print("修复 endpoint 后重跑即可。apply-approved 是幂等的:已应用的不会重复。", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            return 4
        print(f"applied {len(res.applied)}, blocked {len(res.blocked)}")
        return 0

    if args.cmd == "review-orphans":
        # 只读审计孤岛 + 生成补链提案入 Notion。不写 Evergreen(只产 L2 link 提案)。
        rep = audit(vault, orphan_age_days=cfg.thresholds["orphan_age_days"])
        try:
            emit_proposals(vault, client, rep, actor=args.actor)
        except (httpx.HTTPError, httpx.RequestError) as e:
            print(f"warn: Notion 不可达(review-orphans 降级本地暂存): {e}",
                  file=sys.stderr)
        for o in rep.orphans:
            print(f"  orphan: {o}")
        print(f"{len(rep.orphans)} orphans reviewed,补链提案已入 Notion(若可达)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
