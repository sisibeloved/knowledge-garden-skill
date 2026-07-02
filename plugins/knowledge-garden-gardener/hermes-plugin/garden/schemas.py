"""garden tool 的 JSON Schema —— LLM 读这些 决定何时调用哪个 tool。

参数对齐 garden CLI 真实参数(--vault/--config/--actor 等),不是虚构的 --path。
"""

# 公共参数说明
_VAULT = {
    "type": "string",
    "description": "Obsidian vault 根目录路径(默认当前目录)",
}
_CONFIG = {
    "type": "string",
    "description": "gardener.config.yaml 路径(默认 <vault>/_Config/gardener.config.yaml)",
}

INIT = {
    "name": "garden_init",
    "description": (
        "首次引导知识花园:自动建 vault 骨架 + Notion 4 库 + 插件清单。"
        "包装 `garden init`。用户首次搭建时用。"
        "OAuth 是唯一人工断点:首次跑返回 exit 3,完成 Notion OAuth 后带 oauth_done=true 重跑。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "vault": _VAULT,
            "mcp_endpoint": {
                "type": "string",
                "description": "Notion MCP endpoint(必填)",
            },
            "parent_page": {
                "type": "string",
                "description": "Notion 父页面 id,4 个库建在其下(必填)",
            },
            "oauth_done": {
                "type": "boolean",
                "description": "已完成 Notion OAuth(首次跑 false,断点后续跑 true)",
            },
        },
        "required": ["mcp_endpoint", "parent_page"],
    },
}

WEEKLY_AUDIT = {
    "name": "garden_weekly_audit",
    "description": (
        "每周巡园:只读审计 vault(孤岛/过时/Inbox),生成提案入 Notion。"
        "包装 `garden weekly-audit`。不写 Evergreen,安全。"
    ),
    "parameters": {
        "type": "object",
        "properties": {"vault": _VAULT, "config": _CONFIG},
        "required": [],
    },
}

APPLY_APPROVED = {
    "name": "garden_apply_approved",
    "description": (
        "应用 Notion 已批准的提案到 Evergreen + git commit。"
        "包装 `garden apply-approved`。这会写文件(变更 Evergreen),"
        "只在用户确认后运行。定时/无人值守用 actor='scheduled_run'。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "vault": _VAULT,
            "config": _CONFIG,
            "actor": {
                "type": "string",
                "enum": ["manual_session", "scheduled_run"],
                "description": "操作主体。定时/无人值守必须用 scheduled_run(能力受限)",
            },
        },
        "required": [],
    },
}

TRIAGE_INBOX = {
    "name": "garden_triage_inbox",
    "description": (
        "整理 Inbox:列出 _System/_Inbox/ 待处理 Raw。只读,安全。"
        "包装 `garden triage-inbox`。"
    ),
    "parameters": {
        "type": "object",
        "properties": {"vault": _VAULT, "config": _CONFIG},
        "required": [],
    },
}

ALL = [INIT, WEEKLY_AUDIT, APPLY_APPROVED, TRIAGE_INBOX]
