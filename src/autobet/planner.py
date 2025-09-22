# src/autobet/planner.py
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

CHIPS = [50000, 10000, 5000, 1000, 100]  # 由大到小

def decompose_amount(amount: int) -> Tuple[int, List[int]]:
    amount = max(0, int(amount // 100) * 100)
    remain = amount
    chips: List[int] = []
    for v in CHIPS:
        n = remain // v
        if n > 0:
            chips += [v] * n
            remain -= v * n
    actual = amount - remain
    return actual, chips

def build_click_plan(unit: int, targets_units: Dict[str, int]) -> List[Tuple[str, str]]:
    """
    回傳 [('chip','1000'), ... , ('bet','banker'), ('confirm','')]
    不含 confirm，讓引擎決定送單前的 overlay 最終檢查。
    """
    plan: List[Tuple[str, str]] = []
    total = 0
    # 先把所有 chips 點擊排好，再按各標的下注
    for t, u in targets_units.items():
        amt = unit * int(u)
        actual, chips = decompose_amount(amt)
        total += actual
        for c in chips:
            plan.append(('chip', str(c)))
        plan.append(('bet', t))
    logger.debug(f"plan total={total}, steps={len(plan)}")
    return plan