import json
from pathlib import Path
from garden_gardener.init_orchestrator import (
    InitState, run_init, NEEDS_OAUTH, COMPLETED
)
from garden_gardener.notion import NotionClient


def _ok_send(calls):
    def fake_send(method, path, json=None):
        calls.append((method, path, json))
        if path == "/users/me":
            return {"object": "bot"}
        if path == "/databases":
            title = json["title"][0]["text"]["content"]
            return {"id": f"db-{title}"}
        return {}
    return fake_send


def test_init_completes_all_steps_when_auth_done(tmp_path: Path):
    vault = tmp_path / "Garden"
    config_path = vault / "_Config" / "gardener.config.yaml"
    checkpoint = vault / ".garden-init.json"
    calls = []
    client = NotionClient(send=_ok_send(calls))

    # oauth_already_done=True 模拟用户已完成 token 配置 + 页面分享
    result = run_init(
        vault_root=vault, config_path=config_path, checkpoint=checkpoint,
        client=client, parent_page_id="root",
        oauth_already_done=True,
    )
    assert result == COMPLETED
    # vault 骨架建好
    assert (vault / "Concepts" / ".gitkeep").exists()
    # config 写了 database id(5 个库全部回填)+ api_base/token_env
    cfg_text = config_path.read_text(encoding="utf-8")
    assert "db-Projects" in cfg_text
    assert "db-待审核提案" in cfg_text
    assert "db-Tasks" in cfg_text
    assert "db-Habits" in cfg_text
    assert "db-周报" in cfg_text
    assert "tasks_database_id" in cfg_text
    assert "habits_database_id" in cfg_text
    assert "weekly_database_id" in cfg_text
    assert 'api_base: "https://api.notion.com/v1"' in cfg_text
    assert 'token_env: "NOTION_TOKEN"' in cfg_text
    # 插件清单
    assert (vault / ".obsidian" / "community-plugins.json").exists()
    # checkpoint 标记完成
    assert json.loads(checkpoint.read_text())["done"] is True


def test_init_pauses_at_oauth_when_not_done(tmp_path: Path):
    vault = tmp_path / "Garden"
    checkpoint = vault / ".garden-init.json"
    client = NotionClient(send=_ok_send([]))

    result = run_init(
        vault_root=vault, config_path=vault / "_Config" / "gardener.config.yaml",
        checkpoint=checkpoint, client=client, parent_page_id="root",
        oauth_already_done=False,
    )
    assert result == NEEDS_OAUTH
    # vault 骨架应已建好(授权之前能做的都做了)
    assert (vault / "Concepts").exists()
    # 但 Notion 库还没建(checkpoint 记录待授权)
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert state["steps"]["vault_skeleton"] is True
    assert state["steps"]["notion_databases"] is False


def test_init_resumes_from_checkpoint(tmp_path: Path):
    vault = tmp_path / "Garden"
    checkpoint = vault / ".garden-init.json"
    config_path = vault / "_Config" / "gardener.config.yaml"

    # 第一次:授权未完成,停在 NEEDS_OAUTH
    client = NotionClient(send=_ok_send([]))
    run_init(vault_root=vault, config_path=config_path, checkpoint=checkpoint,
             client=client, parent_page_id="root", oauth_already_done=False)

    # 第二次:授权完成 → 续跑,完成 Notion 库 + config + 插件
    result = run_init(vault_root=vault, config_path=config_path, checkpoint=checkpoint,
                      client=client, parent_page_id="root", oauth_already_done=True)
    assert result == COMPLETED
    cfg_text = config_path.read_text(encoding="utf-8")
    assert "db-Projects" in cfg_text


def test_init_completed_state_short_circuits(tmp_path: Path):
    # 已完成的 init 重跑直接返回 COMPLETED,不重复建库
    vault = tmp_path / "Garden"
    vault.mkdir(parents=True)
    checkpoint = vault / ".garden-init.json"
    checkpoint.write_text(json.dumps({"done": True, "steps": {}}))
    calls = []
    client = NotionClient(send=_ok_send(calls))
    result = run_init(vault_root=vault, config_path=vault / "c.yaml",
                      checkpoint=checkpoint, client=client,
                      parent_page_id="root", oauth_already_done=True)
    assert result == COMPLETED
    assert calls == []  # 没重复调 REST
