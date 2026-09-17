"""CLI commands for the garden plugin — wires ``hermes garden <subcommand>``.

mirrors google_meet/cli.py 的 argparse 模式:
  setup_fn(subparser)  注册子命令树
  handler_fn(args)     执行(转调 tools handler)
"""
from __future__ import annotations
import argparse
import shlex
from typing import Any, List

from . import tools


_VERBS = ("init", "weekly-audit", "apply-approved", "triage-inbox",
          "review-orphans", "capture")


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes garden`` argparse tree."""
    subs = subs = subparser.add_subparsers(dest="garden_command")

    init_p = subs.add_parser("init", help="首次引导知识花园(vault + Notion 库)")
    init_p.add_argument("--vault", default=".", help="vault 根目录")
    init_p.add_argument("--api-base", default=None, help="Notion REST API base(默认官方)")
    init_p.add_argument("--token-env", default=None, help="读 token 的环境变量名(默认 NOTION_TOKEN)")
    init_p.add_argument("--parent-page", required=False, help="Notion 父页面 URL 或 page id")
    init_p.add_argument("--auth-done", action="store_true", help="已完成 Notion 授权配置")
    init_p.add_argument("--oauth-done", action="store_true",
                        help="已废弃,--auth-done 的别名")

    for verb in ("weekly-audit", "apply-approved", "triage-inbox", "review-orphans"):
        p = subs.add_parser(verb, help=f"garden {verb}")
        p.add_argument("--vault", default=None, help="vault 根目录")
        p.add_argument("--config", default=None, help="gardener.config.yaml 路径")
        if verb == "apply-approved":
            p.add_argument("--actor", default=None,
                           choices=("manual_session", "scheduled_run"),
                           help="操作主体(定时用 scheduled_run)")

    # capture 有专属参数(--text 必填)
    cap_p = subs.add_parser("capture", help="随手记 → 路由 Raw 或 Notion Task")
    cap_p.add_argument("--vault", default=None, help="vault 根目录")
    cap_p.add_argument("--config", default=None, help="gardener.config.yaml 路径(可选)")
    cap_p.add_argument("--text", required=True, help="随手记文本")
    cap_p.add_argument("--source", default=None, help="来源(manual/web/...)")
    cap_p.add_argument("--ttl", type=int, default=None, help="有效期(天),过期自动归档")


def garden_command(args: argparse.Namespace) -> str:
    """Dispatch ``hermes garden <verb>`` to the matching tool handler."""
    verb = getattr(args, "garden_command", None)
    if verb is None or verb in (None, "help"):
        return ("用法: hermes garden "
                "<init|weekly-audit|apply-approved|triage-inbox|review-orphans|capture> [...]")
    if verb not in _VERBS:
        return f"未知子命令 '{verb}'。可用: {', '.join(_VERBS)}"

    tool_args: dict[str, Any] = {}
    if getattr(args, "vault", None):
        tool_args["vault"] = args.vault
    if getattr(args, "config", None):
        tool_args["config"] = args.config
    if getattr(args, "actor", None):
        tool_args["actor"] = args.actor
    if getattr(args, "api_base", None):
        tool_args["api_base"] = args.api_base
    if getattr(args, "token_env", None):
        tool_args["token_env"] = args.token_env
    if getattr(args, "parent_page", None):
        tool_args["parent_page"] = args.parent_page
    if getattr(args, "auth_done", False) or getattr(args, "oauth_done", False):
        tool_args["auth_done"] = True
    if getattr(args, "text", None):
        tool_args["text"] = args.text
    if getattr(args, "source", None):
        tool_args["source"] = args.source
    if getattr(args, "ttl", None):
        tool_args["ttl"] = args.ttl

    handler = tools.HANDLERS[verb]
    return handler(tool_args)
