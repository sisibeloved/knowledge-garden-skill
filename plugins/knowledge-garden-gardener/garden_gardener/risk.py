from __future__ import annotations
from enum import Enum
from .config import Config


class Decision(Enum):
    AUTO = "auto"       # 直接写(L0 追加 / L1 自动+留 commit)
    APPLY = "apply"     # 有 Notion approved 凭证,执行 apply
    BLOCKED = "blocked" # 硬禁(无凭证写 L2+/超出 actor 能力/hard_disabled)


class Actor(Enum):
    MANUAL = "manual_session"
    SCHEDULED = "scheduled_run"


# 需要授权凭证(Notion approved)才允许 apply 的操作族
SANCTIONED_OPS = {
    "create_evergreen", "update_conclusion", "merge_notes",
    "rename_evergreen", "move_evergreen", "delete_evergreen",
}


def _is_hard_disabled(cfg: Config, operation: str) -> bool:
    """hard_disabled 里 any 类规则:任何 actor 都禁。unsanctioned 类由 sanctioned 参数处理。"""
    for rule in cfg.hard_disabled:
        if "any" in rule and rule["any"] == operation:
            return True
    return False


def decide(cfg: Config, actor: Actor, operation: str, sanctioned: bool) -> Decision:
    """WHO × WHAT 风险分级判定。所有授权决策都过此函数。

    规则(由测试用例固化为权威):
    - hard_disabled(any 类)→ 任何 actor/凭证都 BLOCKED。
    - L0/L1(自动档)→ AUTO,无需凭证。
    - L2(需审批)→ 须 sanctioned;凭证齐全则任意 actor 可 apply(包括 SCHEDULED,
      因为这是“应用已授权写”,不是“无授权擅写”)。
    - L3(破坏性:delete/move/rename)→ 须 sanctioned;且即便 sanctioned,
      也受 actor 能力上限约束(仅 MANUAL 可执行 L3,SCHEDULED 即便已授权也拒——
      因为破坏性操作要求人在场)。
    """
    # 1. hard_disabled(any 类)直接拒,不依赖 operation 是否在 operations 表里
    if _is_hard_disabled(cfg, operation):
        return Decision.BLOCKED

    # 2. 查风险档(此时 operation 必须在 operations 表里,否则 ConfigError 上抛)
    risk = cfg.risk_of(operation)
    risk_def = cfg.risk_levels[risk]

    # 3. 自动档(L0/L1):不需要凭证
    if risk_def["auto"]:
        return Decision.AUTO

    # 4. 需审批档(L2/L3):必须有 sanctioned(Notion approved)凭证
    if operation in SANCTIONED_OPS and not sanctioned:
        return Decision.BLOCKED

    # 5. L3 破坏性操作:即便 sanctioned,也受 actor 能力上限约束
    if risk == "L3":
        allowed_levels = set(cfg.actors[actor.value])
        if "L3" not in allowed_levels:
            return Decision.BLOCKED

    return Decision.APPLY
