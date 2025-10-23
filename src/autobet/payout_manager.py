# src/autobet/payout_manager.py
"""
賠率管理器
負責載入和管理百家樂賠率配置
"""

import json
from pathlib import Path
from typing import Dict, Optional


class PayoutManager:
    """百家樂賠率管理器"""

    DEFAULT_RATES = {
        "banker": 0.95,  # 莊家 1:0.95
        "player": 1.0,   # 閒家 1:1
        "tie": 8.0,      # 和局 1:8
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化賠率管理器

        Args:
            config_path: 配置文件路徑 (預設: configs/payout_rates.json)
        """
        self.config_path = Path(config_path) if config_path else Path("configs/payout_rates.json")
        self.rates = self.DEFAULT_RATES.copy()
        self._load_config()

    def _load_config(self) -> None:
        """載入賠率配置"""
        if not self.config_path.exists():
            # 配置文件不存在，使用預設值並創建
            self._create_default_config()
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                rates_config = config.get("rates", {})

                # 更新賠率
                if "banker" in rates_config:
                    self.rates["banker"] = float(rates_config["banker"].get("win", 0.95))
                if "player" in rates_config:
                    self.rates["player"] = float(rates_config["player"].get("win", 1.0))
                if "tie" in rates_config:
                    self.rates["tie"] = float(rates_config["tie"].get("win", 8.0))

        except Exception as e:
            print(f"⚠️ 賠率配置載入失敗: {e}，使用預設值")

    def _create_default_config(self) -> None:
        """創建預設配置文件"""
        default_config = {
            "description": "百家樂賠率設定 (可根據不同賭場規則調整)",
            "rates": {
                "banker": {
                    "win": 0.95,
                    "description": "莊家贏 1:0.95 (扣除5%佣金)"
                },
                "player": {
                    "win": 1.0,
                    "description": "閒家贏 1:1"
                },
                "tie": {
                    "win": 8.0,
                    "description": "和局贏 1:8 (部分賭場是 1:9)"
                }
            },
            "skip_rules": {
                "banker_tie": {
                    "payout": 0.0,
                    "description": "押莊遇和局，退回本金"
                },
                "player_tie": {
                    "payout": 0.0,
                    "description": "押閒遇和局，退回本金"
                }
            }
        }

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            print(f"✅ 已創建預設賠率配置: {self.config_path}")
        except Exception as e:
            print(f"❌ 創建賠率配置失敗: {e}")

    def get_win_payout(self, direction: str) -> float:
        """
        獲取獲勝賠率

        Args:
            direction: "banker" | "player" | "tie" | "B" | "P" | "T"

        Returns:
            賠率 (例: 0.95 表示贏1元實得0.95元)
        """
        direction_map = {
            "B": "banker",
            "P": "player",
            "T": "tie",
            "BANKER": "banker",
            "PLAYER": "player",
            "TIE": "tie",
        }

        normalized = direction_map.get(direction.upper(), direction.lower())
        return self.rates.get(normalized, 1.0)

    def calculate_pnl(self, amount: float, outcome: str, direction: str) -> float:
        """
        計算盈虧金額

        Args:
            amount: 下注金額
            outcome: "WIN" | "LOSS" | "SKIPPED" | "CANCELLED"
            direction: "banker" | "player" | "tie"

        Returns:
            盈虧金額 (正數=盈利, 負數=虧損, 0=退回)
        """
        outcome_upper = outcome.upper()

        if outcome_upper == "WIN":
            payout_rate = self.get_win_payout(direction)
            return float(amount * payout_rate)

        elif outcome_upper == "LOSS":
            return float(-amount)

        elif outcome_upper in ("SKIPPED", "CANCELLED"):
            # 和局跳過 或 取消局，退回本金
            return 0.0

        return 0.0

    def get_rates_summary(self) -> Dict[str, float]:
        """獲取賠率摘要 (用於 UI 顯示)"""
        return {
            "莊家": self.rates["banker"],
            "閒家": self.rates["player"],
            "和局": self.rates["tie"],
        }

    def update_rate(self, direction: str, rate: float) -> bool:
        """
        更新賠率 (並保存到配置文件)

        Args:
            direction: "banker" | "player" | "tie"
            rate: 新賠率

        Returns:
            是否成功
        """
        if direction.lower() not in self.rates:
            return False

        self.rates[direction.lower()] = float(rate)

        # 保存到配置文件
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            else:
                config = {"rates": {}}

            config["rates"][direction.lower()] = {
                "win": float(rate),
                "description": f"{direction} 更新於用戶設定"
            }

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            return True

        except Exception as e:
            print(f"❌ 保存賠率配置失敗: {e}")
            return False
