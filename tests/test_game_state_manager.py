# tests/test_game_state_manager.py
"""
GameStateManager 單元測試

測試範圍：
1. 基礎功能：round_id 生成、階段轉換
2. 參與狀態追蹤：mark_bet_placed, should_include_in_history
3. 計時器管理：自動階段轉換
4. 多桌支持：獨立的計時器和狀態
5. 錯誤處理：邊界情況和異常
"""

import time
import pytest
from PySide6.QtCore import QCoreApplication, QTimer
from src.autobet.game_state_manager import GameStateManager, GamePhase, Round


@pytest.fixture
def qapp():
    """創建 Qt 應用程序（測試 QTimer 需要）"""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def manager(qapp):
    """創建 GameStateManager 實例"""
    mgr = GameStateManager()
    # 縮短計時器時間以加快測試速度
    mgr.SETTLING_DURATION = 0.05  # 50ms
    mgr.BETTABLE_DURATION = 0.05  # 50ms
    mgr.LOCKED_DURATION = 0.05    # 50ms
    yield mgr
    mgr.stop()


def process_events(qapp, timeout_ms=100):
    """處理 Qt 事件循環（等待計時器觸發）"""
    QTimer.singleShot(timeout_ms, qapp.quit)
    qapp.exec()


class TestBasicFunctionality:
    """測試基礎功能"""

    def test_initialization(self, manager):
        """測試初始化"""
        assert manager.current_rounds == {}
        assert manager.round_history == {}
        assert manager.SETTLING_DURATION == 0.05
        assert manager.BETTABLE_DURATION == 0.05
        assert manager.LOCKED_DURATION == 0.05

    def test_on_result_detected_creates_round(self, manager):
        """測試 on_result_detected 創建新局"""
        timestamp = time.time()
        round_id = manager.on_result_detected("table1", "B", timestamp)

        # 驗證 round_id 格式
        assert round_id.startswith("round-table1-")
        assert len(round_id) > len("round-table1-")

        # 驗證當前局
        current = manager.get_current_round("table1")
        assert current is not None
        assert current.round_id == round_id
        assert current.table_id == "table1"
        assert current.phase == GamePhase.SETTLING
        assert current.result_winner == "B"
        assert current.is_participated is False
        assert current.has_pending_bet is False

        # 驗證歷史
        assert "table1" in manager.round_history
        assert len(manager.round_history["table1"]) == 1
        assert manager.round_history["table1"][0].round_id == round_id

    def test_round_id_format(self, manager):
        """測試 round_id 格式一致性"""
        timestamp = time.time()
        round_id = manager.on_result_detected("table1", "P", timestamp)

        # 格式：round-{table_id}-{timestamp_ms}
        expected_timestamp_ms = int(timestamp * 1000)
        assert round_id == f"round-table1-{expected_timestamp_ms}"

    def test_multiple_results_same_table(self, manager):
        """測試同一桌多次結果"""
        round1 = manager.on_result_detected("table1", "B", time.time())
        time.sleep(0.01)
        round2 = manager.on_result_detected("table1", "P", time.time())

        # 驗證兩局不同
        assert round1 != round2

        # 驗證當前局是最新的
        current = manager.get_current_round("table1")
        assert current.round_id == round2
        assert current.result_winner == "P"

        # 驗證歷史包含兩局
        assert len(manager.round_history["table1"]) == 2

    def test_multiple_tables(self, manager):
        """測試多桌支持"""
        round_t1 = manager.on_result_detected("table1", "B", time.time())
        round_t2 = manager.on_result_detected("table2", "P", time.time())

        # 驗證兩桌獨立
        assert round_t1 != round_t2

        current_t1 = manager.get_current_round("table1")
        current_t2 = manager.get_current_round("table2")

        assert current_t1.round_id == round_t1
        assert current_t2.round_id == round_t2
        assert current_t1.result_winner == "B"
        assert current_t2.result_winner == "P"


