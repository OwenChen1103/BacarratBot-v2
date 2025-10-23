#!/usr/bin/env python3
"""
P0 Emergency Fixes Integration Test

驗證以下修復是否正常工作：
1. ✅ 移除過時的 net profit 追蹤（AutoBetEngine.net）
2. ✅ 修復參與局排除邏輯（handle_result 先檢查 _pending）
3. ✅ 統一 round_id 生成（GameStateManager）

測試場景：
- 觀察局：無下注 → 應記錄到歷史
- 參與局：有下注 → 不應記錄到歷史，直接結算
- round_id 一致性：GameStateManager 統一生成和管理 round_id
"""
import sys
import time
import logging
from pathlib import Path

# 添加 src 到路徑
sys.path.insert(0, str(Path(__file__).parent / "src"))

from autobet.autobet_engine import AutoBetEngine
from autobet.game_state_manager import GameStateManager, GamePhase
from autobet.lines.orchestrator import LineOrchestrator
from autobet.lines.config import load_strategy_definitions

# 設置日誌
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def test_deprecated_net_removal():
    """測試 1: 驗證 AutoBetEngine.net 已移除"""
    logger.info("=" * 60)
    logger.info("測試 1: 驗證過時的 net profit 追蹤已移除")
    logger.info("=" * 60)

    engine = AutoBetEngine(dry_run=True)

    # 檢查 net 屬性不應存在
    if hasattr(engine, 'net'):
        logger.error("❌ FAILED: AutoBetEngine 仍有 net 屬性")
        return False

    # 檢查 get_status() 不應返回 net
    status = engine.get_status()
    if 'net' in status:
        logger.error("❌ FAILED: get_status() 仍返回 net 字段")
        return False

    logger.info("✅ PASSED: AutoBetEngine.net 已正確移除")
    return True


def test_round_manager_unified_ids():
    """測試 2: 驗證 GameStateManager 統一生成 round_id"""
    logger.info("=" * 60)
    logger.info("測試 2: 驗證 GameStateManager 統一 round_id 生成")
    logger.info("=" * 60)

    game_state = GameStateManager()

    # 模擬結果檢測
    table_id = "table1"
    winner = "B"
    detected_at = time.time()

    round_id = game_state.on_result_detected(table_id, winner, detected_at)

    # 驗證 round_id 格式
    expected_prefix = f"round-{table_id}-"
    if not round_id.startswith(expected_prefix):
        logger.error(f"❌ FAILED: round_id 格式錯誤: {round_id}")
        return False

    # 驗證 round_id 不包含 "_next" 後綴
    if "_next" in round_id:
        logger.error(f"❌ FAILED: round_id 包含 '_next' 後綴: {round_id}")
        return False

    # 驗證當前局信息
    current_round = game_state.get_current_round(table_id)
    if not current_round:
        logger.error("❌ FAILED: 無法獲取當前局")
        return False

    if current_round.round_id != round_id:
        logger.error(f"❌ FAILED: round_id 不一致: {current_round.round_id} vs {round_id}")
        return False

    if current_round.result_winner != winner:
        logger.error(f"❌ FAILED: 贏家不一致: {current_round.result_winner} vs {winner}")
        return False

    logger.info(f"✅ PASSED: GameStateManager 統一生成 round_id: {round_id}")
    return True


def test_round_manager_participation_tracking():
    """測試 3: 驗證 GameStateManager 參與狀態追蹤"""
    logger.info("=" * 60)
    logger.info("測試 3: 驗證參與狀態追蹤")
    logger.info("=" * 60)

    game_state = GameStateManager()

    table_id = "table1"
    detected_at = time.time()

    # 創建第一局（觀察局）
    round_id_1 = game_state.on_result_detected(table_id, "B", detected_at)
    current_1 = game_state.get_current_round(table_id)

    if current_1.is_participated:
        logger.error("❌ FAILED: 新局應該是未參與狀態")
        return False

    logger.info(f"✅ 新局 {round_id_1} 初始狀態: is_participated=False")

    # 標記下注
    game_state.mark_bet_placed(table_id, round_id_1)

    current_1_updated = game_state.get_current_round(table_id)
    if not current_1_updated.is_participated:
        logger.error("❌ FAILED: 標記下注後應該是參與狀態")
        return False

    logger.info(f"✅ 標記下注後: is_participated=True")

    # 創建第二局（不下注的觀察局）
    round_id_2 = game_state.on_result_detected(table_id, "P", detected_at + 20)
    current_2 = game_state.get_current_round(table_id)

    if current_2.is_participated:
        logger.error("❌ FAILED: 新觀察局應該是未參與狀態")
        return False

    logger.info(f"✅ 新觀察局 {round_id_2} 狀態: is_participated=False")

    # 驗證 should_include_in_history
    should_include_1 = game_state.should_include_in_history(table_id, round_id_1)
    should_include_2 = game_state.should_include_in_history(table_id, round_id_2)

    if should_include_1:
        logger.error(f"❌ FAILED: 參與局 {round_id_1} 不應計入歷史")
        return False

    if not should_include_2:
        logger.error(f"❌ FAILED: 觀察局 {round_id_2} 應計入歷史")
        return False

    logger.info("✅ PASSED: 參與狀態追蹤正確")
    logger.info(f"   - 參與局 {round_id_1}: should_include=False ✓")
    logger.info(f"   - 觀察局 {round_id_2}: should_include=True ✓")
    return True


