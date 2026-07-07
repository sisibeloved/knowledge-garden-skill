"""Hermes plugin 薄包装的测试。

不依赖 Hermes runtime(用 mock ctx),不依赖真实 garden CLI(测 build_command 拼装)。
API 对齐本机 Hermes v0.18.0 真实 plugin(参考 bundled 的 google_meet)。
覆盖:
- build_command 参数拼装正确
- register(ctx) 注册了 4 tool(register_tool)+ 1 cli command(register_cli_command)
- cli.setup_fn / cli.handler_fn 路由 + flag 解析
- handler 不 raise(garden 不存在时返回 error JSON)
- plugin.yaml 存在且字段齐全(kind/platforms/provides_tools)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

# hermes-plugin/garden 不在默认 sys.path,手动加入
HERMES_PKG = Path(__file__).resolve().parents[1] / "hermes-plugin"
sys.path.insert(0, str(HERMES_PKG))

import garden  # noqa: E402
from garden import tools, schemas, cli  # noqa: E402


# ---- build_command 参数拼装 ----

def test_build_command_init():
    cmd = tools.build_command("init", {
        "vault": "./Garden", "mcp_endpoint": "http://x", "parent_page": "pp",
    })
    assert cmd[0] == "garden"
    assert "init" in cmd
    assert "--mcp-endpoint" in cmd and "http://x" in cmd
    assert "--parent-page" in cmd and "pp" in cmd
    assert "--oauth-done" not in cmd

def test_build_command_init_with_oauth():
    cmd = tools.build_command("init", {
        "vault": "./G", "mcp_endpoint": "http://x", "parent_page": "pp",
        "oauth_done": True,
    })
    assert "--oauth-done" in cmd

def test_build_command_weekly_audit():
    cmd = tools.build_command("weekly-audit", {"vault": "./G", "config": "c.yaml"})
    assert cmd == ["garden", "--vault", "./G", "--config", "c.yaml", "weekly-audit"]

def test_build_command_apply_approved_with_actor():
    cmd = tools.build_command("apply-approved", {"actor": "scheduled_run"})
    assert "--actor" in cmd and "scheduled_run" in cmd
    assert cmd[-1] == "apply-approved"

def test_build_command_minimal():
    cmd = tools.build_command("triage-inbox", {})
    assert cmd == ["garden", "triage-inbox"]


# ---- register(ctx) 注册(对齐真实 API) ----

def test_register_registers_4_tools_and_1_cli_command():
    ctx = MagicMock()
    garden.register(ctx)
    # 4 个 tool(register_tool)
    assert ctx.register_tool.call_count == 4
    tool_names = {c.kwargs["name"] for c in ctx.register_tool.call_args_list}
    assert tool_names == {"garden_init", "garden_weekly_audit",
                          "garden_apply_approved", "garden_triage_inbox"}
    # 所有 tool 都在 garden toolset 且带 emoji
    for c in ctx.register_tool.call_args_list:
        assert c.kwargs["toolset"] == "garden"
        assert "emoji" in c.kwargs
    # 1 个 cli 命令(register_cli_command,不是 register_command)
    assert ctx.register_cli_command.call_count == 1
    cmd_call = ctx.register_cli_command.call_args_list[0]
    assert cmd_call.kwargs["name"] == "garden"
    assert callable(cmd_call.kwargs["setup_fn"])
    assert callable(cmd_call.kwargs["handler_fn"])

def test_register_tool_handlers_match_schemas():
    ctx = MagicMock()
    garden.register(ctx)
    for c in ctx.register_tool.call_args_list:
        schema = c.kwargs["schema"]
        handler = c.kwargs["handler"]
        verb = schema["name"].removeprefix("garden_").replace("_", "-")
        assert handler == tools.HANDLERS[verb]


# ---- cli setup_fn / handler_fn(argparse 模式) ----

def test_cli_setup_fn_builds_subcommands():
    parser = argparse.ArgumentParser(prog="hermes garden")
    cli.register_cli(parser)
    # init 子命令必须存在
    ns = parser.parse_args(["init", "--mcp-endpoint", "http://x", "--parent-page", "pp"])
    assert ns.garden_command == "init"
    assert ns.mcp_endpoint == "http://x"

def test_cli_handler_routes_init():
    ns = argparse.Namespace(garden_command="init", vault=".", mcp_endpoint="http://x",
                            parent_page="pp", oauth_done=False)
    # garden_command handler 把 namespace 转 dict 调 tool handler
    result = cli.garden_command(ns)
    data = json.loads(result)
    # garden 命令不存在 → error JSON(不 raise)
    assert data["ok"] is False

def test_cli_handler_unknown_verb():
    ns = argparse.Namespace(garden_command="bogus")
    assert "未知子命令" in cli.garden_command(ns)


# ---- handler 不 raise(garden 不存在时返回 error JSON) ----

def test_handler_returns_error_json_when_garden_missing(monkeypatch):
    def fake_run(*a, **k):
        raise FileNotFoundError("garden not found")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = tools.garden_weekly_audit({"vault": "./G"})
    data = json.loads(result)
    assert data["ok"] is False
    assert "未找到" in data["error"] or "not found" in data["error"]


# ---- plugin.yaml 存在且字段齐全 ----

def test_plugin_yaml_exists_and_valid():
    p = HERMES_PKG / "garden" / "plugin.yaml"
    assert p.exists()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["name"] == "garden"
    assert data["version"] == "0.3.0"
    assert data["kind"] == "standalone"
    assert "windows" in data["platforms"]  # 本机是 Windows,必须支持
    assert "garden_init" in data["provides_tools"]
    assert len(data["provides_tools"]) == 4


# ---- schemas 参数对齐真实 CLI(无虚构 --path) ----

def test_schemas_use_real_cli_params():
    for s in schemas.ALL:
        props = s["parameters"]["properties"]
        assert "path" not in props, f"{s['name']} 不应用虚构的 path"
    assert "vault" in schemas.WEEKLY_AUDIT["parameters"]["properties"]
    assert "actor" in schemas.APPLY_APPROVED["parameters"]["properties"]
    assert "mcp_endpoint" in schemas.INIT["parameters"]["properties"]
