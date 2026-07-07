"""garden Hermes plugin — 把 garden CLI 注册为 Hermes tool + hermes garden 子命令。

入口:register(ctx)。Hermes 启动时(插件 enable 后)import 本包并调用一次。
API 对齐本机 Hermes v0.18.0 真实 plugin(参考 bundled 的 google_meet):
  - ctx.register_tool(name=, toolset=, schema=, handler=, emoji=, check_fn=)
  - ctx.register_cli_command(name=, help=, setup_fn=, handler_fn=, description=)
不依赖 garden CLI 在 import 时可用(运行时 handler 才 subprocess 调)。
"""
from __future__ import annotations

from . import schemas, tools
from .cli import register_cli as _register_garden_cli, garden_command as _garden_command

__all__ = ["register"]

# (tool name, schema, handler, emoji)
_TOOLS = (
    ("garden_init",          schemas.INIT,          tools.garden_init,          "🌱"),
    ("garden_weekly_audit",  schemas.WEEKLY_AUDIT,  tools.garden_weekly_audit,  "🔍"),
    ("garden_apply_approved", schemas.APPLY_APPROVED, tools.garden_apply_approved, "✅"),
    ("garden_triage_inbox",  schemas.TRIAGE_INBOX,  tools.garden_triage_inbox,  "📥"),
)


def register(ctx) -> None:
    """注册 4 个 tool + hermes garden 子命令。"""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="garden",
            schema=schema,
            handler=handler,
            emoji=emoji,
        )

    ctx.register_cli_command(
        name="garden",
        help="知识花园园丁 (init / weekly-audit / apply-approved / triage-inbox)",
        setup_fn=_register_garden_cli,
        handler_fn=_garden_command,
        description=(
            "运行 garden CLI:初始化知识花园、跑巡园审计、应用已批准提案、整理 Inbox。"
        ),
    )
