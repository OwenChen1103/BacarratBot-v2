# src/autobet/round_manager.py
"""
Round 管理器 - 統一管理局號和階段轉換

職責：
1. 統一生成和管理 round_id
2. 追蹤當前局的狀態和階段
3. 協調 PhaseDetector 和 ResultDetector
4. 管理倉位生命週期
"""

import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Callable
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class RoundPhase(str, Enum):
    """局的階段"""
    IDLE = "idle"              # 空閒（等待結果）
    SETTLING = "settling"      # 結算中（結果剛出現）
    BETTABLE = "bettable"      # 可下注期
    LOCKED = "locked"          # 鎖定期（不可下注）
    RESULTING = "resulting"    # 開獎中


@dataclass
class Round:
    """局信息"""
    round_id: str              # 局號
    table_id: str              # 桌號
    phase: RoundPhase          # 當前階段
    created_at: float          # 創建時間
    result_winner: Optional[str] = None  # 結果（B/P/T）
    result_detected_at: Optional[float] = None  # 結果檢測時間
    has_pending_bet: bool = False  # 是否有待處理的下注
    is_participated: bool = False  # 是否參與了這一局（用於排除歷史）


class RoundManager(QObject):
    """
    Round 管理器

    統一管理局號和階段轉換，解決以下問題：
    1. round_id 不一致（PhaseDetector 的 _next vs ResultDetector 的 detect-xxx）
    2. 參與局沒有排除在歷史外
    3. 倉位追蹤分散在多個地方
    """

    # 信號：階段變化 (table_id, round_id, phase, timestamp)
    phase_changed = Signal(str, str, str, float)

    # 信號：結果確認 (table_id, round_id, winner, timestamp)
    result_confirmed = Signal(str, str, str, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        # 當前活躍的局（每個桌一個）
        self.current_rounds: Dict[str, Round] = {}

        # 歷史記錄（最近的局）
        self.round_history: Dict[str, list] = {}  # {table_id: [Round, ...]}

        logger.info("✅ RoundManager 初始化完成")

    def on_result_detected(self, table_id: str, winner: str, detected_at: float) -> str:
        """
        當檢測到結果時調用

        Args:
            table_id: 桌號
            winner: 贏家（B/P/T）
            detected_at: 檢測時間

        Returns:
            round_id: 這一局的 ID
        """
        # 生成新的 round_id
        round_id = f"round-{table_id}-{int(detected_at * 1000)}"

        # 創建新的局
        new_round = Round(
            round_id=round_id,
            table_id=table_id,
            phase=RoundPhase.SETTLING,
            created_at=detected_at,
            result_winner=winner,
            result_detected_at=detected_at
        )

        # 保存到當前局
        old_round = self.current_rounds.get(table_id)
        self.current_rounds[table_id] = new_round

        # 如果有舊局，檢查是否有未結算的倉位
        if old_round and old_round.has_pending_bet:
            logger.warning(
                f"⚠️ 檢測到新結果，但上一局 {old_round.round_id} 還有未結算的倉位！"
                f"這可能是檢測器漏檢了一局。"
            )

        # 添加到歷史
        if table_id not in self.round_history:
            self.round_history[table_id] = []
        self.round_history[table_id].append(new_round)

        # 只保留最近 100 局
        if len(self.round_history[table_id]) > 100:
            self.round_history[table_id] = self.round_history[table_id][-100:]

        logger.info(f"🎲 新局創建: {round_id} | 結果: {winner}")

        # 發送結果確認信號
        self.result_confirmed.emit(table_id, round_id, winner, detected_at)

        return round_id

    def transition_to_bettable(self, table_id: str) -> Optional[str]:
        """
        轉換到 BETTABLE 階段

        Returns:
            round_id: 可下注的局 ID，如果沒有則返回 None
        """
        current = self.current_rounds.get(table_id)
        if not current:
            logger.warning(f"⚠️ 無法轉換到 BETTABLE：桌 {table_id} 沒有當前局")
            return None

        if current.phase != RoundPhase.SETTLING:
            logger.warning(
                f"⚠️ 無法轉換到 BETTABLE：當前階段是 {current.phase}，不是 SETTLING"
            )
            return None

        # 更新階段
        current.phase = RoundPhase.BETTABLE
        timestamp = time.time()

        logger.info(f"📢 局 {current.round_id} 進入 BETTABLE 階段")

        # 發送階段變化信號
        self.phase_changed.emit(table_id, current.round_id, RoundPhase.BETTABLE.value, timestamp)

        return current.round_id

    def transition_to_locked(self, table_id: str) -> Optional[str]:
        """
        轉換到 LOCKED 階段

        Returns:
            round_id: 鎖定的局 ID
        """
        current = self.current_rounds.get(table_id)
        if not current:
            logger.warning(f"⚠️ 無法轉換到 LOCKED：桌 {table_id} 沒有當前局")
            return None

        if current.phase != RoundPhase.BETTABLE:
            logger.warning(
                f"⚠️ 無法轉換到 LOCKED：當前階段是 {current.phase}，不是 BETTABLE"
            )
            return None

        # 更新階段
        current.phase = RoundPhase.LOCKED
        timestamp = time.time()

        logger.info(f"🔒 局 {current.round_id} 進入 LOCKED 階段")

        # 發送階段變化信號
        self.phase_changed.emit(table_id, current.round_id, RoundPhase.LOCKED.value, timestamp)

        return current.round_id

    def mark_bet_placed(self, table_id: str, round_id: str):
        """
        標記某局已下注

        Args:
            table_id: 桌號
            round_id: 局號
        """
        current = self.current_rounds.get(table_id)
        if not current or current.round_id != round_id:
            logger.warning(
                f"⚠️ 無法標記下注：局 {round_id} 不是當前局"
            )
            return

        current.has_pending_bet = True
        current.is_participated = True

        logger.info(f"💰 局 {round_id} 已標記為參與局（有下注）")

    def mark_bet_settled(self, table_id: str, round_id: str):
        """
        標記某局的下注已結算

        Args:
            table_id: 桌號
            round_id: 局號
        """
        # 在歷史中查找（因為結算時可能已經是下一局了）
        if table_id not in self.round_history:
            logger.warning(f"⚠️ 無法標記結算：桌 {table_id} 沒有歷史記錄")
            return

        for round_obj in reversed(self.round_history[table_id]):
            if round_obj.round_id == round_id:
                round_obj.has_pending_bet = False
                logger.info(f"✅ 局 {round_id} 的下注已結算")
                return

        logger.warning(f"⚠️ 無法標記結算：找不到局 {round_id}")

    def should_include_in_history(self, table_id: str, round_id: str) -> bool:
        """
        判斷某局是否應該計入策略歷史

        規則：參與的局（is_participated=True）不計入歷史

        Args:
            table_id: 桌號
            round_id: 局號

        Returns:
            是否應該計入歷史
        """
        # 檢查當前局
        current = self.current_rounds.get(table_id)
        if current and current.round_id == round_id:
            return not current.is_participated

        # 檢查歷史
        if table_id in self.round_history:
            for round_obj in reversed(self.round_history[table_id]):
                if round_obj.round_id == round_id:
                    return not round_obj.is_participated

        # 找不到，默認計入歷史
        return True

    def get_current_round(self, table_id: str) -> Optional[Round]:
        """獲取當前局"""
        return self.current_rounds.get(table_id)

    def get_round(self, table_id: str, round_id: str) -> Optional[Round]:
        """獲取指定局"""
        # 先檢查當前局
        current = self.current_rounds.get(table_id)
        if current and current.round_id == round_id:
            return current

        # 再檢查歷史
        if table_id in self.round_history:
            for round_obj in reversed(self.round_history[table_id]):
                if round_obj.round_id == round_id:
                    return round_obj

        return None

    def get_status(self, table_id: str) -> Dict:
        """獲取狀態信息（用於調試）"""
        current = self.current_rounds.get(table_id)
        if not current:
            return {"status": "no_current_round"}

        return {
            "round_id": current.round_id,
            "phase": current.phase.value,
            "result_winner": current.result_winner,
            "has_pending_bet": current.has_pending_bet,
            "is_participated": current.is_participated,
            "created_at": current.created_at,
        }

    def stop(self):
        """停止管理器"""
        logger.info("🛑 RoundManager 停止")
        self.current_rounds.clear()
        self.round_history.clear()
