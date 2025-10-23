# src/autobet/game_state_manager.py
"""
遊戲狀態管理器 - 統一管理局和階段轉換

職責：
1. 統一生成和管理 round_id
2. 管理遊戲階段轉換（SETTLING → BETTABLE → LOCKED → IDLE）
3. 追蹤參與狀態（用於歷史排除）
4. 發送階段變化和結果確認事件

合併了：
- RoundManager: round_id 生成、參與追蹤
- PhaseDetector: 階段計時和轉換

未來替換為 T9 API：
- 將計時器替換為 WebSocket 事件監聽器
- 保持相同的信號接口
"""

import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict
from PySide6.QtCore import QTimer, QObject, Signal

logger = logging.getLogger(__name__)


class GamePhase(str, Enum):
    """遊戲階段"""
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
    phase: GamePhase           # 當前階段
    created_at: float          # 創建時間
    result_winner: Optional[str] = None  # 結果（B/P/T）
    result_detected_at: Optional[float] = None  # 結果檢測時間
    has_pending_bet: bool = False  # 是否有待處理的下注
    is_participated: bool = False  # 是否參與了這一局（用於排除歷史）


class GameStateManager(QObject):
    """
    遊戲狀態管理器

    統一管理局的生命週期和階段轉換，解決以下問題：
    1. round_id 不一致（PhaseDetector 的 _next vs ResultDetector 的 detect-xxx）
    2. 參與局沒有排除在歷史外
    3. 階段轉換邏輯分散在多個地方

    時間配置（可調整）：
    - SETTLING 期：2 秒（結果顯示、籌碼結算）
    - BETTABLE 期：10 秒（可下注）
    - LOCKED 期：5 秒（發牌、開獎）
    """

    # 信號：階段變化 (table_id, round_id, phase, timestamp)
    phase_changed = Signal(str, str, str, float)

    # 信號：結果確認 (table_id, round_id, winner, timestamp)
    result_confirmed = Signal(str, str, str, float)

    # 時間配置（秒）
    SETTLING_DURATION = 2.0    # 結算期（結果後）
    BETTABLE_DURATION = 10.0   # 下注期
    LOCKED_DURATION = 5.0      # 鎖定期

    def __init__(self, parent=None):
        super().__init__(parent)

        # 當前活躍的局（每個桌一個）
        self.current_rounds: Dict[str, Round] = {}

        # 歷史記錄（最近的局）
        self.round_history: Dict[str, list] = {}  # {table_id: [Round, ...]}

        # 計時器（每個桌一組）
        self._settling_timers: Dict[str, QTimer] = {}
        self._bettable_timers: Dict[str, QTimer] = {}
        self._locked_timers: Dict[str, QTimer] = {}

        logger.info("✅ GameStateManager 初始化完成")

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
        # 停止該桌的所有計時器
        self._stop_table_timers(table_id)

        # 生成新的 round_id
        round_id = f"round-{table_id}-{int(detected_at * 1000)}"

        # 創建新的局
        new_round = Round(
            round_id=round_id,
            table_id=table_id,
            phase=GamePhase.SETTLING,
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

        logger.info(f"🎲 新局創建: {round_id} | 結果: {winner} | 階段: SETTLING")

        # 發送結果確認信號
        self.result_confirmed.emit(table_id, round_id, winner, detected_at)

        # 啟動 SETTLING 計時器
        self._start_settling_timer(table_id)

        return round_id

    def _start_settling_timer(self, table_id: str):
        """啟動 SETTLING 計時器"""
        # 創建或重用計時器
        if table_id not in self._settling_timers:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._on_settling_complete(table_id))
            self._settling_timers[table_id] = timer
        else:
            timer = self._settling_timers[table_id]

        logger.debug(f"GameStateManager: 啟動 SETTLING 計時器 ({self.SETTLING_DURATION}秒) - {table_id}")
        timer.start(int(self.SETTLING_DURATION * 1000))

    def _on_settling_complete(self, table_id: str):
        """SETTLING 階段完成，進入 BETTABLE 階段"""
        current = self.current_rounds.get(table_id)
        if not current:
            logger.warning(f"GameStateManager: SETTLING 完成但桌 {table_id} 沒有當前局")
            return

        if current.phase != GamePhase.SETTLING:
            logger.warning(
                f"GameStateManager: SETTLING 完成但當前階段是 {current.phase}，不是 SETTLING"
            )
            return

        # 更新階段
        current.phase = GamePhase.BETTABLE
        timestamp = time.time()

        logger.info(f"📢 局 {current.round_id} 進入 BETTABLE 階段 ({self.BETTABLE_DURATION}秒)")

        # 發送階段變化信號
        self.phase_changed.emit(table_id, current.round_id, GamePhase.BETTABLE.value, timestamp)

        # 啟動 BETTABLE 計時器
        self._start_bettable_timer(table_id)

    def _start_bettable_timer(self, table_id: str):
        """啟動 BETTABLE 計時器"""
        if table_id not in self._bettable_timers:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._on_bettable_complete(table_id))
            self._bettable_timers[table_id] = timer
        else:
            timer = self._bettable_timers[table_id]

        timer.start(int(self.BETTABLE_DURATION * 1000))

    def _on_bettable_complete(self, table_id: str):
        """BETTABLE 階段完成，進入 LOCKED 階段"""
        current = self.current_rounds.get(table_id)
        if not current:
            logger.warning(f"GameStateManager: BETTABLE 完成但桌 {table_id} 沒有當前局")
            return

        if current.phase != GamePhase.BETTABLE:
            logger.warning(
                f"GameStateManager: BETTABLE 完成但當前階段是 {current.phase}，不是 BETTABLE"
            )
            return

        # 更新階段
        current.phase = GamePhase.LOCKED
        timestamp = time.time()

        logger.info(f"🔒 局 {current.round_id} 進入 LOCKED 階段 ({self.LOCKED_DURATION}秒)")

        # 發送階段變化信號
        self.phase_changed.emit(table_id, current.round_id, GamePhase.LOCKED.value, timestamp)

        # 啟動 LOCKED 計時器
        self._start_locked_timer(table_id)

    def _start_locked_timer(self, table_id: str):
        """啟動 LOCKED 計時器"""
        if table_id not in self._locked_timers:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._on_locked_complete(table_id))
            self._locked_timers[table_id] = timer
        else:
            timer = self._locked_timers[table_id]

        timer.start(int(self.LOCKED_DURATION * 1000))

    def _on_locked_complete(self, table_id: str):
        """LOCKED 階段完成，進入 IDLE（等待下次結果）"""
        current = self.current_rounds.get(table_id)
        if not current:
            logger.debug(f"GameStateManager: LOCKED 完成但桌 {table_id} 沒有當前局")
            return

        # 更新階段
        current.phase = GamePhase.IDLE
        logger.debug(f"GameStateManager: 局 {current.round_id} 進入 IDLE（等待下次結果）")
        # 不發送 IDLE 信號，等待下次結果觸發

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
                f"⚠️ 無法標記下注：局 {round_id} 不是當前局（當前局: {current.round_id if current else 'None'}）"
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

    def get_status(self, table_id: str = None) -> Dict:
        """
        獲取狀態信息（用於調試）

        Args:
            table_id: 桌號，如果為 None 則返回所有桌的狀態
        """
        if table_id is None:
            # 返回所有桌的狀態
            return {
                tid: self.get_status(tid)
                for tid in self.current_rounds.keys()
            }

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
            "timers": {
                "settling_active": self._settling_timers.get(table_id, QTimer()).isActive(),
                "bettable_active": self._bettable_timers.get(table_id, QTimer()).isActive(),
                "locked_active": self._locked_timers.get(table_id, QTimer()).isActive(),
            }
        }

    def _stop_table_timers(self, table_id: str):
        """停止指定桌的所有計時器"""
        if table_id in self._settling_timers:
            self._settling_timers[table_id].stop()
        if table_id in self._bettable_timers:
            self._bettable_timers[table_id].stop()
        if table_id in self._locked_timers:
            self._locked_timers[table_id].stop()

    def _stop_all_timers(self):
        """停止所有計時器"""
        for timer in self._settling_timers.values():
            timer.stop()
        for timer in self._bettable_timers.values():
            timer.stop()
        for timer in self._locked_timers.values():
            timer.stop()

    def stop(self):
        """停止管理器"""
        logger.info("🛑 GameStateManager 停止")
        self._stop_all_timers()
        self.current_rounds.clear()
        self.round_history.clear()


# 未來 T9 API 版本的接口（預留）
class T9GameStateManager(QObject):
    """
    T9 API 遊戲狀態管理器（未來實現）

    集成 T9 WebSocket，接收真實的階段事件
    保持與 GameStateManager 相同的信號接口
    """

    # 相同的信號
    phase_changed = Signal(str, str, str, float)
    result_confirmed = Signal(str, str, str, float)

    def __init__(self, t9_api_url: str, parent=None):
        super().__init__(parent)
        self.t9_api_url = t9_api_url
        # TODO: 實現 WebSocket 連接
        logger.info("T9GameStateManager 初始化（未實現）")

    def on_result_detected(self, table_id: str, winner: str, detected_at: float) -> str:
        """與 GameStateManager 相同的接口"""
        # TODO: 通知 T9 API
        pass

    def stop(self):
        """停止管理器"""
        # TODO: 關閉 WebSocket 連接
        pass
