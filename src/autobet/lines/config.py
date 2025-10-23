# src/autobet/lines/config.py
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class DedupMode(str, Enum):
    NONE = "none"
    OVERLAP = "overlap_dedup"
    STRICT = "strict"


class AdvanceRule(str, Enum):
    WIN = "win"
    LOSS = "loss"


class StackPolicy(str, Enum):
    NONE = "none"
    MERGE = "merge"
    PARALLEL = "parallel"


class CrossTableMode(str, Enum):
    ACCUMULATE = "accumulate"
    RESET = "reset"


class RiskLevelAction(str, Enum):
    STOP_ALL = "stop_all"
    PAUSE = "pause"
    NOTIFY = "notify"


class RiskScope(str, Enum):
    GLOBAL_DAY = "global_day"
    TABLE = "table"
    TABLE_STRATEGY = "table_strategy"
    ALL_TABLES_STRATEGY = "all_tables_strategy"
    MULTI_STRATEGY = "multi_strategy"


@dataclass(frozen=True)
class EntryConfig:
    pattern: str
    valid_window_sec: float = 0.0
    dedup: DedupMode = DedupMode.STRICT  # 🔥 改為 STRICT，避免歷史重疊觸發
    first_trigger_layer: int = 1


@dataclass(frozen=True)
class StakingConfig:
    sequence: List[int]
    advance_on: AdvanceRule = AdvanceRule.LOSS
    reset_on_win: bool = True
    reset_on_loss: bool = False
    max_layers: Optional[int] = None
    per_hand_cap: Optional[float] = None
    stack_policy: StackPolicy = StackPolicy.NONE

    def __post_init__(self) -> None:
        if not self.sequence:
            raise ValueError("staking.sequence must contain at least one element")
        object.__setattr__(self, "sequence", list(self.sequence))


@dataclass(frozen=True)
class CrossTableLayerConfig:
    scope: str = "strategy_key"
    mode: CrossTableMode = CrossTableMode.RESET


@dataclass(frozen=True)
class RiskLevelConfig:
    scope: RiskScope
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    max_drawdown_losses: Optional[int] = None
    action: RiskLevelAction = RiskLevelAction.PAUSE
    cooldown_sec: Optional[float] = None


@dataclass(frozen=True)
class StrategyRiskConfig:
    levels: List[RiskLevelConfig] = field(default_factory=list)

    def sorted_levels(self) -> List[RiskLevelConfig]:
        priority = {
            RiskScope.GLOBAL_DAY: 1,
            RiskScope.TABLE: 2,
            RiskScope.TABLE_STRATEGY: 3,
            RiskScope.ALL_TABLES_STRATEGY: 4,
            RiskScope.MULTI_STRATEGY: 5,
        }
        return sorted(self.levels, key=lambda lvl: priority.get(lvl.scope, 99))


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_key: str
    entry: EntryConfig
    staking: StakingConfig
    cross_table_layer: CrossTableLayerConfig = CrossTableLayerConfig()
    risk: StrategyRiskConfig = StrategyRiskConfig()
    metadata: Dict[str, Any] = field(default_factory=dict)


def _require(data: Dict[str, Any], key: str, ctx: str) -> Any:
    if key not in data:
        raise KeyError(f"Missing required field '{key}' in {ctx}")
    return data[key]


def _parse_entry(cfg: Dict[str, Any]) -> EntryConfig:
    pattern = _require(cfg, "pattern", "entry")
    valid_window = float(cfg.get("valid_window_sec", 0) or 0)
    dedup = DedupMode(cfg.get("dedup", DedupMode.OVERLAP.value))
    first_trigger_layer = int(cfg.get("first_trigger_layer", 1))
    return EntryConfig(
        pattern=pattern,
        valid_window_sec=valid_window,
        dedup=dedup,
        first_trigger_layer=first_trigger_layer,
    )


