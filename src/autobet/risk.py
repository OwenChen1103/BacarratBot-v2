# src/autobet/risk.py
import hashlib, logging
from dataclasses import dataclass
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

@dataclass
class Limits:
    per_round_cap: int
    session_stop_loss: int
    session_take_profit: int

class IdempotencyGuard:
    def __init__(self):
        self.seen = set()

    def key(self, round_id: str, plan_repr: str) -> str:
        h = hashlib.md5(plan_repr.encode("utf-8")).hexdigest()
        return f"{round_id}:{h}"

    def accept(self, round_id: str, plan_repr: str) -> bool:
        k = self.key(round_id, plan_repr)
        if k in self.seen:
            return False
        self.seen.add(k)
        return True

def check_limits(limits_cfg: Dict, this_round_amount: int, net_profit: int) -> Tuple[bool, str]:
    lim = Limits(
        per_round_cap=int(limits_cfg.get("per_round_cap", 10000)),
        session_stop_loss=int(limits_cfg.get("session_stop_loss", -20000)),
        session_take_profit=int(limits_cfg.get("session_take_profit", 30000)),
    )
    if this_round_amount > lim.per_round_cap:
        return False, f"per_round_cap exceeded: {this_round_amount} > {lim.per_round_cap}"
    if net_profit <= lim.session_stop_loss:
        return False, f"stop_loss hit: net={net_profit}"
    if net_profit >= lim.session_take_profit:
        return False, f"take_profit hit: net={net_profit}"
    return True, "ok"