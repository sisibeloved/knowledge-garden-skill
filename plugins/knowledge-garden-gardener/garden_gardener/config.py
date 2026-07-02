from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml


class ConfigError(Exception):
    """配置加载或校验错误。"""


@dataclass
class Config:
    raw: dict
    operations: dict
    actors: dict
    hard_disabled: list
    thresholds: dict
    access: dict
    notion: dict
    risk_levels: dict

    def risk_of(self, operation: str) -> str:
        if operation not in self.operations:
            raise ConfigError(f"unknown operation: {operation}")
        level = self.operations[operation]
        if level not in self.risk_levels:
            raise ConfigError(
                f"operation {operation} maps to unknown risk level {level}"
            )
        return level


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = ["risk_levels", "operations", "actors", "hard_disabled",
                "thresholds", "access", "notion"]
    for k in required:
        if k not in data:
            raise ConfigError(f"missing top-level key: {k}")
    cfg = Config(
        raw=data, risk_levels=data["risk_levels"], operations=data["operations"],
        actors=data["actors"], hard_disabled=data["hard_disabled"],
        thresholds=data["thresholds"], access=data["access"], notion=data["notion"],
    )
    # 校验所有 operation 映射的 risk level 都存在(触发 ConfigError)
    for op, lvl in cfg.operations.items():
        cfg.risk_of(op)
    return cfg
