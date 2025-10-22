# src/autobet/strategy_templates.py
"""
策略範本庫 - 預設策略範本定義
"""
from __future__ import annotations

from typing import Dict
from dataclasses import dataclass

from .lines.config import (
    StrategyDefinition,
    EntryConfig,
    StakingConfig,
    CrossTableLayerConfig,
    CrossTableMode,
    StrategyRiskConfig,
    RiskLevelConfig,
    RiskScope,
    RiskLevelAction,
    AdvanceRule,
    DedupMode,
    StackPolicy,
)


@dataclass
class StrategyTemplate:
    """策略範本"""
    key: str
    name: str
    description: str
    icon: str
    difficulty: str  # "新手" | "進階" | "專家"
    definition: StrategyDefinition


class StrategyTemplateLibrary:
    """預設策略範本庫"""

    @staticmethod
    def get_all_templates() -> Dict[str, StrategyTemplate]:
        """取得所有範本"""
        return {
            "classic_martingale": StrategyTemplateLibrary.classic_martingale(),
            "anti_martingale": StrategyTemplateLibrary.anti_martingale(),
            "fixed_bet": StrategyTemplateLibrary.fixed_bet(),
            "fibonacci": StrategyTemplateLibrary.fibonacci(),
            "trend_follow": StrategyTemplateLibrary.trend_follow(),
            "two_player_bet_banker": StrategyTemplateLibrary.two_player_bet_banker(),
        }

    @staticmethod
    def classic_martingale() -> StrategyTemplate:
        """經典馬丁 - 兩莊後押閒,輸加倍"""
        return StrategyTemplate(
            key="classic_martingale",
            name="經典馬丁",
            description="兩莊後押閒,輸了加倍,贏了重置",
            icon="📈",
            difficulty="新手",
            definition=StrategyDefinition(
                strategy_key="classic_martingale",
                entry=EntryConfig(
                    pattern="BB then bet P",
                    valid_window_sec=0.0,
                    dedup=DedupMode.OVERLAP,
                    first_trigger_layer=1
                ),
                staking=StakingConfig(
                    sequence=[100, 200, 400, 800, 1600, 3200, 6400],
                    advance_on=AdvanceRule.LOSS,  # 輸進下一層
                    reset_on_win=True,  # 贏重置
                    reset_on_loss=False,
                    max_layers=7,
                    per_hand_cap=None,
                    stack_policy=StackPolicy.NONE
                ),
                cross_table_layer=CrossTableLayerConfig(
                    scope="strategy_key",
                    mode=CrossTableMode.RESET  # 每桌獨立
                ),
                risk=StrategyRiskConfig(
                    levels=[
                        RiskLevelConfig(
                            scope=RiskScope.TABLE,
                            take_profit=1000.0,
                            stop_loss=-500.0,
                            max_drawdown_losses=5,
                            action=RiskLevelAction.PAUSE,
                            cooldown_sec=300.0
                        )
                    ]
                ),
                metadata={
                    "template": "classic_martingale",
                    "created_from_template": True
                }
            )
        )

    @staticmethod
    def anti_martingale() -> StrategyTemplate:
        """反馬丁 - 贏加碼輸回歸"""
        return StrategyTemplate(
            key="anti_martingale",
            name="反馬丁",
            description="贏了加碼,輸了重置 (保護利潤)",
            icon="📉",
            difficulty="進階",
            definition=StrategyDefinition(
                strategy_key="anti_martingale",
                entry=EntryConfig(
                    pattern="BB then bet P",
                    valid_window_sec=0.0,
                    dedup=DedupMode.OVERLAP,
                    first_trigger_layer=1
                ),
                staking=StakingConfig(
                    sequence=[100, 200, 400, 800],
                    advance_on=AdvanceRule.WIN,  # 贏進下一層
                    reset_on_win=False,
                    reset_on_loss=True,  # 輸重置
                    max_layers=4,
                    per_hand_cap=None,
                    stack_policy=StackPolicy.NONE
                ),
                cross_table_layer=CrossTableLayerConfig(
                    scope="strategy_key",
                    mode=CrossTableMode.RESET
                ),
                risk=StrategyRiskConfig(
                    levels=[
                        RiskLevelConfig(
                            scope=RiskScope.TABLE,
                            take_profit=1500.0,
                            stop_loss=-300.0,
                            max_drawdown_losses=3,
                            action=RiskLevelAction.PAUSE,
                            cooldown_sec=300.0
                        )
                    ]
                ),
                metadata={"template": "anti_martingale"}
            )
        )

    @staticmethod
    def fixed_bet() -> StrategyTemplate:
        """固定注碼 - 最保守"""
        return StrategyTemplate(
            key="fixed_bet",
            name="固定注碼",
            description="每手固定金額,不加碼 (最保守)",
            icon="💰",
            difficulty="新手",
            definition=StrategyDefinition(
                strategy_key="fixed_bet",
                entry=EntryConfig(
                    pattern="BB then bet P",
                    valid_window_sec=0.0,
                    dedup=DedupMode.OVERLAP,
                    first_trigger_layer=1
                ),
                staking=StakingConfig(
                    sequence=[100],  # 固定 100
                    advance_on=AdvanceRule.LOSS,
                    reset_on_win=False,
                    reset_on_loss=False,
                    max_layers=1,
                    per_hand_cap=None,
                    stack_policy=StackPolicy.NONE
                ),
                cross_table_layer=CrossTableLayerConfig(
                    scope="strategy_key",
                    mode=CrossTableMode.RESET
                ),
                risk=StrategyRiskConfig(
                    levels=[
                        RiskLevelConfig(
                            scope=RiskScope.TABLE,
                            take_profit=500.0,
                            stop_loss=-300.0,
                            max_drawdown_losses=10,
                            action=RiskLevelAction.PAUSE,
                            cooldown_sec=300.0
                        )
                    ]
                ),
                metadata={"template": "fixed_bet"}
            )
        )

    @staticmethod
    def fibonacci() -> StrategyTemplate:
        """費波那契數列"""
        return StrategyTemplate(
            key="fibonacci",
            name="費波那契",
            description="按費氏數列遞增 (1,1,2,3,5,8...)",
            icon="🔢",
            difficulty="進階",
            definition=StrategyDefinition(
                strategy_key="fibonacci",
                entry=EntryConfig(
                    pattern="BB then bet P",
                    valid_window_sec=0.0,
                    dedup=DedupMode.OVERLAP,
                    first_trigger_layer=1
                ),
                staking=StakingConfig(
                    sequence=[100, 100, 200, 300, 500, 800, 1300],
                    advance_on=AdvanceRule.LOSS,
                    reset_on_win=True,
                    reset_on_loss=False,
                    max_layers=7,
                    per_hand_cap=None,
                    stack_policy=StackPolicy.NONE
                ),
                cross_table_layer=CrossTableLayerConfig(
                    scope="strategy_key",
                    mode=CrossTableMode.RESET
                ),
                risk=StrategyRiskConfig(
                    levels=[
                        RiskLevelConfig(
                            scope=RiskScope.TABLE,
                            take_profit=800.0,
                            stop_loss=-600.0,
                            max_drawdown_losses=6,
                            action=RiskLevelAction.PAUSE,
                            cooldown_sec=300.0
                        )
                    ]
                ),
                metadata={"template": "fibonacci"}
            )
        )

    @staticmethod
    def trend_follow() -> StrategyTemplate:
        """追長龍 - 兩莊後繼續押莊"""
        return StrategyTemplate(
            key="trend_follow",
            name="追長龍",
            description="兩莊後繼續押莊,順勢而為",
            icon="🐉",
            difficulty="進階",
            definition=StrategyDefinition(
                strategy_key="trend_follow",
                entry=EntryConfig(
                    pattern="BB then bet B",  # 兩莊後繼續押莊
                    valid_window_sec=0.0,
                    dedup=DedupMode.OVERLAP,
                    first_trigger_layer=1
                ),
                staking=StakingConfig(
                    sequence=[100, 150, 225, 340, 510],
                    advance_on=AdvanceRule.WIN,  # 贏了加碼
                    reset_on_win=False,
                    reset_on_loss=True,  # 輸了回歸
                    max_layers=5,
                    per_hand_cap=None,
                    stack_policy=StackPolicy.NONE
                ),
                cross_table_layer=CrossTableLayerConfig(
                    scope="strategy_key",
                    mode=CrossTableMode.RESET
                ),
                risk=StrategyRiskConfig(
                    levels=[
                        RiskLevelConfig(
                            scope=RiskScope.TABLE,
                            take_profit=1000.0,
                            stop_loss=-400.0,
                            max_drawdown_losses=3,
                            action=RiskLevelAction.PAUSE,
                            cooldown_sec=300.0
                        )
                    ]
                ),
                metadata={"template": "trend_follow"}
            )
        )

    @staticmethod
    def two_player_bet_banker() -> StrategyTemplate:
        """兩閒押莊 - 切龍策略"""
        return StrategyTemplate(
            key="two_player_bet_banker",
            name="兩閒押莊",
            description="看到兩閒就押莊,切斷閒龍",
            icon="✂️",
            difficulty="新手",
            definition=StrategyDefinition(
                strategy_key="two_player_bet_banker",
                entry=EntryConfig(
                    pattern="PP then bet B",
                    valid_window_sec=0.0,
                    dedup=DedupMode.OVERLAP,
                    first_trigger_layer=1
                ),
                staking=StakingConfig(
                    sequence=[100, 200, 400],
                    advance_on=AdvanceRule.LOSS,
                    reset_on_win=True,
                    reset_on_loss=False,
                    max_layers=3,
                    per_hand_cap=None,
                    stack_policy=StackPolicy.NONE
                ),
                cross_table_layer=CrossTableLayerConfig(
                    scope="strategy_key",
                    mode=CrossTableMode.RESET
                ),
                risk=StrategyRiskConfig(
                    levels=[
                        RiskLevelConfig(
                            scope=RiskScope.TABLE,
                            take_profit=600.0,
                            stop_loss=-300.0,
                            max_drawdown_losses=4,
                            action=RiskLevelAction.PAUSE,
                            cooldown_sec=180.0
                        )
                    ]
                ),
                metadata={"template": "two_player_bet_banker"}
            )
        )
