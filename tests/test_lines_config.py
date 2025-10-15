# tests/test_lines_config.py
import json
from pathlib import Path

from src.autobet.lines.config import (
    AdvanceRule,
    CrossTableMode,
    DedupMode,
    RiskLevelAction,
    RiskScope,
    StackPolicy,
    parse_strategy_definition,
)


def build_definition(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_parse_strategy_definition_defaults(tmp_path):
    payload = {
        "strategy_key": "BB_to_P",
        "entry": {"pattern": "BB then bet P"},
        "staking": {"sequence": [10, 20, 40]},
    }
    definition = parse_strategy_definition(payload)

    assert definition.strategy_key == "BB_to_P"
    assert definition.entry.pattern == "BB then bet P"
    assert definition.entry.dedup == DedupMode.OVERLAP
    assert definition.staking.advance_on == AdvanceRule.LOSS
    assert definition.staking.sequence == [10, 20, 40]
    assert definition.staking.stack_policy == StackPolicy.NONE
    assert definition.cross_table_layer.mode == CrossTableMode.RESET
    assert definition.risk.levels == []


def test_parse_strategy_definition_with_risk(tmp_path):
    payload = {
        "strategy_key": "Aggressive",
        "entry": {
            "pattern": "PPP then bet B",
            "valid_window_sec": 12,
            "dedup": "overlap_dedup",
            "first_trigger_layer": 0,
        },
        "staking": {
            "sequence": [5, 10],
            "advance_on": "win",
            "reset_on_win": False,
            "reset_on_loss": True,
            "stack_policy": "parallel",
        },
        "cross_table_layer": {"mode": "accumulate"},
        "risk": {
            "levels": [
                {"scope": "table", "stop_loss": -500, "action": "pause"},
                {
                    "scope": "global_day",
                    "take_profit": 1500,
                    "action": "stop_all",
                    "cooldown_sec": 3600,
                },
            ]
        },
    }
    definition = parse_strategy_definition(payload)

    assert definition.entry.first_trigger_layer == 0
    assert definition.staking.advance_on == AdvanceRule.WIN
    assert definition.staking.stack_policy == StackPolicy.PARALLEL
    assert definition.cross_table_layer.mode == CrossTableMode.ACCUMULATE

    levels = definition.risk.sorted_levels()
    assert levels[0].scope == RiskScope.GLOBAL_DAY
    assert levels[0].action == RiskLevelAction.STOP_ALL
    assert levels[1].scope == RiskScope.TABLE
    assert levels[1].stop_loss == -500
