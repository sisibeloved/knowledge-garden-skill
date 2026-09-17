"""garden tool handlers —— 把 schema 参数转成 garden CLI 命令并 subprocess 调用。

设计:纯函数 build_command + 一个 _run 复用。不依赖 Hermes runtime,
可在无 Hermes 环境下单测(只测 build_command 和 _run 的参数拼装)。
handler 永不 raise,所有异常捕获后返回 error JSON(符合 Hermes tool 契约)。
"""
from __future__ import annotations
import json
import subprocess


def build_command(verb: str, args: dict) -> list[str]:
    """把 schema 参数(dict)转成 garden CLI 参数列表。

    verb: init | weekly-audit | apply-approved | triage-inbox | review-orphans | capture
    args: schema 里定义的 properties dict
    """
    cmd = ["garden"]
    # 全局参数(所有 verb 共用)
    if verb == "init":
        cmd.append("init")
        cmd += ["--vault", args.get("vault", ".")]
        if args.get("api_base"):
            cmd += ["--api-base", args["api_base"]]
        if args.get("token_env"):
            cmd += ["--token-env", args["token_env"]]
        cmd += ["--parent-page", args["parent_page"]]
        if args.get("auth_done") or args.get("oauth_done"):
            cmd.append("--auth-done")
        return cmd

    # 其它 verb:全局参数在子命令前
    config = args.get("config")
    vault = args.get("vault")
    actor = args.get("actor")
    if vault:
        cmd += ["--vault", vault]
    if config:
        cmd += ["--config", config]
    if actor:
        cmd += ["--actor", actor]
    cmd.append(verb)
    # capture 的子命令参数(--text/--source)在 verb 之后
    if verb == "capture":
        cmd += ["--text", args["text"]]
        if args.get("source"):
            cmd += ["--source", args["source"]]
    return cmd


def _run(cmd: list[str]) -> str:
    """执行命令,返回 JSON 字符串结果。永不 raise。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, check=False,
        )
        return json.dumps({
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": " ".join(cmd),
        }, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({
            "ok": False,
            "error": "`garden` 命令未找到。请先 pip install knowledge-garden-gardener。",
            "command": " ".join(cmd),
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "ok": False,
            "error": f"命令超时(300s): {' '.join(cmd)}",
            "command": " ".join(cmd),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False, "error": str(e), "command": " ".join(cmd),
        }, ensure_ascii=False)


def garden_init(args, **kwargs):
    return _run(build_command("init", args))

def garden_weekly_audit(args, **kwargs):
    return _run(build_command("weekly-audit", args))

def garden_apply_approved(args, **kwargs):
    return _run(build_command("apply-approved", args))

def garden_triage_inbox(args, **kwargs):
    return _run(build_command("triage-inbox", args))

def garden_review_orphans(args, **kwargs):
    return _run(build_command("review-orphans", args))

def garden_capture(args, **kwargs):
    return _run(build_command("capture", args))


# verb → handler 映射(slash command 复用)
HANDLERS = {
    "init": garden_init,
    "weekly-audit": garden_weekly_audit,
    "apply-approved": garden_apply_approved,
    "triage-inbox": garden_triage_inbox,
    "review-orphans": garden_review_orphans,
    "capture": garden_capture,
}
