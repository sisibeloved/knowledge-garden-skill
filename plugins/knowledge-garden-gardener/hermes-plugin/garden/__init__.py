"""garden Hermes plugin —— 把 garden CLI 注册为 Hermes tool + slash command。

入口:register(ctx)。Hermes 启动时 import 本包并调用一次。
不依赖 garden CLI 在 import 时可用(运行时 handler 才 subprocess 调)。
"""
from __future__ import annotations
import shlex
from . import schemas, tools

__all__ = ["register"]

_VERBS = ["init", "weekly-audit", "apply-approved", "triage-inbox"]


def _handle_slash(raw_args: str) -> str:
    """/garden <verb> [--vault X] ... 的 slash command handler。

    复用 tool handler,保证 slash command 和 tool 行为一致。
    raw_args: /garden 之后的原始字符串(如 'weekly-audit --vault ./Garden')。
    """
    parts = shlex.split(raw_args) if raw_args.strip() else []
    if not parts or parts[0] in ("help", "-h", "--help"):
        return "用法: /garden <init|weekly-audit|apply-approved|triage-inbox> [--vault X] ..."
    verb = parts[0]
    if verb not in _VERBS:
        return f"未知子命令 '{verb}'。可用: {', '.join(_VERBS)}"
    # 把 --key value 对解析回 dict,交给 tool handler
    args = _parse_flags(parts[1:])
    handler = tools.HANDLERS[verb]
    return handler(args)


def _parse_flags(tokens: list[str]) -> dict:
    """把 ['--vault', './G', '--actor', 'scheduled_run'] → {'vault': './G', ...}"""
    out = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--"):
            key = t[2:].replace("-", "_")
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                out[key] = tokens[i + 1]
                i += 2
            else:
                out[key] = True  # 布尔 flag(如 --oauth-done)
                i += 1
        else:
            i += 1
    return out


def register(ctx):
    """Hermes plugin 入口:注册 4 个 tool + 1 个 /garden slash command。"""
    # 4 个 tool(LLM 自动调用)
    for schema in schemas.ALL:
        # tool name 如 garden_weekly_audit → verb weekly-audit → 找 handler
        verb = schema["name"].removeprefix("garden_").replace("_", "-")
        handler = tools.HANDLERS[verb]
        ctx.register_tool(
            name=schema["name"], toolset="garden",
            schema=schema, handler=handler,
        )
    # 1 个 slash command(用户手动 /garden)
    ctx.register_command(
        "garden", handler=_handle_slash,
        description="运行 garden CLI: /garden <init|weekly-audit|apply-approved|triage-inbox>",
    )
