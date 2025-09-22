"""
策略管理模組 - 讀寫驗證策略配置，處理過濾器和遞增邏輯
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class StakingType(Enum):
    """遞增策略類型"""
    FIXED = "fixed"
    MARTINGALE = "martingale"
    ANTI_MARTINGALE = "anti_martingale"
    FIBONACCI = "fibonacci"


@dataclass
class StrategyLimits:
    """策略限制"""
    per_round_cap: int = 10000
    session_stop_loss: int = -20000
    session_take_profit: int = 30000
    max_retries: int = 1
    max_consecutive_losses: int = 5


@dataclass
class StakingConfig:
    """遞增策略配置"""
    type: StakingType = StakingType.FIXED
    base_units: int = 1
    max_steps: int = 3
    reset_on_win: bool = True
    progression: List[int] = None

    def __post_init__(self):
        if self.progression is None:
            if self.type == StakingType.MARTINGALE:
                self.progression = [1, 2, 4, 8][:self.max_steps]
            elif self.type == StakingType.FIBONACCI:
                self.progression = [1, 1, 2, 3, 5, 8][:self.max_steps]
            else:
                self.progression = [1] * self.max_steps


@dataclass
class StrategyFilter:
    """策略過濾器"""
    name: str
    when: str  # 條件表達式，如 "last_winner == 'P'"
    override_targets: Optional[List[str]] = None
    override_units: Optional[Dict[str, int]] = None
    enabled: bool = True


class StrategyManager:
    """策略配置管理器"""

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.unit: int = 1000
        self.targets: List[str] = ["banker"]
        self.split_units: Dict[str, int] = {"banker": 1}
        self.staking: StakingConfig = StakingConfig()
        self.filters: List[StrategyFilter] = []
        self.limits: StrategyLimits = StrategyLimits()
        self.conditions: Dict[str, Any] = {}

        # 狀態追蹤
        self.current_step: int = 0
        self.last_winner: Optional[str] = None
        self.win_streak: int = 0
        self.loss_streak: int = 0
        self.session_profit: int = 0
        self.round_count: int = 0

    def load_from_file(self, file_path: str) -> bool:
        """從檔案載入策略配置"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"策略配置檔案不存在: {file_path}")
                return False

            with open(file_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)

            # 載入基本配置
            self.unit = self.config.get('unit', 1000)
            self.targets = self.config.get('targets', ["banker"])
            self.split_units = self.config.get('split_units', {"banker": 1})

            # 載入遞增策略
            staking_config = self.config.get('staking', {})
            self.staking = self._load_staking_config(staking_config)

            # 載入過濾器
            filters_config = self.config.get('filters', [])
            self.filters = self._load_filters(filters_config)

            # 載入限制
            limits_config = self.config.get('limits', {})
            self.limits = self._load_limits(limits_config)

            # 載入條件
            self.conditions = self.config.get('conditions', {})

            logger.info(f"成功載入策略配置: {file_path}")
            return True

        except Exception as e:
            logger.error(f"載入策略配置失敗: {e}")
            return False

    def _load_staking_config(self, config: Dict[str, Any]) -> StakingConfig:
        """載入遞增策略配置"""
        staking_type = StakingType(config.get('type', 'fixed'))
        base_units = config.get('base_units', 1)
        max_steps = config.get('max_steps', 3)
        reset_on_win = config.get('reset_on_win', True)
        progression = config.get('progression')

        return StakingConfig(
            type=staking_type,
            base_units=base_units,
            max_steps=max_steps,
            reset_on_win=reset_on_win,
            progression=progression
        )

    def _load_filters(self, filters_config: List[Dict[str, Any]]) -> List[StrategyFilter]:
        """載入策略過濾器"""
        filters = []
        for filter_config in filters_config:
            filter_obj = StrategyFilter(
                name=filter_config.get('name', ''),
                when=filter_config.get('when', ''),
                override_targets=filter_config.get('override_targets'),
                override_units=filter_config.get('override_units'),
                enabled=filter_config.get('enabled', True)
            )
            filters.append(filter_obj)
        return filters

    def _load_limits(self, limits_config: Dict[str, Any]) -> StrategyLimits:
        """載入策略限制"""
        return StrategyLimits(
            per_round_cap=limits_config.get('per_round_cap', 10000),
            session_stop_loss=limits_config.get('session_stop_loss', -20000),
            session_take_profit=limits_config.get('session_take_profit', 30000),
            max_retries=limits_config.get('max_retries', 1),
            max_consecutive_losses=limits_config.get('max_consecutive_losses', 5)
        )

    def get_current_plan(self) -> Dict[str, Any]:
        """取得當前下注計劃"""
        # 應用過濾器
        current_targets = self.targets.copy()
        current_units = self.split_units.copy()

        for filter_obj in self.filters:
            if filter_obj.enabled and self._evaluate_filter_condition(filter_obj.when):
                if filter_obj.override_targets:
                    current_targets = filter_obj.override_targets
                if filter_obj.override_units:
                    current_units = filter_obj.override_units
                logger.info(f"應用過濾器: {filter_obj.name}")

        # 計算當前步驟的單位數
        current_multiplier = self._get_current_multiplier()

        # 生成下注計劃
        plan = {
            "unit": self.unit,
            "targets": current_targets,
            "split_units": current_units,
            "multiplier": current_multiplier,
            "step": self.current_step,
            "total_amount": 0,
            "target_amounts": {}
        }

        # 計算各目標的金額
        total_amount = 0
        for target in current_targets:
            target_units = current_units.get(target, 1)
            target_amount = target_units * current_multiplier * self.unit
            plan["target_amounts"][target] = target_amount
            total_amount += target_amount

        plan["total_amount"] = total_amount

        # 檢查限制
        if total_amount > self.limits.per_round_cap:
            logger.warning(f"下注金額 {total_amount} 超過單局上限 {self.limits.per_round_cap}")
            return None

        return plan

    def _evaluate_filter_condition(self, condition: str) -> bool:
        """評估過濾器條件"""
        try:
            # 建立評估環境
            env = {
                'last_winner': self.last_winner,
                'win_streak': self.win_streak,
                'loss_streak': self.loss_streak,
                'session_profit': self.session_profit,
                'round_count': self.round_count,
                'current_step': self.current_step
            }

            # 安全評估表達式
            return eval(condition, {"__builtins__": {}}, env)

        except Exception as e:
            logger.error(f"評估過濾器條件失敗: {condition}, 錯誤: {e}")
            return False

    def _get_current_multiplier(self) -> int:
        """取得當前步驟的倍數"""
        if self.current_step >= len(self.staking.progression):
            return self.staking.progression[-1]
        return self.staking.progression[self.current_step]

    def update_result(self, winner: str, amount_bet: int, is_win: bool):
        """更新結果並調整策略狀態"""
        self.last_winner = winner
        self.round_count += 1

        if is_win:
            self.win_streak += 1
            self.loss_streak = 0
            self.session_profit += amount_bet  # 簡化計算，實際可能需要根據賠率

            # 勝利時重置步驟
            if self.staking.reset_on_win:
                self.current_step = 0

        else:
            self.loss_streak += 1
            self.win_streak = 0
            self.session_profit -= amount_bet

            # 失敗時推進步驟
            if self.staking.type in [StakingType.MARTINGALE, StakingType.FIBONACCI]:
                self.current_step = min(self.current_step + 1, self.staking.max_steps - 1)

        logger.info(f"結果更新 - 勝者: {winner}, 勝利: {is_win}, "
                   f"連勝: {self.win_streak}, 連敗: {self.loss_streak}, "
                   f"會話收益: {self.session_profit}")

    def check_limits(self) -> Dict[str, bool]:
        """檢查是否觸發限制"""
        limits_hit = {
            "stop_loss": self.session_profit <= self.limits.session_stop_loss,
            "take_profit": self.session_profit >= self.limits.session_take_profit,
            "max_losses": self.loss_streak >= self.limits.max_consecutive_losses
        }

        return limits_hit

    def should_pause(self) -> bool:
        """是否應該暫停"""
        limits = self.check_limits()
        return any(limits.values())

    def reset_session(self):
        """重置會話狀態"""
        self.current_step = 0
        self.last_winner = None
        self.win_streak = 0
        self.loss_streak = 0
        self.session_profit = 0
        self.round_count = 0
        logger.info("策略會話狀態已重置")

    def save_to_file(self, file_path: str) -> bool:
        """儲存策略配置到檔案"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)

            logger.info(f"策略配置已儲存: {file_path}")
            return True

        except Exception as e:
            logger.error(f"儲存策略配置失敗: {e}")
            return False