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
        "首次引导知识花园:自动建 vault 骨架 + Notion 5 库 + 插件清单。"
        "包装 `garden init`。用户首次搭建时用。"
        "Notion 授权是唯一人工断点:首次跑返回 exit 3,完成 integration token"
        "配置 + 父页面分享后带 auth_done=true 重跑。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "vault": _VAULT,
            "parent_page": {
                "type": "string",
                "description": "Notion 父页面 URL 或 page id,5 个库建在其下(必填)",
            },
            "api_base": {
                "type": "string",
                "description": "Notion REST API base(默认官方 https://api.notion.com/v1)",
            },
            "token_env": {
                "type": "string",
                "description": "读 Notion token 的环境变量名(默认 NOTION_TOKEN)",
            },
            "auth_done": {
                "type": "boolean",
                "description": "已完成 integration token 配置 + 父页面分享(断点后续跑 true)",
            },
        },
        "required": ["parent_page"],
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
        "整理 Inbox:列出 _System/_Inbox/ 待处理 Raw + 每条归类建议。只读,安全。"
        "包装 `garden triage-inbox`。"
    ),
    "parameters": {
        "type": "object",
        "properties": {"vault": _VAULT, "config": _CONFIG},
        "required": [],
    },
}

REVIEW_ORPHANS = {
    "name": "garden_review_orphans",
    "description": (
        "找孤岛笔记(无 links/无反向链接/较老)+ 生成补链提案入 Notion。"
        "包装 `garden review-orphans`。只读审计 + 产 L2 link 提案,不写 Evergreen。"
    ),
    "parameters": {
        "type": "object",
        "properties": {"vault": _VAULT, "config": _CONFIG},
        "required": [],
    },
}

CAPTURE = {
    "name": "garden_capture",
    "description": (
        "手机/手动随手记:接收一段文本,路由到 Obsidian Raw Inbox 或 Notion Task。"
        "包装 `garden capture --text ...`。任务类语义(计划/待办/截止)→ Task,"
        "其余 → Raw。Task 不可达时降级落 Inbox(type=task_candidate)待下轮提升。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "vault": _VAULT,
            "text": {
                "type": "string",
                "description": "随手记文本(必填)",
            },
            "source": {
                "type": "string",
                "description": "来源(manual/web/...),默认 manual",
            },
            "config": _CONFIG,
        },
        "required": ["text"],
    },
}

ALL = [INIT, WEEKLY_AUDIT, APPLY_APPROVED, TRIAGE_INBOX, REVIEW_ORPHANS, CAPTURE]
