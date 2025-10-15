# tests/test_line_orchestrator.py
import time

from src.autobet.lines import (
    LineOrchestrator,
    TablePhase,
    parse_strategy_definition,
)


def build_definition(**overrides):
    base = {
        "strategy_key": "BB_to_P",
        "entry": {"pattern": "BB then bet P"},
        "staking": {"sequence": [10, 20, 40]},
    }
    base.update(overrides)
    return parse_strategy_definition(base)


def test_orchestrator_generates_decision_with_signal():
    definition = build_definition()
    orchestrator = LineOrchestrator(
        bankroll=1000,
        per_hand_risk_pct=0.1,
        per_table_risk_pct=0.2,
        per_hand_cap=100,
        max_concurrent_tables=3,
        min_unit=1.0,
    )

    orchestrator.register_strategy(definition, tables=["WG7"])

    now = time.time()
    orchestrator.handle_result("WG7", "1", "B", now - 10)
    orchestrator.handle_result("WG7", "2", "B", now - 5)

    decisions = orchestrator.update_table_phase("WG7", "3", TablePhase.BETTABLE, now)
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.table_id == "WG7"
    assert decision.direction.value == "P"
    assert decision.amount == 10


def test_orchestrator_applies_risk_freeze_on_loss_streak():
    definition = build_definition(
        risk={
            "levels": [
                {
                    "scope": "table_strategy",
                    "max_drawdown_losses": 1,
                    "action": "pause",
                }
            ]
        }
    )
    orchestrator = LineOrchestrator(
        bankroll=1000,
        per_hand_risk_pct=0.5,
        per_table_risk_pct=0.5,
        per_hand_cap=200,
        max_concurrent_tables=3,
        min_unit=1.0,
    )
    orchestrator.register_strategy(definition, tables=["WG8"])

    now = time.time()
    orchestrator.handle_result("WG8", "1", "B", now - 10)
    orchestrator.handle_result("WG8", "2", "B", now - 5)

    decisions = orchestrator.update_table_phase("WG8", "3", TablePhase.BETTABLE, now)
    assert decisions, "first entry expected"
    decision = decisions[0]

    # simulate losing the bet
    orchestrator.handle_result("WG8", decision.round_id, "B", now + 10)

    # Next trigger should be blocked due to risk freeze (needs another pattern)
    orchestrator.handle_result("WG8", "4", "B", now + 20)
    orchestrator.handle_result("WG8", "5", "B", now + 25)
    next_decisions = orchestrator.update_table_phase("WG8", "6", TablePhase.BETTABLE, now + 30)
    assert not next_decisions, "risk freeze should block new entries"


def test_snapshot_restore_roundtrip():
    definition = build_definition()
    orchestrator = LineOrchestrator(
        bankroll=500,
        per_hand_risk_pct=0.2,
        per_table_risk_pct=0.3,
        per_hand_cap=80,
        max_concurrent_tables=2,
        min_unit=1.0,
    )
    orchestrator.register_strategy(definition, tables=["WG9"])

    now = time.time()
    orchestrator.handle_result("WG9", "1", "B", now - 15)
    orchestrator.handle_result("WG9", "2", "B", now - 10)
    decisions = orchestrator.update_table_phase("WG9", "3", TablePhase.BETTABLE, now)
    assert decisions
    decision = decisions[0]
    orchestrator.handle_result("WG9", decision.round_id, "P", now + 5)

    snapshot = orchestrator.snapshot()

    restored = LineOrchestrator(
        bankroll=500,
        per_hand_risk_pct=0.2,
        per_table_risk_pct=0.3,
        per_hand_cap=80,
        max_concurrent_tables=2,
        min_unit=1.0,
    )
    restored.register_strategy(definition, tables=["WG9"])
    restored.restore_state(snapshot)

    restored_state = restored.snapshot()
    assert restored_state["capital"]["bankroll_free"] == snapshot["capital"]["bankroll_free"]
    assert restored_state["lines"] == snapshot["lines"]
