# src/autobet/risk_templates.py
"""風控範本系統"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .lines.config import RiskLevelConfig, RiskScope, RiskLevelAction


@dataclass
class RiskTemplate:
    """風控範本"""
    key: str
    name: str
    description: str
    icon: str
    levels: List[RiskLevelConfig]


class RiskTemplateLibrary:
    """風控範本庫"""

    @staticmethod
    def conservative() -> RiskTemplate:
        """保守型風控 - 多層保護,嚴格控管"""
        return RiskTemplate(
            key="conservative",
            name="保守型風控",
            description="多層風控保護,嚴格控制風險,適合新手",
            icon="🛡️",
            levels=[
                # 全域單日限制
                RiskLevelConfig(
                    scope=RiskScope.GLOBAL_DAY,
                    take_profit=5000.0,
                    stop_loss=-2000.0,
                    max_drawdown_losses=None,
                    action=RiskLevelAction.STOP_ALL,
                    cooldown_sec=None,
                ),
                # 單桌限制
                RiskLevelConfig(
                    scope=RiskScope.TABLE,
                    take_profit=1000.0,
                    stop_loss=-500.0,
                    max_drawdown_losses=3,
                    action=RiskLevelAction.PAUSE,
                    cooldown_sec=300.0,
                ),
                # 桌別×策略
                RiskLevelConfig(
                    scope=RiskScope.TABLE_STRATEGY,
                    take_profit=500.0,
                    stop_loss=-300.0,
                    max_drawdown_losses=2,
                    action=RiskLevelAction.PAUSE,
                    cooldown_sec=180.0,
                ),
            ]
        )

    @staticmethod
    def balanced() -> RiskTemplate:
        """平衡型風控 - 適度控管"""
        return RiskTemplate(
            key="balanced",
            name="平衡型風控",
            description="平衡風險與收益,適合一般用戶",
            icon="⚖️",
            levels=[
                # 全域單日限制
                RiskLevelConfig(
                    scope=RiskScope.GLOBAL_DAY,
                    take_profit=10000.0,
                    stop_loss=-5000.0,
                    max_drawdown_losses=None,
                    action=RiskLevelAction.STOP_ALL,
                    cooldown_sec=None,
                ),
                # 跨桌×策略
                RiskLevelConfig(
                    scope=RiskScope.ALL_TABLES_STRATEGY,
                    take_profit=2000.0,
                    stop_loss=-1000.0,
                    max_drawdown_losses=5,
                    action=RiskLevelAction.PAUSE,
                    cooldown_sec=600.0,
                ),
            ]
        )

    @staticmethod
    def aggressive() -> RiskTemplate:
        """激進型風控 - 最小限制"""
        return RiskTemplate(
            key="aggressive",
            name="激進型風控",
            description="最小風控限制,追求最大利潤,風險較高",
            icon="🔥",
            levels=[
                # 僅全域限制
                RiskLevelConfig(
                    scope=RiskScope.GLOBAL_DAY,
                    take_profit=20000.0,
                    stop_loss=-10000.0,
                    max_drawdown_losses=None,
                    action=RiskLevelAction.NOTIFY,
                    cooldown_sec=None,
                ),
            ]
        )

    @staticmethod
    def martingale_specific() -> RiskTemplate:
        """馬丁專用風控 - 連輸保護"""
        return RiskTemplate(
            key="martingale_specific",
            name="馬丁專用風控",
            description="針對馬丁策略設計,重點監控連輸次數",
            icon="🎲",
            levels=[
                # 全域單日
                RiskLevelConfig(
                    scope=RiskScope.GLOBAL_DAY,
                    take_profit=8000.0,
                    stop_loss=-4000.0,
                    max_drawdown_losses=None,
                    action=RiskLevelAction.STOP_ALL,
                    cooldown_sec=None,
                ),
                # 桌別×策略 - 重點監控連輸
                RiskLevelConfig(
                    scope=RiskScope.TABLE_STRATEGY,
                    take_profit=None,
                    stop_loss=None,
                    max_drawdown_losses=4,  # 馬丁最怕連輸
                    action=RiskLevelAction.PAUSE,
                    cooldown_sec=600.0,
                ),
                # 單桌
                RiskLevelConfig(
                    scope=RiskScope.TABLE,
                    take_profit=1500.0,
                    stop_loss=-800.0,
                    max_drawdown_losses=None,
                    action=RiskLevelAction.PAUSE,
                    cooldown_sec=300.0,
                ),
            ]
        )

    @staticmethod
    def multi_strategy() -> RiskTemplate:
        """多策略組合風控"""
        return RiskTemplate(
            key="multi_strategy",
            name="多策略組合風控",
            description="適用於同時運行多個策略的場景",
            icon="🎯",
            levels=[
                # 全域
                RiskLevelConfig(
                    scope=RiskScope.GLOBAL_DAY,
                    take_profit=15000.0,
                    stop_loss=-7000.0,
                    max_drawdown_losses=None,
                    action=RiskLevelAction.STOP_ALL,
                    cooldown_sec=None,
                ),
                # 多策略組
                RiskLevelConfig(
                    scope=RiskScope.MULTI_STRATEGY,
                    take_profit=3000.0,
                    stop_loss=-1500.0,
                    max_drawdown_losses=6,
                    action=RiskLevelAction.PAUSE,
                    cooldown_sec=900.0,
                ),
                # 單策略跨桌
                RiskLevelConfig(
                    scope=RiskScope.ALL_TABLES_STRATEGY,
                    take_profit=1000.0,
                    stop_loss=-600.0,
                    max_drawdown_losses=4,
                    action=RiskLevelAction.PAUSE,
                    cooldown_sec=300.0,
                ),
            ]
        )

    @classmethod
    def get_all(cls) -> List[RiskTemplate]:
        """取得所有範本"""
        return [
            cls.conservative(),
            cls.balanced(),
            cls.aggressive(),
            cls.martingale_specific(),
            cls.multi_strategy(),
        ]

    @classmethod
    def get_by_key(cls, key: str) -> RiskTemplate | None:
        """根據 key 取得範本"""
        for template in cls.get_all():
            if template.key == key:
                return template
        return None
