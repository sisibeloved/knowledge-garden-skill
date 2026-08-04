"""验证非 init 子命令的错误处理和配置回退。

覆盖三个关键修复:
1. triage-inbox 不依赖 config 即可运行(不抛 FileNotFoundError)
2. apply-approved Notion 不可达时优雅 exit 4,无 traceback
3. weekly-audit / apply-approved 在缺 config 时给出 exit 5 + 友好引导
"""
from pathlib import Path
from garden_gardener.cli_entry import main


def _init_git_repo(p: Path) -> None:
    """给 tmp_path 里的 vault 一个最简单的 git 工作状态(git pull 需要 upstream)。

    shell 调用 git init / commit / remote add / pull —— windows 上 git 在 PATH。
    """
    import subprocess
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=p, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
         "--allow-empty", "-m", "init"],
        cwd=p, check=True,
    )
    # 用一个 bare 兄弟目录做 remote,这样 pull 能成功 (already up to date)
    bare = p.parent / f"{p.name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=p, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=p, check=True)


def test_triage_inbox_runs_without_config(tmp_path: Path, capsys):
    """修复:triage-inbox 不应该要求 _Config/gardener.config.yaml 存在。

    原行为:argparse 默认 config="_Config/gardener.config.yaml" 相对 CWD 解析,
    任何不显式传 --config 的调用都 FileNotFoundError(裸 traceback)。
    新行为:fallback 到 <vault>/_Config/gardener.config.yaml,且 triage-inbox 不依赖 config,
    所以即使没 _Config/ 也能跑通。
    """
    vault = tmp_path / "Garden"
    vault.mkdir()
    (vault / "_System" / "_Inbox").mkdir(parents=True)
    (vault / "_System" / "_Inbox" / "raw-001.md").write_text(
        "---\nstatus: inbox\ntype: raw\n---\n", encoding="utf-8"
    )
    # cli_entry.py 的 argparse 设计:--vault / --config 是主 parser 参数,必须在子命令前
    rc = main(["--vault", str(vault), "triage-inbox"])
    out = capsys.readouterr().out
    assert rc == 0, f"expected exit 0, got {rc}"
    assert "1 inbox items pending triage" in out


def test_triage_inbox_with_explicit_config(tmp_path: Path, capsys):
    """triage-inbox 即使显式传 --config 也要能跑(向后兼容)。"""
    vault = tmp_path / "Garden"
    vault.mkdir()
    (vault / "_System" / "_Inbox").mkdir(parents=True)
    (vault / "_System" / "_Inbox" / "raw.md").write_text(
        "---\nstatus: inbox\ntype: raw\n---\n", encoding="utf-8"
    )
    cfg = vault / "_Config" / "gardener.config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("""\
version: 0.1
risk_levels:
  L0: {auto: true, needs_review: false, confirm: false}
  L1: {auto: true, needs_review: false, confirm: false, log: commit}
  L2: {auto: false, needs_review: true, confirm: once, log: commit+notion}
  L3: {auto: false, needs_review: true, confirm: twice, log: commit+notion}
operations:
  append_raw: L0
  append_draft: L0
  generate_report: L0
  create_proposal: L0
  backfill_frontmatter: L1
  add_wikilink: L1
  add_tag: L1
  create_evergreen: L2
  update_conclusion: L2
  merge_notes: L2
  rename_evergreen: L3
  move_evergreen: L3
  delete_evergreen: L3
actors:
  manual_session: [L0, L1, L2, L3]
  scheduled_run: [L0, L1]
hard_disabled: []
thresholds: {orphan_age_days: 7, stale_review_days: 90, confidence_min: 0.6, batch_l1_max: 50}
access: {preferred: cli, fallback: filesystem}
notion: {proposal_database_id: p, projects_database_id: q, mcp_endpoint: http://invalid}
""", encoding="utf-8")
    rc = main([
        "--vault", str(vault), "--config", str(cfg), "triage-inbox",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 inbox items pending triage" in out


def test_weekly_audit_missing_config_exits_5(tmp_path: Path, capsys):
    """修复:weekly-audit 在没 _Config/ 时给 exit 5 + 友好引导(不是裸 traceback)。

    旧行为:config 默认值相对 CWD → FileNotFoundError 裸栈。
    新行为:fallback 到 <vault>/_Config/gardener.config.yaml,失败时输出 init 引导。
    """
    vault = tmp_path / "Garden"
    vault.mkdir()
    _init_git_repo(vault)  # weekly-audit 需要 git pull OK
    rc = main(["--vault", str(vault), "weekly-audit"])
    assert rc == 5, f"expected exit 5, got {rc}"
    err = capsys.readouterr().err
    assert "找不到 config" in err or "config" in err
    assert "Traceback" not in err
    assert "garden init" in err  # 给用户下一步指引


def test_apply_approved_notion_unreachable_exits_4(tmp_path: Path, capsys):
    """修复:apply-approved 在 Notion endpoint 不可达时给 exit 4 + 友好文案。

    旧行为:httpx.RequestError 裸栈飘到 stderr,cron 误判失败。
    新行为:catch 住 + 友好文案 + exit 4。
    """
    import shutil
    vault = tmp_path / "Garden"
    vault.mkdir()
    _init_git_repo(vault)

    cfg = vault / "_Config" / "gardener.config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    # 故意用一个不可能的 protocol 触发 UnsupportedProtocol(不会发请求,但会抛)
    cfg.write_text("""\
version: 0.1
risk_levels:
  L0: {auto: true, needs_review: false, confirm: false}
  L1: {auto: true, needs_review: false, confirm: false, log: commit}
  L2: {auto: false, needs_review: true, confirm: once, log: commit+notion}
  L3: {auto: false, needs_review: true, confirm: twice, log: commit+notion}
operations:
  append_raw: L0
  append_draft: L0
  generate_report: L0
  create_proposal: L0
  backfill_frontmatter: L1
  add_wikilink: L1
  add_tag: L1
  create_evergreen: L2
  update_conclusion: L2
  merge_notes: L2
  rename_evergreen: L3
  move_evergreen: L3
  delete_evergreen: L3
actors:
  manual_session: [L0, L1, L2, L3]
  scheduled_run: [L0, L1]
hard_disabled: []
thresholds: {orphan_age_days: 7, stale_review_days: 90, confidence_min: 0.6, batch_l1_max: 50}
access: {preferred: cli, fallback: filesystem}
notion: {proposal_database_id: p, projects_database_id: q, mcp_endpoint: invalid-no-protocol}
""", encoding="utf-8")
    rc = main(["--vault", str(vault), "apply-approved"])
    assert rc == 4, f"expected exit 4 (Notion unreachable), got {rc}"
    err = capsys.readouterr().err
    assert "Notion 不可达" in err
    assert "Traceback" not in err
    assert "幂等" in err  # 提示用户 retry 是安全的
