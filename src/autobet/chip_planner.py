# src/autobet/chip_planner.py
"""
智能籌碼規劃器
根據目標金額和可用籌碼，計算最佳下注組合
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from collections import Counter
import logging

logger = logging.getLogger(__name__)


@dataclass
class Chip:
    """籌碼資訊"""
    slot: int           # 籌碼槽位 (1-6)
    value: int          # 籌碼金額
    label: str          # 顯示標籤 (例如 "1K", "100")
    x: int = 0          # 螢幕 X 座標
    y: int = 0          # 螢幕 Y 座標
    calibrated: bool = False  # 是否已校準


@dataclass
class BetPlan:
    """下注計劃"""
    success: bool                    # 是否成功規劃
    target_amount: int               # 目標金額
    actual_amount: int               # 實際金額（可能不同）
    chips: List[Chip] = field(default_factory=list)  # 籌碼序列
    clicks: int = 0                  # 總點擊次數
    recipe: str = ""                 # 人話配方
    warnings: List[str] = field(default_factory=list)  # 警告訊息
    reason: str = ""                 # 失敗原因


class BettingPolicy:
    """下注策略配置"""

    # 優先級
    MIN_CLICKS = "min_clicks"           # 最少點擊
    EXACT_MATCH = "exact_match"         # 精確匹配
    CONSERVATIVE_FLOOR = "conservative_floor"  # 保守向下

    # Fallback 策略
    FLOOR = "floor"         # 向下取整
    CEIL = "ceil"           # 向上取整
    ALT_COMBO = "alt_combo" # 替代組合
    SKIP = "skip"           # 跳過本手

    def __init__(
        self,
        priority: str = MIN_CLICKS,
        fallback: str = FLOOR,
        allow_partial: bool = False
    ):
        self.priority = priority
        self.fallback = fallback
        self.allow_partial = allow_partial


class SmartChipPlanner:
    """智能籌碼規劃器"""

    def __init__(self, available_chips: List[Chip], policy: Optional[BettingPolicy] = None):
        """
        初始化規劃器

        Args:
            available_chips: 可用的籌碼列表（已校準的）
            policy: 下注策略，預設為最少點擊
        """
        self.available_chips = sorted(
            available_chips,
            key=lambda c: c.value,
            reverse=True  # 由大到小排序
        )
        self.policy = policy or BettingPolicy()

        logger.info(f"SmartChipPlanner 初始化: {len(self.available_chips)} 顆可用籌碼")
        for chip in self.available_chips:
            logger.info(f"  Chip {chip.slot}: {chip.label} ({chip.value}元)")

    def plan_bet(
        self,
        target_amount: int,
        max_clicks: Optional[int] = None
    ) -> BetPlan:
        """
        規劃下注方案

        Args:
            target_amount: 目標金額
            max_clicks: 最大點擊次數限制

        Returns:
            BetPlan: 下注計劃
        """
        if target_amount <= 0:
            return BetPlan(
                success=False,
                target_amount=target_amount,
                actual_amount=0,
                reason="目標金額必須大於 0"
            )

        if not self.available_chips:
            return BetPlan(
                success=False,
                target_amount=target_amount,
                actual_amount=0,
                reason="沒有可用的籌碼（請先校準籌碼位置）"
            )

        # 根據策略選擇規劃方法
        if self.policy.priority == BettingPolicy.MIN_CLICKS:
            return self._plan_min_clicks(target_amount, max_clicks)
        elif self.policy.priority == BettingPolicy.EXACT_MATCH:
            return self._plan_exact_match(target_amount, max_clicks)
        elif self.policy.priority == BettingPolicy.CONSERVATIVE_FLOOR:
            return self._plan_conservative_floor(target_amount, max_clicks)
        else:
            return self._plan_min_clicks(target_amount, max_clicks)

    def _plan_min_clicks(
        self,
        target_amount: int,
        max_clicks: Optional[int] = None
    ) -> BetPlan:
        """
        最少點擊策略：貪婪法，從大到小湊
        """
        remain = target_amount
        selected_chips: List[Chip] = []

        # 貪婪法
        for chip in self.available_chips:
            count = remain // chip.value
            if count > 0:
                selected_chips.extend([chip] * int(count))
                remain -= chip.value * count

        actual_amount = target_amount - remain
        clicks = len(selected_chips)

        # 檢查是否超過點擊限制
        if max_clicks and clicks > max_clicks:
            return self._handle_too_many_clicks(
                target_amount, selected_chips, max_clicks
            )

        # 檢查是否完全匹配
        if remain > 0:
            return self._handle_partial_match(
                target_amount, actual_amount, selected_chips, remain
            )

        # 成功
        return BetPlan(
            success=True,
            target_amount=target_amount,
            actual_amount=actual_amount,
            chips=selected_chips,
            clicks=clicks,
            recipe=self._format_recipe(selected_chips)
        )

    def _plan_exact_match(
        self,
        target_amount: int,
        max_clicks: Optional[int] = None
    ) -> BetPlan:
        """
        精確匹配策略：使用動態規劃找到精確組合
        （簡化版：先用貪婪法，未來可擴展為完整 DP）
        """
        # 目前簡化為貪婪法，未來可實作完整的動態規劃
        return self._plan_min_clicks(target_amount, max_clicks)

    def _plan_conservative_floor(
        self,
        target_amount: int,
        max_clicks: Optional[int] = None
    ) -> BetPlan:
        """
        保守向下策略：只使用可精確組合的最大金額
        """
        plan = self._plan_min_clicks(target_amount, max_clicks)

        if not plan.success and plan.actual_amount < target_amount:
            # 接受向下取整的結果
            plan.success = True
            plan.warnings.append(
                f"使用向下取整: 目標 {target_amount} 元，實際 {plan.actual_amount} 元"
            )

        return plan

    def _handle_too_many_clicks(
        self,
        target_amount: int,
        chips: List[Chip],
        max_clicks: int
    ) -> BetPlan:
        """處理點擊次數過多的情況"""
        clicks = len(chips)
        actual_amount = sum(c.value for c in chips)

        if self.policy.fallback == BettingPolicy.FLOOR:
            # 向下取整：減少籌碼直到符合點擊限制
            truncated_chips = chips[:max_clicks]
            actual = sum(c.value for c in truncated_chips)

            return BetPlan(
                success=True,
                target_amount=target_amount,
                actual_amount=actual,
                chips=truncated_chips,
                clicks=len(truncated_chips),
                recipe=self._format_recipe(truncated_chips),
                warnings=[
                    f"超過點擊限制 (需要 {clicks} 次，限制 {max_clicks} 次)",
                    f"向下取整至 {actual} 元"
                ]
            )

        elif self.policy.fallback == BettingPolicy.SKIP:
            return BetPlan(
                success=False,
                target_amount=target_amount,
                actual_amount=0,
                reason=f"需要 {clicks} 次點擊，超過限制 {max_clicks} 次。建議校準更大面額籌碼"
            )

        else:
            # 預設：返回失敗
            return BetPlan(
                success=False,
                target_amount=target_amount,
                actual_amount=actual_amount,
                chips=chips,
                clicks=clicks,
                reason=f"需要 {clicks} 次點擊，超過限制 {max_clicks} 次"
            )

    def _handle_partial_match(
        self,
        target_amount: int,
        actual_amount: int,
        chips: List[Chip],
        remain: int
    ) -> BetPlan:
        """處理無法精確匹配的情況"""

        if self.policy.fallback == BettingPolicy.FLOOR:
            # 接受向下取整
            return BetPlan(
                success=True,
                target_amount=target_amount,
                actual_amount=actual_amount,
                chips=chips,
                clicks=len(chips),
                recipe=self._format_recipe(chips),
                warnings=[
                    f"無法精確組合 {target_amount} 元",
                    f"向下取整至 {actual_amount} 元 (剩餘 {remain} 元無法組合)"
                ]
            )

        elif self.policy.fallback == BettingPolicy.SKIP:
            return BetPlan(
                success=False,
                target_amount=target_amount,
                actual_amount=0,
                reason=f"無法精確組合 {target_amount} 元 (剩餘 {remain} 元)"
            )

        else:
            return BetPlan(
                success=False,
                target_amount=target_amount,
                actual_amount=actual_amount,
                chips=chips,
                clicks=len(chips),
                reason=f"無法精確組合 {target_amount} 元 (剩餘 {remain} 元)"
            )

    def _format_recipe(self, chips: List[Chip]) -> str:
        """
        格式化配方為人話

        例: [Chip(slot=2, value=1000), Chip(slot=2, value=1000)]
        返回: "2×1K (點擊 Chip 2 兩次，共 2 次點擊)"
        """
        if not chips:
            return "無籌碼"

        # 統計每種籌碼的數量
        counter = Counter((c.slot, c.label, c.value) for c in chips)

        parts = []
        for (slot, label, value), count in sorted(counter.items(), key=lambda x: -x[0][2]):
            parts.append(f"{count}×{label}")

        recipe_text = " + ".join(parts)
        total_clicks = len(chips)

        # 加上詳細說明
        if len(counter) == 1:
            # 只有一種籌碼
            slot = list(counter.keys())[0][0]
            count = list(counter.values())[0]
            if count == 1:
                return f"{recipe_text} (點擊 Chip {slot} 一次)"
            else:
                return f"{recipe_text} (點擊 Chip {slot} {count} 次)"
        else:
            # 多種籌碼
            return f"{recipe_text} (共 {total_clicks} 次點擊)"

    def validate_amount(
        self,
        amount: int,
        min_bet: int,
        max_bet: int,
        max_clicks: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        驗證金額是否可行

        Returns:
            (is_valid, error_message)
        """
        if amount < min_bet:
            return False, f"低於最小投注額 {min_bet} 元"

        if amount > max_bet:
            return False, f"超過最大投注額 {max_bet} 元"

        plan = self.plan_bet(amount, max_clicks)

        if not plan.success:
            return False, plan.reason

        if plan.warnings:
            # 有警告但仍可執行
            return True, None

        return True, None

    def get_recipe_preview(self, amounts: List[int]) -> Dict[int, str]:
        """
        批量獲取配方預覽（用於 UI 即時顯示）

        Args:
            amounts: 金額列表

        Returns:
            {amount: recipe_text, ...}
        """
        result = {}
        for amount in amounts:
            plan = self.plan_bet(amount)
            if plan.success:
                result[amount] = plan.recipe
            else:
                result[amount] = f"❌ {plan.reason}"

        return result
