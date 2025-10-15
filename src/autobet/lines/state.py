# src/autobet/lines/state.py
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from .config import AdvanceRule, StakingConfig


class LinePhase(str, Enum):
    IDLE = "idle"
    ARMED = "armed"
    ENTERED = "entered"
    WAITING_RESULT = "waiting_result"
    FROZEN = "frozen"
    EXITED = "exited"


class LayerOutcome(str, Enum):
    WIN = "win"
    LOSS = "loss"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class LayerState:
    index: int = 0
    stake: int = 0
    outcome: Optional[LayerOutcome] = None
    updated_at: float = field(default_factory=time.time)


@dataclass
class LineState:
    strategy_key: str
    table_id: str
    current_layer_index: int = 0
    armed_count: int = 0
    phase: LinePhase = LinePhase.IDLE
    pnl: float = 0.0
    last_round_id: Optional[str] = None
    cool_down_until: Optional[float] = None
    frozen: bool = False
    layer_state: LayerState = field(default_factory=LayerState)

    def enter(self, layer_index: int, stake: float, round_id: str) -> None:
        self.phase = LinePhase.ENTERED
        self.current_layer_index = layer_index
        self.layer_state = LayerState(index=layer_index, stake=int(stake))
        self.last_round_id = round_id
        self.armed_count = 0

    def mark_waiting(self) -> None:
        self.phase = LinePhase.WAITING_RESULT

    def record_outcome(self, outcome: LayerOutcome, pnl_delta: float) -> None:
        self.layer_state.outcome = outcome
        self.layer_state.updated_at = time.time()
        self.pnl += pnl_delta
        self.phase = LinePhase.IDLE

    def freeze(self, until: Optional[float]) -> None:
        self.frozen = True
        self.phase = LinePhase.FROZEN
        self.cool_down_until = until

    def unfreeze(self) -> None:
        self.frozen = False
        self.phase = LinePhase.IDLE
        self.cool_down_until = None


@dataclass
class LayerProgression:
    config: StakingConfig
    index: int = 0

    def current_stake(self) -> int:
        seq = self.config.sequence
        idx = min(self.index, len(seq) - 1)
        return seq[idx]

    def advance(self, outcome: LayerOutcome) -> None:
        if outcome == LayerOutcome.WIN:
            if self.config.advance_on == AdvanceRule.WIN:
                self.index = min(self.index + 1, len(self.config.sequence) - 1)
            if self.config.reset_on_win:
                self.reset()
        elif outcome == LayerOutcome.LOSS:
            if self.config.advance_on == AdvanceRule.LOSS:
                self.index = min(self.index + 1, len(self.config.sequence) - 1)
            if self.config.reset_on_loss:
                self.reset()

    def reset(self) -> None:
        self.index = 0


@dataclass
class LayerPool:
    """Shared layer progression state for cross-table accumulate mode."""

    strategy_key: str
    progression: LayerProgression
    table_indices: Dict[str, int] = field(default_factory=dict)

    def current_index(self, table_id: str) -> int:
        return self.table_indices.get(table_id, self.progression.index)

    def update_index(self, table_id: str, index: int) -> None:
        self.table_indices[table_id] = index
        self.progression.index = max(self.progression.index, index)
