"""验证 garden init 的错误处理:Notion 不可达时优雅退出而非抛栈。"""
import json
from pathlib import Path
from garden_gardener.cli_entry import main


def test_init_returns_4_when_notion_unreachable(tmp_path: Path, capsys):
    vault = tmp_path / "Garden"
    # 第一次:停在 OAuth,建好骨架
    rc1 = main(["init", "--vault", str(vault),
                "--mcp-endpoint", "http://localhost:9/fake",
                "--parent-page", "pp"])
    assert rc1 == 3
    assert (vault / "Concepts").exists()

    # 第二次:带 --oauth-done,但 endpoint 不可达 → 应 exit 4,不抛异常
    rc2 = main(["init", "--vault", str(vault),
                "--mcp-endpoint", "http://localhost:9/fake",
                "--parent-page", "pp", "--oauth-done"])
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
               "--mcp-endpoint", "http://localhost:9/fake",
               "--parent-page", "pp", "--oauth-done"])
    assert rc == 0  # 直接 COMPLETED,不重跑
