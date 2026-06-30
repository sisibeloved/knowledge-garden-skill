from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .config import load_config
from .vault import Vault
from .notion import NotionClient
from .gitutil import Git
from .audit import audit
from .proposal import emit_proposals
from .apply import apply_approved
from .init_orchestrator import run_init, COMPLETED, NEEDS_OAUTH
from .init_notion import NotionBootstrapError
from .init_plugins import install_instructions


def _cmd_init(args) -> int:
    """garden init: 引导整个知识花园(vault + Notion + 插件清单)。

    OAuth 是唯一人工断点:首次跑返回 NEEDS_OAUTH(exit 3),打印指引;
    用户完成 Notion OAuth 授权后,带 --oauth-done 重跑即可续。
    Notion 不可达时返回 exit 4 + 友好消息(不抛栈),checkpoint 保留可续跑。
    """
    client = NotionClient(args.mcp_endpoint, "pending", "pending")
    try:
        result = run_init(
            vault_root=Path(args.vault),
            config_path=Path(args.config),
            checkpoint=Path(args.vault) / ".garden-init.json",
            client=client,
            parent_page_id=args.parent_page,
            oauth_already_done=args.oauth_done,
        )
    except NotionBootstrapError as e:
        print("=" * 60, file=sys.stderr)
        print("Notion 连接失败,无法建库。", file=sys.stderr)
        print(f"原因:{e}", file=sys.stderr)
        print("已完成的步骤已保存,修复后重新运行同样的命令即可续跑(不会重头)。", file=sys.stderr)
        print("常见原因:endpoint 错误、OAuth 未真正完成、网络不通。", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return 4
    if result == NEEDS_OAUTH:
        print("=" * 60)
        print("需要完成 Notion OAuth 授权(唯一人工步骤):")
        print("  1. 打开 Notion → Settings → My connections / 开发者设置")
        print("  2. 按 Notion MCP 官方文档完成 OAuth(scope 最小化,")
        print("     只授权 garden init 要建的库所在的 page)")
        print("  3. 确认 MCP endpoint 可达后,重新运行:")
        print(f"       garden init --vault {args.vault} \\")
        print(f"         --mcp-endpoint {args.mcp_endpoint} \\")
        print(f"         --parent-page {args.parent_page} --oauth-done")
        print("=" * 60)
        return 3
    print("init 完成。", install_instructions(Path(args.vault)))
    print("\n下一步:在 Obsidian 内打开此 vault,装好插件后即可运行 weekly-audit。")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="garden")
    p.add_argument("--config", default="_Config/gardener.config.yaml")
    p.add_argument("--vault", default=".")
    p.add_argument("--actor", default="manual_session",
                   choices=["manual_session", "scheduled_run"])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("weekly-audit")
    sub.add_parser("apply-approved")
    sub.add_parser("triage-inbox")

    init_p = sub.add_parser("init", help="引导知识花园(vault+Notion+插件清单)")
    # init 有独立的 --vault/--config(init 是创建 config,不读取),故在此子命令重新声明
    init_p.add_argument("--vault", default=".",
                        help="vault 根目录(init 会在此建骨架+config)")
    init_p.add_argument("--config", default="_Config/gardener.config.yaml",
                        help="config 输出路径")
    init_p.add_argument("--mcp-endpoint", required=True,
                        help="Notion MCP endpoint")
    init_p.add_argument("--parent-page", required=True,
                        help="Notion 父页面 id,4 个库建在其下")
    init_p.add_argument("--oauth-done", action="store_true",
                        help="已完成 Notion OAuth(首次跑不要带,断点后带上续跑)")

    args = p.parse_args(argv)

    if args.cmd == "init":
        return _cmd_init(args)

    cfg = load_config(Path(args.config))
    vault = Vault(Path(args.vault))
    git = Git(Path(args.vault))
    client = NotionClient(
        cfg.notion["mcp_endpoint"],
        cfg.notion["proposal_database_id"],
        cfg.notion["projects_database_id"],
    )

    if args.cmd == "weekly-audit":
        if not git.pull():
            print("ABORT: git pull failed; 不基于脏数据跑", file=sys.stderr)
            return 2
        rep = audit(
            vault,
            orphan_age_days=cfg.thresholds["orphan_age_days"],
            stale_days=cfg.thresholds.get("stale_review_days", 90),
        )
        emit_proposals(vault, client, rep, actor=args.actor)
        print(f"audit done: {len(rep.orphans)} orphans, {len(rep.stale)} stale, "
              f"{len(rep.inbox_pending)} inbox")
        return 0

    if args.cmd == "apply-approved":
        if not git.pull():
            print("ABORT: git pull failed", file=sys.stderr)
            return 2
        res = apply_approved(cfg, vault, client, git, actor=args.actor)
        print(f"applied {len(res.applied)}, blocked {len(res.blocked)}")
        return 0

    if args.cmd == "triage-inbox":
        rep = audit(vault)
        print(f"{len(rep.inbox_pending)} inbox items pending triage")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