class TestPhaseTransitions:
    """測試階段轉換"""

    def test_phase_transition_settling_to_bettable(self, manager, qapp):
        """測試 SETTLING → BETTABLE 自動轉換"""
        # 記錄信號
        phase_signals = []
        manager.phase_changed.connect(
            lambda tid, rid, phase, ts: phase_signals.append((tid, rid, phase))
        )

        # 觸發結果
        round_id = manager.on_result_detected("table1", "B", time.time())

        # 驗證初始階段
        current = manager.get_current_round("table1")
        assert current.phase == GamePhase.SETTLING

        # 等待 SETTLING 計時器觸發
        process_events(qapp, timeout_ms=100)

        # 驗證轉換到 BETTABLE
        current = manager.get_current_round("table1")
        assert current.phase == GamePhase.BETTABLE

        # 驗證信號發送
        assert len(phase_signals) >= 1
        assert phase_signals[0] == ("table1", round_id, "bettable")

    def test_phase_transition_bettable_to_locked(self, manager, qapp):
        """測試 BETTABLE → LOCKED 自動轉換"""
        phase_signals = []
        manager.phase_changed.connect(
            lambda tid, rid, phase, ts: phase_signals.append((tid, rid, phase))
        )

        round_id = manager.on_result_detected("table1", "B", time.time())

        # 等待 SETTLING → BETTABLE
        process_events(qapp, timeout_ms=100)

        # 清空之前的信號
        phase_signals.clear()

        # 等待 BETTABLE → LOCKED（縮短等待時間避免進入 IDLE）
        process_events(qapp, timeout_ms=70)

        # 驗證轉換到 LOCKED 或 IDLE（因為計時器可能已執行完）
        current = manager.get_current_round("table1")
        assert current.phase in (GamePhase.LOCKED, GamePhase.IDLE)

        # 驗證信號發送（至少收到 locked 信號）
        assert len(phase_signals) >= 1
        locked_signals = [sig for sig in phase_signals if sig[2] == "locked"]
        assert len(locked_signals) >= 1
        assert locked_signals[0] == ("table1", round_id, "locked")

    def test_phase_transition_locked_to_idle(self, manager, qapp):
        """測試 LOCKED → IDLE 自動轉換"""
        round_id = manager.on_result_detected("table1", "B", time.time())

        # 等待所有階段轉換完成
        # SETTLING (50ms) + BETTABLE (50ms) + LOCKED (50ms) = 150ms
        process_events(qapp, timeout_ms=200)

        # 驗證進入 IDLE
        current = manager.get_current_round("table1")
        assert current.phase == GamePhase.IDLE

    def test_complete_phase_cycle(self, manager, qapp):
        """測試完整階段循環"""
        phase_history = []
        manager.phase_changed.connect(
            lambda tid, rid, phase, ts: phase_history.append(phase)
        )

        # 觸發第一個結果
        manager.on_result_detected("table1", "B", time.time())

        # 等待完整循環
        process_events(qapp, timeout_ms=200)

        # 驗證階段順序：SETTLING → BETTABLE → LOCKED → IDLE
        # 注意：SETTLING 和 IDLE 不發送信號
        assert len(phase_history) >= 2
        assert phase_history[0] == "bettable"
        assert phase_history[1] == "locked"


class TestParticipationTracking:
    """測試參與狀態追蹤"""

    def test_mark_bet_placed(self, manager):
        """測試標記下注"""
        round_id = manager.on_result_detected("table1", "B", time.time())

        # 驗證初始狀態
        current = manager.get_current_round("table1")
        assert current.is_participated is False
        assert current.has_pending_bet is False

        # 標記下注
        manager.mark_bet_placed("table1", round_id)

        # 驗證狀態更新
        current = manager.get_current_round("table1")
        assert current.is_participated is True
        assert current.has_pending_bet is True

    def test_mark_bet_settled(self, manager):
        """測試標記結算"""
        round_id = manager.on_result_detected("table1", "B", time.time())
        manager.mark_bet_placed("table1", round_id)

        # 創建新局（這樣舊局進入歷史）
        time.sleep(0.01)
        round_id2 = manager.on_result_detected("table1", "P", time.time())

        # 結算舊局
        manager.mark_bet_settled("table1", round_id)

        # 驗證歷史中的舊局已標記為已結算
        old_round = manager.get_round("table1", round_id)
        assert old_round.has_pending_bet is False
        assert old_round.is_participated is True  # is_participated 不會改變

    def test_should_include_in_history_observation_round(self, manager):
        """測試觀察局應計入歷史"""
        round_id = manager.on_result_detected("table1", "B", time.time())

        # 未下注的局應計入歷史
        assert manager.should_include_in_history("table1", round_id) is True

    def test_should_include_in_history_participation_round(self, manager):
        """測試參與局不計入歷史"""
        round_id = manager.on_result_detected("table1", "B", time.time())
        manager.mark_bet_placed("table1", round_id)

        # 已下注的局不應計入歷史
        assert manager.should_include_in_history("table1", round_id) is False

    def test_should_include_in_history_unknown_round(self, manager):
        """測試未知局默認計入歷史"""
        # 不存在的局默認計入歷史
        assert manager.should_include_in_history("table1", "unknown_round") is True


