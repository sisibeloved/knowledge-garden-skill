"""验证 garden init 的错误处理:Notion 不可达时优雅退出而非抛栈。"""
import json
from pathlib import Path
from garden_gardener.cli_entry import main, parse_page_ref, _init_config_path

# invalid-no-protocol 触发 httpx.UnsupportedProtocol(不发请求,测降级)
_BAD_API_BASE = "invalid-no-protocol"


def test_init_returns_4_when_notion_unreachable(tmp_path: Path, capsys):
    vault = tmp_path / "Garden"
    # 第一次:停在授权断点,建好骨架
    rc1 = main(["init", "--vault", str(vault),
                "--api-base", _BAD_API_BASE,
                "--parent-page", "1" * 32])
    assert rc1 == 3
    assert (vault / "Concepts").exists()

    # 第二次:带 --auth-done,但 API base 不可达 → 应 exit 4,不抛异常
    rc2 = main(["init", "--vault", str(vault),
                "--api-base", _BAD_API_BASE,
                "--parent-page", "1" * 32, "--auth-done"])
    assert rc2 == 4
    captured = capsys.readouterr()
    # 友好消息(非 Python 栈)
    assert "Notion 连接失败" in captured.err or "失败" in captured.err
    assert "Traceback" not in captured.err
    # checkpoint 保留,vault_skeleton 仍 true(可续跑)
    state = json.loads((vault / ".garden-init.json").read_text(encoding="utf-8"))
    assert state["steps"]["vault_skeleton"] is True
    assert state["done"] is False


def test_init_short_circuits_when_already_done(tmp_path: Path, capsys):
    vault = tmp_path / "Garden"
    vault.mkdir(parents=True)
    # 预置一个已完成的 checkpoint
    (vault / ".garden-init.json").write_text(json.dumps({"done": True, "steps": {}}))
    rc = main(["init", "--vault", str(vault),
               "--api-base", _BAD_API_BASE,
               "--parent-page", "1" * 32, "--auth-done"])
    assert rc == 0  # 直接 COMPLETED,不重跑


def test_init_oauth_done_alias_still_accepted(tmp_path: Path):
    """--oauth-done 是 --auth-done 的废弃别名,旧脚本不破坏。"""
    vault = tmp_path / "Garden"
    rc = main(["init", "--vault", str(vault),
               "--api-base", _BAD_API_BASE,
               "--parent-page", "1" * 32, "--oauth-done"])
    assert rc == 4  # 走到了建库分支(别名生效),因不可达而 exit 4


def test_init_rejects_bad_parent_page(tmp_path: Path, capsys):
    vault = tmp_path / "Garden"
    rc = main(["init", "--vault", str(vault), "--parent-page", "not-a-page"])
    assert rc == 1
    assert "--parent-page" in capsys.readouterr().err


# ---------- parse_page_ref:URL / id 解析 ----------

def test_parse_page_ref_from_url_with_view_param():
    # 尾段是 32 hex 的 page id;?v= 是 view id,必须丢弃
    url = ("https://www.notion.so/knowledge-garden-"
           "0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d?v=ffff")
    assert parse_page_ref(url) == "0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d"


def test_parse_page_ref_from_dashed_uuid():
    assert parse_page_ref("0A1B2C3D-4E5F-6A7B-8C9D-0E1F2A3B4C5D") == \
        "0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d"


def test_parse_page_ref_from_bare_id():
    assert parse_page_ref("0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d") == \
        "0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d"


def test_parse_page_ref_rejects_garbage():
    for bad in ("", "not-a-page", "https://www.notion.so/"):
        try:
            parse_page_ref(bad)
            assert False, f"should reject {bad!r}"
        except ValueError:
            pass


# ---------- init config 输出路径(回归:曾相对 CWD 解析写错位置) ----------

class _NS:
    """最小 args 替身。"""
    def __init__(self, config, vault):
        self.config = config
        self.vault = vault


def test_init_config_path_defaults_to_vault_not_cwd():
    p = _init_config_path(_NS(config=None, vault="D:/Garden"))
    assert p == Path("D:/Garden") / "_Config" / "gardener.config.yaml"


def test_init_config_path_explicit_wins():
    p = _init_config_path(_NS(config="custom/dir/c.yaml", vault="D:/Garden"))
    assert p == Path("custom/dir/c.yaml")
