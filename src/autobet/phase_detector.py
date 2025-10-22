# src/autobet/phase_detector.py
"""
階段檢測器 - 基於倒計時模擬

職責：
- 模擬百家樂遊戲的階段轉換（SETTLING → BETTABLE → LOCKED）
- 在適當時機觸發 LineOrchestrator 的階段更新
- 發送階段變化事件給 EngineWorker

未來替換為 T9 API：
- 將計時器替換為 WebSocket 事件監聽器
- 保持相同的接口（on_result_detected, on_phase_change）
"""

import time
import logging
from enum import Enum
from typing import Optional, Callable
from PySide6.QtCore import QTimer, QObject, Signal

logger = logging.getLogger(__name__)


class GamePhase(str, Enum):
    """遊戲階段"""
    IDLE = "idle"              # 空閒（等待結果）
    SETTLING = "settling"      # 結算中（結果剛出現）
    BETTABLE = "bettable"      # 可下注期
    LOCKED = "locked"          # 鎖定期（不可下注）
    RESULTING = "resulting"    # 開獎中


class PhaseDetector(QObject):
    """
    階段檢測器（基於倒計時模擬）

    時間配置（可調整）：
    - SETTLING 期：2 秒（結果顯示、籌碼結算）
    - BETTABLE 期：10 秒（可下注）
    - LOCKED 期：5 秒（發牌、開獎）

    未來替換為 T9 API 時，保持相同的信號接口
    """

    # 信號：階段變化
    phase_changed = Signal(str, str, str, float)  # (table_id, round_id, phase, timestamp)

    # 時間配置（秒）
    SETTLING_DURATION = 2.0    # 結算期（結果後）
    BETTABLE_DURATION = 10.0   # 下注期
    LOCKED_DURATION = 5.0      # 鎖定期

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_phase: GamePhase = GamePhase.IDLE
        self.current_table_id: Optional[str] = None
        self.current_round_id: Optional[str] = None

        # 計時器
        self._settling_timer = QTimer(self)
        self._settling_timer.setSingleShot(True)
        self._settling_timer.timeout.connect(self._on_settling_complete)

        self._bettable_timer = QTimer(self)
        self._bettable_timer.setSingleShot(True)
        self._bettable_timer.timeout.connect(self._on_bettable_complete)

        self._locked_timer = QTimer(self)
        self._locked_timer.setSingleShot(True)
        self._locked_timer.timeout.connect(self._on_locked_complete)

        logger.info("PhaseDetector 初始化完成（倒計時模式）")

    def on_result_detected(self, table_id: str, round_id: str, winner: str):
        """
        結果檢測到時調用

        Args:
            table_id: 桌號（單桌模式下固定為 "main"）
            round_id: 局號
            winner: 贏家（B/P/T）
        """
        logger.info(f"PhaseDetector: 檢測到結果 {winner}，開始階段轉換循環")

        # 停止所有計時器
        self._stop_all_timers()

        # 保存當前信息
        self.current_table_id = table_id
        self.current_round_id = round_id

        # 進入 SETTLING 階段
        self.current_phase = GamePhase.SETTLING
        logger.debug(f"PhaseDetector: 進入 SETTLING 階段 ({self.SETTLING_DURATION}秒)")

        # 啟動 SETTLING 計時器
        self._settling_timer.start(int(self.SETTLING_DURATION * 1000))

    def _on_settling_complete(self):
        """SETTLING 階段完成，進入 BETTABLE 階段"""
        if not self.current_table_id or not self.current_round_id:
            logger.warning("PhaseDetector: SETTLING 完成但缺少桌號/局號信息")
            return

        # 生成下一局的 round_id
        next_round_id = f"{self.current_round_id}_next"

        # 進入 BETTABLE 階段
        self.current_phase = GamePhase.BETTABLE
        timestamp = time.time()

        logger.info(f"PhaseDetector: 進入 BETTABLE 階段 ({self.BETTABLE_DURATION}秒) - round={next_round_id}")

        # 發送階段變化信號
        self.phase_changed.emit(
            self.current_table_id,
            next_round_id,
            GamePhase.BETTABLE.value,
            timestamp
        )

        # 更新 round_id
        self.current_round_id = next_round_id

        # 啟動 BETTABLE 計時器
        self._bettable_timer.start(int(self.BETTABLE_DURATION * 1000))

    def _on_bettable_complete(self):
        """BETTABLE 階段完成，進入 LOCKED 階段"""
        if not self.current_table_id or not self.current_round_id:
            logger.warning("PhaseDetector: BETTABLE 完成但缺少桌號/局號信息")
            return

        # 進入 LOCKED 階段
        self.current_phase = GamePhase.LOCKED
        timestamp = time.time()

        logger.info(f"PhaseDetector: 進入 LOCKED 階段 ({self.LOCKED_DURATION}秒)")

        # 發送階段變化信號
        self.phase_changed.emit(
            self.current_table_id,
            self.current_round_id,
            GamePhase.LOCKED.value,
            timestamp
        )

        # 啟動 LOCKED 計時器
        self._locked_timer.start(int(self.LOCKED_DURATION * 1000))

    def _on_locked_complete(self):
        """LOCKED 階段完成，進入 IDLE（等待下次結果）"""
        logger.debug("PhaseDetector: LOCKED 階段完成，進入 IDLE（等待下次結果）")
        self.current_phase = GamePhase.IDLE
        # 不發送 IDLE 信號，等待下次結果觸發

    def _stop_all_timers(self):
        """停止所有計時器"""
        self._settling_timer.stop()
        self._bettable_timer.stop()
        self._locked_timer.stop()

    def stop(self):
        """停止檢測器"""
        logger.info("PhaseDetector: 停止檢測器")
        self._stop_all_timers()
        self.current_phase = GamePhase.IDLE
        self.current_table_id = None
        self.current_round_id = None

    def get_status(self) -> dict:
        """獲取當前狀態"""
        return {
            "current_phase": self.current_phase.value,
            "table_id": self.current_table_id,
            "round_id": self.current_round_id,
            "settling_active": self._settling_timer.isActive(),
            "bettable_active": self._bettable_timer.isActive(),
            "locked_active": self._locked_timer.isActive(),
        }


# 未來 T9 API 版本的接口（預留）
class T9PhaseDetector(QObject):
    """
    T9 API 階段檢測器（未來實現）

    集成 T9 WebSocket，接收真實的階段事件
    保持與 PhaseDetector 相同的信號接口
    """

    # 相同的信號
    phase_changed = Signal(str, str, str, float)

    def __init__(self, t9_api_url: str, parent=None):
        super().__init__(parent)
        self.t9_api_url = t9_api_url
        # TODO: 實現 WebSocket 連接
        logger.info("T9PhaseDetector 初始化（未實現）")

    def on_result_detected(self, table_id: str, round_id: str, winner: str):
        """與 PhaseDetector 相同的接口"""
        # TODO: 通知 T9 API
        pass

    def stop(self):
        """停止檢測器"""
        # TODO: 關閉 WebSocket 連接
        pass