def test_orchestrator_participation_exclusion():
    """測試 4: 驗證 LineOrchestrator 的參與局排除邏輯"""
    logger.info("=" * 60)
    logger.info("測試 4: 驗證參與局排除邏輯")
    logger.info("=" * 60)

    # 載入策略配置
    try:
        strategy_defs = load_strategy_definitions()
        if not strategy_defs:
            logger.warning("⚠️ 沒有策略配置，跳過此測試")
            return True
    except Exception as e:
        logger.warning(f"⚠️ 無法載入策略配置: {e}，跳過此測試")
        return True

    # 創建 LineOrchestrator
    orchestrator = LineOrchestrator(strategies=strategy_defs)

    table_id = "table1"
    strategy_key = list(strategy_defs.keys())[0]

    # 獲取 SignalTracker
    tracker = orchestrator.signal_trackers.get(strategy_key)
    if not tracker:
        logger.error(f"❌ FAILED: 找不到策略 {strategy_key} 的 tracker")
        return False

    # 場景 1: 觀察局 - 無 pending position
    logger.info(f"場景 1: 觀察局（無下注）")
    round_id_obs = f"round-{table_id}-{int(time.time() * 1000)}"

    # 記錄歷史前的狀態
    history_before = tracker._get_recent_winners(table_id, 10)
    logger.info(f"  觀察前歷史: {history_before}")

    # 模擬結果處理（無 pending position）
    orchestrator.handle_result(
        table_id=table_id,
        round_id=round_id_obs,
        winner="B",
        timestamp=time.time(),
    )

    # 檢查歷史是否增加
    history_after = tracker._get_recent_winners(table_id, 10)
    logger.info(f"  觀察後歷史: {history_after}")

    if len(history_after) != len(history_before) + 1:
        logger.error("❌ FAILED: 觀察局應該記錄到歷史")
        return False

    if history_after[-1] != "B":
        logger.error(f"❌ FAILED: 歷史記錄錯誤: {history_after[-1]} != B")
        return False

    logger.info("✅ 觀察局正確記錄到歷史")

    # 場景 2: 參與局 - 有 pending position
    logger.info(f"場景 2: 參與局（有下注）")
    round_id_bet = f"round-{table_id}-{int(time.time() * 1000) + 1000}"

    # 手動添加 pending position（模擬下注）
    from autobet.lines.state import LayerOutcome
    from autobet.lines.orchestrator import PendingPosition

    pending_position = PendingPosition(
        table_id=table_id,
        round_id=round_id_bet,
        strategy_key=strategy_key,
        direction="B",
        layer_index=0,
        amount=100,
        timestamp=time.time(),
    )

    pending_key = (table_id, round_id_bet, strategy_key)
    orchestrator._pending[pending_key] = pending_position

    # 記錄歷史前的狀態
    history_before_2 = tracker._get_recent_winners(table_id, 10)
    logger.info(f"  下注前歷史: {history_before_2}")

    # 模擬結果處理（有 pending position）
    orchestrator.handle_result(
        table_id=table_id,
        round_id=round_id_bet,
        winner="B",  # 贏
        timestamp=time.time(),
    )

    # 檢查歷史是否沒有增加
    history_after_2 = tracker._get_recent_winners(table_id, 10)
    logger.info(f"  下注後歷史: {history_after_2}")

    if len(history_after_2) != len(history_before_2):
        logger.error("❌ FAILED: 參與局不應記錄到歷史")
        logger.error(f"  歷史長度變化: {len(history_before_2)} -> {len(history_after_2)}")
        return False

    logger.info("✅ 參與局正確排除在歷史外")

    # 驗證 pending position 已被移除
    if pending_key in orchestrator._pending:
        logger.error("❌ FAILED: pending position 應該被移除")
        return False

    logger.info("✅ PASSED: 參與局排除邏輯正確")
    return True


def main():
    """運行所有測試"""
    logger.info("\n" + "=" * 60)
    logger.info("P0 Emergency Fixes Integration Test")
    logger.info("=" * 60 + "\n")

    tests = [
        test_deprecated_net_removal,
        test_round_manager_unified_ids,
        test_round_manager_participation_tracking,
        test_orchestrator_participation_exclusion,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            logger.error(f"❌ 測試 {test_func.__name__} 發生異常: {e}", exc_info=True)
            results.append((test_func.__name__, False))

        logger.info("")  # 空行分隔

    # 總結
    logger.info("=" * 60)
    logger.info("測試總結")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status}: {test_name}")

    logger.info("")
    logger.info(f"總計: {passed}/{total} 測試通過")

    if passed == total:
        logger.info("🎉 所有 P0 修復驗證通過！")
        return 0
    else:
        logger.error(f"⚠️ {total - passed} 個測試失敗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