def _parse_staking(cfg: Dict[str, Any]) -> StakingConfig:
    sequence_raw = cfg.get("sequence")
    if not isinstance(sequence_raw, Iterable):
        raise ValueError("staking.sequence must be an iterable of numbers")
    sequence = [int(x) for x in sequence_raw]
    advance_on = AdvanceRule(cfg.get("advance_on", AdvanceRule.LOSS.value))
    reset_on_win = bool(cfg.get("reset_on_win", advance_on == AdvanceRule.LOSS))
    reset_on_loss = bool(cfg.get("reset_on_loss", advance_on == AdvanceRule.WIN))
    max_layers = cfg.get("max_layers")
    per_hand_cap = cfg.get("per_hand_cap")
    stack_policy = StackPolicy(cfg.get("stack_policy", StackPolicy.NONE.value))

    return StakingConfig(
        sequence=sequence,
        advance_on=advance_on,
        reset_on_win=reset_on_win,
        reset_on_loss=reset_on_loss,
        max_layers=int(max_layers) if max_layers is not None else None,
        per_hand_cap=float(per_hand_cap) if per_hand_cap is not None else None,
        stack_policy=stack_policy,
    )


def _parse_cross_table(cfg: Optional[Dict[str, Any]]) -> CrossTableLayerConfig:
    if not cfg:
        return CrossTableLayerConfig()
    scope = cfg.get("scope", "strategy_key")
    mode = CrossTableMode(cfg.get("mode", CrossTableMode.RESET.value))
    return CrossTableLayerConfig(scope=scope, mode=mode)


def _parse_risk_level(cfg: Dict[str, Any]) -> RiskLevelConfig:
    scope = RiskScope(cfg.get("scope", RiskScope.TABLE.value))
    take_profit = cfg.get("take_profit")
    stop_loss = cfg.get("stop_loss")
    max_drawdown = cfg.get("max_drawdown_losses")
    action = RiskLevelAction(cfg.get("action", RiskLevelAction.PAUSE.value))
    cooldown_sec = cfg.get("cooldown_sec")
    return RiskLevelConfig(
        scope=scope,
        take_profit=float(take_profit) if take_profit is not None else None,
        stop_loss=float(stop_loss) if stop_loss is not None else None,
        max_drawdown_losses=int(max_drawdown) if max_drawdown is not None else None,
        action=action,
        cooldown_sec=float(cooldown_sec) if cooldown_sec is not None else None,
    )


def _parse_risk(cfg: Optional[Dict[str, Any]]) -> StrategyRiskConfig:
    if not cfg:
        return StrategyRiskConfig()
    levels_raw = cfg.get("levels", [])
    levels = [_parse_risk_level(level_cfg) for level_cfg in levels_raw]
    return StrategyRiskConfig(levels=levels)


def load_strategy_definition(source: Path) -> StrategyDefinition:
    if not source.exists():
        raise FileNotFoundError(f"Strategy definition not found: {source}")
    with source.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    return parse_strategy_definition(raw, context=str(source))


def load_strategy_definitions(directory: Path) -> Dict[str, StrategyDefinition]:
    if not directory.exists():
        raise FileNotFoundError(f"Strategy directory not found: {directory}")
    strategies: Dict[str, StrategyDefinition] = {}
    for path in directory.glob("*.json"):
        definition = load_strategy_definition(path)
        if definition.strategy_key in strategies:
            raise ValueError(f"Duplicate strategy_key '{definition.strategy_key}' in {path}")
        strategies[definition.strategy_key] = definition
    return strategies


def parse_strategy_definition(data: Dict[str, Any], context: str = "<dict>") -> StrategyDefinition:
    strategy_key = _require(data, "strategy_key", context)
    entry_cfg = _parse_entry(_require(data, "entry", context))
    staking_cfg = _parse_staking(_require(data, "staking", context))
    cross_table_cfg = _parse_cross_table(data.get("cross_table_layer"))
    risk_cfg = _parse_risk(data.get("risk"))
    metadata = data.get("metadata", {})
    if metadata and not isinstance(metadata, dict):
        raise ValueError("metadata must be a dictionary")
    return StrategyDefinition(
        strategy_key=str(strategy_key),
        entry=entry_cfg,
        staking=staking_cfg,
        cross_table_layer=cross_table_cfg,
        risk=risk_cfg,
        metadata=metadata or {},
    )
