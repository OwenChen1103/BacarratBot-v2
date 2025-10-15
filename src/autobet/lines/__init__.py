# src/autobet/lines/__init__.py
"""
Line strategy orchestration package.

This module exposes the primary entry points for strategy configuration,
state management, and signal tracking used by the auto-betting engine.
"""

from .config import (
    StrategyDefinition,
    EntryConfig,
    StakingConfig,
    CrossTableLayerConfig,
    RiskLevelAction,
    RiskScope,
    RiskLevelConfig,
    StrategyRiskConfig,
    load_strategy_definition,
    load_strategy_definitions,
    parse_strategy_definition,
)
from .state import LineState, LayerOutcome
from .signal import SignalTracker, SignalEvent
from .orchestrator import (
    LineOrchestrator,
    TablePhase,
    BetDecision,
    OrchestratorEvent,
)

__all__ = [
    "StrategyDefinition",
    "EntryConfig",
    "StakingConfig",
    "CrossTableLayerConfig",
    "RiskLevelAction",
    "RiskScope",
    "RiskLevelConfig",
    "StrategyRiskConfig",
    "load_strategy_definition",
    "load_strategy_definitions",
    "parse_strategy_definition",
    "LineState",
    "LayerOutcome",
    "SignalTracker",
    "SignalEvent",
    "LineOrchestrator",
    "TablePhase",
    "BetDecision",
    "OrchestratorEvent",
]
