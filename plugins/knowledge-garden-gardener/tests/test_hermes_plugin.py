"""Hermes plugin 薄包装的测试。

不依赖 Hermes runtime(用 mock ctx),不依赖真实 garden CLI(测 build_command 拼装,
handler 的 _run 只在集成时才真调)。覆盖:
- build_command 参数拼装正确
- register(ctx) 注册了 4 tool + 1 command
- slash command handler 路由 + flag 解析
- plugin.yaml 存在且字段齐全
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# hermes-plugin/garden 不在默认 sys.path,手动加入
HERMES_PKG = Path(__file__).resolve().parents[1] / "hermes-plugin"
sys.path.insert(0, str(HERMES_PKG))

import garden  # noqa: E402
from garden import tools, schemas  # noqa: E402


# ---- build_command 参数拼装 ----

def test_build_command_init():
    cmd = tools.build_command("init", {
        "vault": "./Garden", "mcp_endpoint": "http://x", "parent_page": "pp",
    })
    assert cmd[0] == "garden"
    assert "init" in cmd
    assert "--mcp-endpoint" in cmd and "http://x" in cmd
    assert "--parent-page" in cmd and "pp" in cmd
    assert "--oauth-done" not in cmd  # 默认不带

def test_build_command_init_with_oauth():
    cmd = tools.build_command("init", {
        "vault": "./G", "mcp_endpoint": "http://x", "parent_page": "pp",
        "oauth_done": True,
    })
    assert "--oauth-done" in cmd

def test_build_command_weekly_audit():
    cmd = tools.build_command("weekly-audit", {"vault": "./G", "config": "c.yaml"})
    # 非 init:全局参数在 verb 前
    assert cmd == ["garden", "--vault", "./G", "--config", "c.yaml", "weekly-audit"]

def test_build_command_apply_approved_with_actor():
    cmd = tools.build_command("apply-approved", {"actor": "scheduled_run"})
    assert "--actor" in cmd and "scheduled_run" in cmd
    assert cmd[-1] == "apply-approved"

def test_build_command_minimal():
    # 无参数:只返回 garden + verb
    cmd = tools.build_command("triage-inbox", {})
    assert cmd == ["garden", "triage-inbox"]


# ---- register(ctx) 注册 ----

def test_register_registers_4_tools_and_1_command():
    ctx = MagicMock()
    garden.register(ctx)
    # 4 个 tool
    assert ctx.register_tool.call_count == 4
    tool_names = {c.kwargs["name"] for c in ctx.register_tool.call_args_list}
    assert tool_names == {"garden_init", "garden_weekly_audit",
                          "garden_apply_approved", "garden_triage_inbox"}
    # 所有 tool 都在 garden toolset
    for c in ctx.register_tool.call_args_list:
        assert c.kwargs["toolset"] == "garden"
    # 1 个 slash command
    assert ctx.register_command.call_count == 1
    cmd_call = ctx.register_command.call_args_list[0]
    assert cmd_call.args[0] == "garden"

def test_register_tool_handlers_match_schemas():
    ctx = MagicMock()
    garden.register(ctx)
    for c in ctx.register_tool.call_args_list:
        schema = c.kwargs["schema"]
        handler = c.kwargs["handler"]
        verb = schema["name"].removeprefix("garden_").replace("_", "-")
        assert handler == tools.HANDLERS[verb]  # handler 对得上


# ---- slash command handler ----

def test_slash_help():
    assert "用法" in garden._handle_slash("")

def test_slash_unknown_verb():
    assert "未知子命令" in garden._handle_slash("foobar")

def test_slash_parse_flags():
    args = garden._parse_flags(["--vault", "./G", "--actor", "scheduled_run"])
    assert args == {"vault": "./G", "actor": "scheduled_run"}

def test_slash_parse_boolean_flag():
    args = garden._parse_flags(["--oauth-done"])
    assert args == {"oauth_done": True}


# ---- handler 不 raise(garden 不存在时返回 error JSON,不抛) ----

def test_handler_returns_error_json_when_garden_missing(monkeypatch):
    # 模拟 garden 命令不存在
    import subprocess
    def fake_run(*a, **k):
        raise FileNotFoundError("garden not found")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = tools.garden_weekly_audit({"vault": "./G"})
    data = json.loads(result)
    assert data["ok"] is False
    assert "未找到" in data["error"] or "not found" in data["error"]


# ---- plugin.yaml 存在且字段齐全 ----

def test_plugin_yaml_exists_and_valid():
    import yaml
    p = HERMES_PKG / "garden" / "plugin.yaml"
    assert p.exists()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["name"] == "garden"
    assert data["version"]
    assert "description" in data
    assert "garden_init" in data["provides_tools"]
    assert len(data["provides_tools"]) == 4


# ---- schemas 参数对齐真实 CLI(无虚构 --path) ----

def test_schemas_use_real_cli_params():
    # 确保没有虚构的 --path,用的是 --vault/--config/--actor
    for s in schemas.ALL:
        props = s["parameters"]["properties"]
        assert "path" not in props, f"{s['name']} 不应用虚构的 path"
    assert "vault" in schemas.WEEKLY_AUDIT["parameters"]["properties"]
    assert "actor" in schemas.APPLY_APPROVED["parameters"]["properties"]
    assert "mcp_endpoint" in schemas.INIT["parameters"]["properties"]