class TestMultiTableSupport:
    """測試多桌支持"""

    def test_independent_phases(self, manager, qapp):
        """測試多桌獨立階段"""
        # 兩桌同時開始
        round_t1 = manager.on_result_detected("table1", "B", time.time())
        round_t2 = manager.on_result_detected("table2", "P", time.time())

        # 驗證初始階段
        assert manager.get_current_round("table1").phase == GamePhase.SETTLING
        assert manager.get_current_round("table2").phase == GamePhase.SETTLING

        # 等待轉換
        process_events(qapp, timeout_ms=100)

        # 驗證兩桌都轉換到 BETTABLE
        assert manager.get_current_round("table1").phase == GamePhase.BETTABLE
        assert manager.get_current_round("table2").phase == GamePhase.BETTABLE

    def test_independent_timers(self, manager, qapp):
        """測試多桌獨立計時器"""
        phase_signals = []
        manager.phase_changed.connect(
            lambda tid, rid, phase, ts: phase_signals.append((tid, phase))
        )

        # 錯開時間啟動兩桌
        round_t1 = manager.on_result_detected("table1", "B", time.time())
        time.sleep(0.03)  # 30ms 延遲
        round_t2 = manager.on_result_detected("table2", "P", time.time())

        # 等待兩桌都完成 SETTLING
        process_events(qapp, timeout_ms=150)

        # 驗證兩桌都發送了 phase_changed 信號
        table1_signals = [sig for sig in phase_signals if sig[0] == "table1"]
        table2_signals = [sig for sig in phase_signals if sig[0] == "table2"]

        assert len(table1_signals) >= 1
        assert len(table2_signals) >= 1

    def test_independent_participation_tracking(self, manager):
        """測試多桌獨立參與追蹤"""
        round_t1 = manager.on_result_detected("table1", "B", time.time())
        round_t2 = manager.on_result_detected("table2", "P", time.time())

        # 只在 table1 下注
        manager.mark_bet_placed("table1", round_t1)

        # 驗證 table1 參與，table2 未參與
        assert manager.should_include_in_history("table1", round_t1) is False
        assert manager.should_include_in_history("table2", round_t2) is True


class TestRoundQueries:
    """測試局查詢功能"""

    def test_get_current_round(self, manager):
        """測試獲取當前局"""
        round_id = manager.on_result_detected("table1", "B", time.time())

        current = manager.get_current_round("table1")
        assert current is not None
        assert current.round_id == round_id

        # 不存在的桌
        assert manager.get_current_round("table_nonexist") is None

    def test_get_round_current(self, manager):
        """測試獲取當前局（通過 round_id）"""
        round_id = manager.on_result_detected("table1", "B", time.time())

        round_obj = manager.get_round("table1", round_id)
        assert round_obj is not None
        assert round_obj.round_id == round_id

    def test_get_round_history(self, manager):
        """測試獲取歷史局"""
        round1 = manager.on_result_detected("table1", "B", time.time())
        time.sleep(0.01)
        round2 = manager.on_result_detected("table1", "P", time.time())

        # 獲取舊局（在歷史中）
        old_round = manager.get_round("table1", round1)
        assert old_round is not None
        assert old_round.round_id == round1

        # 獲取當前局
        current_round = manager.get_round("table1", round2)
        assert current_round is not None
        assert current_round.round_id == round2

    def test_get_round_nonexistent(self, manager):
        """測試獲取不存在的局"""
        round_obj = manager.get_round("table1", "nonexistent_round")
        assert round_obj is None


