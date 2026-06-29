import pytest
from garden_gardener.config import Config
from garden_gardener.risk import decide, Decision, Actor, SANCTIONED_OPS


def _cfg() -> Config:
    return Config(
        raw={},
        risk_levels={
            "L0": {"auto": True,  "needs_review": False, "confirm": False},
            "L1": {"auto": True,  "needs_review": False, "confirm": False},
            "L2": {"auto": False, "needs_review": True,  "confirm": "once"},
            "L3": {"auto": False, "needs_review": True,  "confirm": "twice"},
        },
        operations={"append_raw": "L0", "create_evergreen": "L2", "delete_evergreen": "L3"},
        actors={"manual_session": ["L0", "L1", "L2", "L3"], "scheduled_run": ["L0", "L1"]},
        hard_disabled=[{"unsanctioned": "create_evergreen"}, {"any": "notion_delete"}],
        thresholds={"confidence_min": 0.6},
        access={"preferred": "cli", "fallback": "filesystem"},
        notion={},
    )


def test_l0_auto_allowed_for_scheduled():
    d = decide(_cfg(), Actor.SCHEDULED, "append_raw", sanctioned=False)
    assert d == Decision.AUTO  # L0 自由


def test_l2_requires_sanction_unsanctioned_blocked():
    d = decide(_cfg(), Actor.SCHEDULED, "create_evergreen", sanctioned=False)
    assert d == Decision.BLOCKED  # 无 Notion approved 凭证,硬禁


def test_l2_sanctioned_allowed_when_manual():
    d = decide(_cfg(), Actor.MANUAL, "create_evergreen", sanctioned=True)
    assert d == Decision.APPLY  # 有凭证,手动会话,放行 apply


def test_scheduled_can_apply_sanctioned_l2():
    d = decide(_cfg(), Actor.SCHEDULED, "create_evergreen", sanctioned=True)
    assert d == Decision.APPLY  # 定时可应用已 Notion approved 的写


def test_actor_cannot_exceed_capability():
    # scheduled_run 的 actors 上限是 [L0,L1];L3 即便 sanctioned 也拒(超能力)
    d = decide(_cfg(), Actor.SCHEDULED, "delete_evergreen", sanctioned=True)
    assert d == Decision.BLOCKED


def test_notion_delete_always_blocked():
    # hard_disabled: any: notion_delete —— 注意 notion_delete 不在 operations,
    # 但 hard_disabled(any 类)在查风险档之前先判,故直接 BLOCKED
    d = decide(_cfg(), Actor.MANUAL, "notion_delete", sanctioned=True)
    assert d == Decision.BLOCKED
