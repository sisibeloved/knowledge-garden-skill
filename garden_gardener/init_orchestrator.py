from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .notion import NotionClient
from .init_vault import init_vault_skeleton
from .init_notion import create_all_databases, NotionBootstrapError
from .init_plugins import write_plugin_enable_list

# init 结果状态
COMPLETED = "completed"
NEEDS_OAUTH = "needs_oauth"

# config 模板(从 templates/gardener.config.yaml 派生的最小可运行版,
# init 把 database id 填进 notion 段)
_CONFIG_TEMPLATE = """\
version: 0.1

risk_levels:
  L0: {auto: true,  needs_review: false, confirm: false}
  L1: {auto: true,  needs_review: false, confirm: false, log: commit}
  L2: {auto: false, needs_review: true,  confirm: once,  log: commit+notion}
  L3: {auto: false, needs_review: true,  confirm: twice, log: commit+notion}

operations:
  append_raw:           L0
  append_draft:         L0
  generate_report:      L0
  create_proposal:      L0
  backfill_frontmatter: L1
  add_wikilink:         L1
  add_tag:              L1
  create_evergreen:     L2
  update_conclusion:    L2
  merge_notes:          L2
  rename_evergreen:     L3
  move_evergreen:       L3
  delete_evergreen:     L3

actors:
  manual_session: [L0, L1, L2, L3]
  scheduled_run:  [L0, L1]

hard_disabled:
  - unsanctioned: create_evergreen
  - any: notion_delete
  - any: overwrite_without_backup

thresholds:
  orphan_age_days: 7
  stale_review_days: 90
  confidence_min: 0.6
  batch_l1_max: 50

access:
  preferred: cli
  fallback: filesystem

notion:
  proposal_database_id: "__PROPOSAL_DB__"
  projects_database_id: "__PROJECTS_DB__"
  mcp_endpoint: "__MCP_ENDPOINT__"
"""


@dataclass
class InitState:
    done: bool = False
    steps: dict = field(default_factory=lambda: {
        "vault_skeleton": False,
        "oauth": False,
        "notion_databases": False,
        "config_written": False,
        "plugins": False,
    })
    database_ids: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "InitState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(done=data.get("done", False), steps=data.get("steps", {}),
                   database_ids=data.get("database_ids", {}))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                        encoding="utf-8")


def run_init(*, vault_root: Path, config_path: Path, checkpoint: Path,
             client: NotionClient, parent_page_id: str,
             oauth_already_done: bool) -> str:
    """引导整个知识花园。返回 COMPLETED 或 NEEDS_OAUTH。

    可断点续跑:读 checkpoint 跳过已完成步骤。OAuth 是唯一人工断点。
    """
    state = InitState.load(checkpoint)
    if state.done:
        return COMPLETED

    vault_root = Path(vault_root)

    # 1. vault 骨架(不需 OAuth)
    if not state.steps.get("vault_skeleton"):
        init_vault_skeleton(vault_root)
        state.steps["vault_skeleton"] = True
        state.save(checkpoint)

    # 2. OAuth 检查 —— 唯一人工断点
    if not oauth_already_done:
        state.steps["oauth"] = False
        state.save(checkpoint)
        return NEEDS_OAUTH
    state.steps["oauth"] = True

    # 3. Notion 4 库(需 OAuth + MCP 可达)
    if not state.steps.get("notion_databases"):
        try:
            ids = create_all_databases(client, parent_page_id=parent_page_id)
        except NotionBootstrapError as e:
            state.save(checkpoint)
            raise
        state.database_ids = ids
        state.steps["notion_databases"] = True
        state.save(checkpoint)

    # 4. 写 config(填入 database id + mcp_endpoint)
    # 用唯一标记替换,不用 .format()(避免 YAML 花括号被当占位符)
    if not state.steps.get("config_written"):
        config_path.parent.mkdir(parents=True, exist_ok=True)
        text = (_CONFIG_TEMPLATE
                .replace("__PROPOSAL_DB__", state.database_ids.get("待审核提案", ""))
                .replace("__PROJECTS_DB__", state.database_ids.get("Projects", ""))
                .replace("__MCP_ENDPOINT__", client.endpoint))
        config_path.write_text(text, encoding="utf-8")
        state.steps["config_written"] = True
        state.save(checkpoint)

    # 5. 插件启用清单
    if not state.steps.get("plugins"):
        write_plugin_enable_list(vault_root)
        state.steps["plugins"] = True
        state.save(checkpoint)

    state.done = True
    state.save(checkpoint)
    return COMPLETED