class TestHistoryManagement:
    """測試歷史管理"""

    def test_history_limit(self, manager):
        """測試歷史限制（最多 100 局）"""
        # 創建 150 局
        for i in range(150):
            manager.on_result_detected("table1", "B", time.time())
            time.sleep(0.001)

        # 驗證只保留最近 100 局
        assert len(manager.round_history["table1"]) == 100

    def test_history_order(self, manager):
        """測試歷史順序（從舊到新）"""
        rounds = []
        for i in range(5):
            round_id = manager.on_result_detected("table1", "B", time.time())
            rounds.append(round_id)
            time.sleep(0.01)

        # 驗證歷史順序
        history = manager.round_history["table1"]
        for i, expected_round_id in enumerate(rounds):
            assert history[i].round_id == expected_round_id


class TestStatus:
    """測試狀態獲取"""

    def test_get_status_no_round(self, manager):
        """測試無當前局時的狀態"""
        status = manager.get_status("table1")
        assert status["status"] == "no_current_round"

    def test_get_status_with_round(self, manager):
        """測試有當前局時的狀態"""
        round_id = manager.on_result_detected("table1", "B", time.time())

        status = manager.get_status("table1")
        assert status["round_id"] == round_id
        assert status["phase"] == "settling"
        assert status["result_winner"] == "B"
        assert status["has_pending_bet"] is False
        assert status["is_participated"] is False
        assert "timers" in status

    def test_get_status_all_tables(self, manager):
        """測試獲取所有桌狀態"""
        manager.on_result_detected("table1", "B", time.time())
        manager.on_result_detected("table2", "P", time.time())

        status = manager.get_status()  # 無參數 = 所有桌
        assert "table1" in status
        assert "table2" in status
        assert status["table1"]["result_winner"] == "B"
        assert status["table2"]["result_winner"] == "P"


class TestErrorHandling:
    """測試錯誤處理"""

    def test_mark_bet_placed_wrong_round(self, manager):
        """測試標記不存在的局下注"""
        round_id = manager.on_result_detected("table1", "B", time.time())

        # 嘗試標記錯誤的 round_id（應記錄警告但不崩潰）
        manager.mark_bet_placed("table1", "wrong_round_id")

        # 驗證當前局未受影響
        current = manager.get_current_round("table1")
        assert current.is_participated is False

    def test_mark_bet_settled_nonexistent_table(self, manager):
        """測試標記不存在的桌結算"""
        # 不應崩潰
        manager.mark_bet_settled("nonexistent_table", "some_round")

    def test_warning_on_pending_bet(self, manager, caplog):
        """測試檢測到有未結算倉位時的警告"""
        import logging
        caplog.set_level(logging.WARNING)

        # 第一局下注但未結算
        round1 = manager.on_result_detected("table1", "B", time.time())
        manager.mark_bet_placed("table1", round1)

        # 立即開始第二局（第一局還有未結算倉位）
        round2 = manager.on_result_detected("table1", "P", time.time())

        # 驗證警告被記錄
        assert any("未結算的倉位" in record.message for record in caplog.records)


class TestStopAndCleanup:
    """測試停止和清理"""

    def test_stop(self, manager, qapp):
        """測試停止管理器"""
        # 創建一些狀態
        manager.on_result_detected("table1", "B", time.time())
        manager.on_result_detected("table2", "P", time.time())

        # 停止
        manager.stop()

        # 驗證清理
        assert len(manager.current_rounds) == 0
        assert len(manager.round_history) == 0

    def test_stop_cancels_timers(self, manager, qapp):
        """測試停止取消所有計時器"""
        manager.on_result_detected("table1", "B", time.time())

        # 驗證計時器啟動
        status = manager.get_status("table1")
        # 至少有一個計時器應該是活躍的
        timers = status.get("timers", {})
        any_active = any(timers.values())

        # 停止
        manager.stop()

        # 等待一段時間確保沒有計時器觸發
        process_events(qapp, timeout_ms=200)

        # 管理器應該保持清空狀態
        assert len(manager.current_rounds) == 0
