import textwrap
from pathlib import Path
from garden_gardener.config import load_config, ConfigError

SAMPLE = textwrap.dedent("""
version: 0.1
risk_levels:
  L0: {auto: true, needs_review: false, confirm: false}
  L1: {auto: true, needs_review: false, confirm: false, log: commit}
  L2: {auto: false, needs_review: true, confirm: once, log: commit+notion}
  L3: {auto: false, needs_review: true, confirm: twice, log: commit+notion}
operations:
  append_raw: L0
  create_evergreen: L2
  delete_evergreen: L3
actors:
  manual_session: [L0, L1, L2, L3]
  scheduled_run: [L0, L1]
hard_disabled:
  - unsanctioned: create_evergreen
  - any: notion_delete
thresholds: {orphan_age_days: 7, confidence_min: 0.6, batch_l1_max: 50}
access: {preferred: cli, fallback: filesystem}
notion: {proposal_database_id: "db-1", projects_database_id: "db-2", mcp_endpoint: "http://x"}
""")


def test_load_config_parses_fields(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(SAMPLE, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.operations["create_evergreen"] == "L2"
    assert cfg.actors["scheduled_run"] == ["L0", "L1"]
    assert cfg.thresholds["orphan_age_days"] == 7


def test_load_config_rejects_missing_risk_level(tmp_path: Path):
    bad = tmp_path / "c.yaml"
    body = SAMPLE.replace("  create_evergreen: L2", "  create_evergreen: L9")
    bad.write_text(body, encoding="utf-8")
    try:
        load_config(bad)
        assert False, "should have raised"
    except ConfigError as e:
        assert "L9" in str(e)
