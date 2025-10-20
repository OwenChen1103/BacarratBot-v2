# src/autobet/autobet_engine.py
import os, csv, json, time, logging, threading
from typing import Dict, Optional, List, Tuple
from .detectors import OverlayDetectorWrapper as OverlayDetector, ProductionOverlayDetector
from .planner import build_click_plan
from .chip_planner import SmartChipPlanner, BettingPolicy
from .chip_profile_manager import ChipProfile
from .actuator import Actuator
from .risk import IdempotencyGuard, check_limits

logger = logging.getLogger(__name__)

class AutoBetEngine:
    def __init__(self, dry_run: bool = True, log_callback=None, chip_profile: Optional[ChipProfile] = None):
        self.dry = bool(dry_run)
        self.log_callback = log_callback
        self.enabled = False
        self.ui: Dict = {}
        self.pos: Dict = {}
        self.strategy: Dict = {}
        self.overlay: Optional[OverlayDetector] = None
        self.act: Optional[Actuator] = None
        self.chip_profile = chip_profile
        self.smart_planner: Optional[SmartChipPlanner] = None
        self._tick_stop = threading.Event()
        self._tick_thread: Optional[threading.Thread] = None
        self.state = "idle"
        self.last_winner = None
        self.rounds = 0
        self.net = 0
        self.step_idx = 0  # for martingale
        self.guard = IdempotencyGuard()
        self.current_plan = None
        self.session_ctx = {"last_result_ready": False}
        self._exec_lock = threading.Lock()  # 防止併發執行
        self.dry_step_delay_ms = 2000  # 模擬模式步驟間隔（毫秒）- 2秒間隔
        # session files
        os.makedirs("data/sessions", exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.csv_path = f"data/sessions/session-{ts}.csv"
        self.ndjson_path = "data/sessions/events.out.ndjson"
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["ts","state","round_id","winner","plan","amount","net"])

    def load_ui_config(self, ui: Dict):
        self.ui = ui or {}

    def load_positions(self, path: str, dpi_scale: float = 1.0) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.pos = json.load(f)
            return True
        except Exception as e:
            logger.error(f"load_positions: {e}")
            return False

    def load_strategy(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.strategy = json.load(f)
            return True
        except Exception as e:
            logger.error(f"load_strategy: {e}")
            return False

    def set_log_callback(self, callback):
        """設置日誌回調函數"""
        self.log_callback = callback
        if self.act:
            self.act.log_callback = callback

    def initialize_components(self) -> bool:
        try:
            self.overlay = OverlayDetector(self.ui, self.pos)

            # 初始化 Actuator：優先使用 ChipProfile，否則使用 positions
            self.act = Actuator(
                chip_profile=self.chip_profile,
                positions=self.pos,
                ui_cfg=self.ui,
                dry_run=self.dry,
                log_callback=self.log_callback
            )

            # 初始化 SmartChipPlanner
            if self.chip_profile:
                calibrated_chips = self.chip_profile.get_calibrated_chips()
                if calibrated_chips:
                    self.smart_planner = SmartChipPlanner(
                        available_chips=calibrated_chips,
                        policy=BettingPolicy(priority=BettingPolicy.MIN_CLICKS, fallback=BettingPolicy.FLOOR)
                    )
                    logger.info(f"SmartChipPlanner 初始化成功，{len(calibrated_chips)} 顆已校準籌碼")
                else:
                    logger.warning("ChipProfile 中沒有已校準的籌碼，將使用舊系統")

            # 加這兩行 - 確認載入的是哪個類
            logger.warning(
                "USING OVERLAY: %s (module=%s)",
                type(self.overlay).__name__, type(self.overlay).__module__
            )

            # 截圖健康檢查
            ok, err = getattr(self.overlay, "health_check", lambda: (True, ""))()
            if not ok:
                logger.error(f"Overlay screenshot health-check failed: {err}")
                raise RuntimeError(err)

            return True
        except Exception as e:
            logger.error(f"init components failed: {e}", exc_info=True)
            return False

    # 外部事件來源會呼叫它（RESULT / BETTING_OPEN 等）
    def on_event(self, evt: Dict):
        et = evt.get("type")
        if et == "RESULT":
            self._handle_result(evt)

    def set_enabled(self, flag: bool):
        if self.enabled == flag:
            return
        self.enabled = flag
        if flag:
            self._tick_stop.clear()
            self._tick_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._tick_thread.start()
            logger.info("engine enabled")
        else:
            self._tick_stop.set()
            if self._tick_thread and self._tick_thread.is_alive():
                self._tick_thread.join(timeout=1.5)
            logger.info("engine disabled")

    def _run_loop(self):
        # 120ms 一次
        while not self._tick_stop.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.error(f"tick error: {e}", exc_info=True)
                self.state = "error"
                break
            time.sleep(0.12)

    def _tick(self):
        """主狀態機循環 - 完整狀態轉換邏輯"""
        if not self.enabled:
            self.state = "stopped"
            return

        try:
            # 檢查是否可下注
            is_open = self.overlay.overlay_is_open() if self.overlay else False
            
            # 添加調試日誌
            if self.state == "idle" and is_open:
                logger.info(f"檢測到可下注狀態，從 idle 轉換到 betting_open")

            if self.state == "idle":
                if is_open:
                    self.state = "betting_open"
                    self._emit_state_change()

            elif self.state == "betting_open":
                if is_open:
                    # 停用自動執行，只記錄狀態變化
                    # 實際執行由 Dashboard 的手動觸發控制
                    logger.debug("在 betting_open 狀態，等待外部觸發執行")
                    # 不自動執行，維持 betting_open 狀態
                else:
                    # 下注期關閉，直接進入 in_round
                    self.state = "in_round"
                    self._emit_state_change()

            elif self.state == "placing_bets":
                # 下注動作完成，進入確認等待
                self.state = "wait_confirm"
                self._emit_state_change()

            elif self.state == "wait_confirm":
                # 送單前最後檢查
                if not self.dry:
                    if is_open:
                        self.act.confirm()
                        logger.info("Confirmed betting")
                    else:
                        if self.ui.get("safety", {}).get("cancel_on_close", True):
                            self.act.cancel()
                            logger.warning("overlay closed before confirm -> cancelled")
                self.state = "in_round"
                self._emit_state_change()

            elif self.state == "in_round":
                # 等待結果事件，由 _handle_result 觸發轉換
                pass

            elif self.state == "eval_result":
                # 結果處理完成，回到等待狀態
                self.state = "idle"
                self._emit_state_change()

            elif self.state in ("waiting_round", "paused", "error"):
                # 特殊狀態處理
                if self.state == "waiting_round" and is_open:
                    self.state = "idle"
                    self._emit_state_change()

        except Exception as e:
            logger.error(f"state machine error: {e}", exc_info=True)
            self.state = "error"
            self._emit_state_change()

    def _emit_state_change(self):
        """通知狀態變更"""
        logger.info(f"引擎狀態變更: {self.state}")

    def _build_plan_with_smart_planner(self, unit: int, targets_units: Dict[str, int]) -> List[Tuple[str, str]]:
        """
        使用 SmartChipPlanner 生成下注計畫

        Args:
            unit: 單位金額
            targets_units: 目標與單位數 {target: units}

        Returns:
            List[Tuple[str, str]]: 點擊計畫，格式與舊系統相同
        """
        plan: List[Tuple[str, str]] = []

        for target, units in targets_units.items():
            amount = unit * int(units)

            # 使用 SmartChipPlanner 規劃
            bet_plan = self.smart_planner.plan_bet(
                target_amount=amount,
                max_clicks=self.chip_profile.constraints.get("max_clicks_per_hand", 8) if self.chip_profile else None
            )

            if not bet_plan.success:
                logger.error(f"SmartChipPlanner 規劃失敗: {bet_plan.reason}")
                # 回退到舊系統
                logger.warning("回退到舊系統 planner")
                return build_click_plan(unit, targets_units)

            if bet_plan.warnings:
                for warning in bet_plan.warnings:
                    logger.warning(f"SmartChipPlanner 警告: {warning}")

            # 轉換 BetPlan 為舊格式
            for chip in bet_plan.chips:
                plan.append(('chip', str(chip.value)))
            plan.append(('bet', target))

            logger.info(f"目標 {target}: {bet_plan.recipe} (實際 {bet_plan.actual_amount} 元)")

        return plan

    # ============================================================
    # 🗑️ 舊版策略系統已廢棄
    # 所有自動投注邏輯現由 LineOrchestrator 處理
    # 以下方法已移除：_prepare_betting_plan, _execute_betting_plan
    # 保留 trigger_if_open() 僅供手動測試點擊順序使用
    # ============================================================

    def trigger_if_open(self) -> bool:
        """手動觸發執行點擊順序（僅用於測試）

        注意：這個方法不再用於自動投注策略，僅保留用於：
        1. Dashboard 手動測試點擊順序
        2. 驗證點擊配置是否正確

        所有實際下注決策由 LineOrchestrator 處理。
        回傳是否成功觸發執行。
        """
        try:
            # 防止併發執行檢查
            if not self._exec_lock.acquire(blocking=False):
                logger.info("trigger_if_open: 已有執行中，跳過重複觸發")
                return False

            try:
                # 簡單檢查：只執行點擊順序，不管複雜狀態
                click_sequence = self.pos.get("click_sequence", [])
                if not click_sequence:
                    logger.warning("沒有找到點擊順序配置")
                    return False

                logger.info(f"觸發執行點擊順序: {click_sequence}")
                self._execute_click_sequence(click_sequence)

                # 執行完成後更新狀態
                if self.state == "betting_open":
                    self.state = "placing_bets"
                    self._emit_state_change()

                return True
            finally:
                self._exec_lock.release()

        except Exception as e:
            logger.error(f"trigger_if_open 發生錯誤: {e}", exc_info=True)
            return False

    def _execute_click_sequence(self, sequence: list):
        """執行自定義點擊順序"""
        logger.info(f"開始執行點擊順序: {' → '.join(sequence)}")

        for i, action in enumerate(sequence):
            # 在模擬模式下，除了第一個步驟外，先延遲再執行（讓步驟間隔明顯）
            if self.dry and i > 0:
                time.sleep(self.dry_step_delay_ms / 1000.0)

            action_desc = self._get_action_description(action)
            logger.info(f"步驟 {i+1}/{len(sequence)}: {action_desc}")

            # 根據動作類型執行相應操作
            if action.startswith("chip_"):
                # 解析籌碼值
                chip_value = self._parse_chip_value(action)
                if chip_value:
                    self.act.click_chip_value(chip_value)
            elif action in ["banker", "player", "tie"]:
                self.act.click_bet(action)
            elif action == "confirm":
                self.act.confirm()
            elif action == "cancel":
                self.act.cancel()
            else:
                logger.warning(f"未知動作: {action}")

        logger.info("點擊順序執行完成")
        # 狀態已在 trigger_if_open 中重置

    def _get_action_description(self, action: str) -> str:
        """獲取動作的中文描述"""
        descriptions = {
            "chip_100": "選擇 100 籌碼",
            "chip_1k": "選擇 1K 籌碼", 
            "chip_5k": "選擇 5K 籌碼",
            "chip_10k": "選擇 10K 籌碼",
            "chip_50k": "選擇 50K 籌碼",
            "banker": "下注莊家",
            "player": "下注閒家",
            "tie": "下注和局",
            "confirm": "確認下注",
            "cancel": "取消下注"
        }
        return descriptions.get(action, action)

    def _parse_chip_value(self, chip_action: str) -> int:
        """解析籌碼動作為數值"""
        chip_mapping = {
            "chip_100": 100,
            "chip_1k": 1000,
            "chip_5k": 5000,
            "chip_10k": 10000,
            "chip_50k": 50000
        }
        return chip_mapping.get(chip_action, 0)

    def _do_betting_cycle(self):
        self.state = "betting_open"
        unit = int(self.strategy.get("unit", 1000))
        targets = self.strategy.get("targets", ["banker"])
        split = self.strategy.get("split_units", {"banker":1})
        targets_units = {t: int(split.get(t,1)) for t in targets}

        # 優先使用 SmartChipPlanner
        if self.smart_planner:
            logger.info("使用 SmartChipPlanner 生成計畫")
            plan = self._build_plan_with_smart_planner(unit, targets_units)
        else:
            logger.warning("SmartChipPlanner 未初始化，使用舊系統")
            plan = build_click_plan(unit, targets_units)

        plan_repr = json.dumps(plan, ensure_ascii=False)
        round_id = f"NOID-{int(time.time())}"  # 若外部未給，送單冪等仍可用

        # 風控：計算此輪金額
        per_round_amount = unit * sum(targets_units.values())
        ok, reason = check_limits(self.strategy.get("limits", {}), per_round_amount, self.net)
        if not ok:
            logger.warning(f"risk blocked: {reason}")
            self.state = "paused"
            return

        # 冪等鎖
        if not self.guard.accept(round_id, plan_repr):
            logger.info("idempotent reject (same plan in same round)")
            self.state = "waiting_round"
            return

        # 點 chips + 下注點，不送 confirm（乾跑驗收階段）
        self.state = "placing_bets"
        for kind, val in plan:
            if kind == "chip":
                self.act.click_chip_value(int(val))
            elif kind == "bet":
                self.act.click_bet(val)

        # 乾跑：不按確認；實戰才送單且最後再檢查 overlay
        if not self.dry:
            if self.overlay.overlay_is_open():
                self.act.confirm()
            else:
                if self.ui.get("safety", {}).get("cancel_on_close", True):
                    self.act.cancel()
                    logger.warning("overlay closed before confirm -> cancel()")

        self.state = "in_round"

    def _handle_result(self, evt: Dict):
        """處理遊戲結果事件"""
        try:
            # 更新統計
            self.rounds += 1
            self.last_winner = evt.get("winner")

            # 設置結果就緒標記，讓狀態機轉換到 eval_result
            self.session_ctx["last_result_ready"] = True

            # 進入結果評估狀態
            if self.state == "in_round":
                self.state = "eval_result"
                self._emit_state_change()
                self._apply_result_and_staking(evt)

            # 寫會話記錄
            row = [int(time.time()*1000), self.state, evt.get("round_id"), self.last_winner, "-", "-", self.net]
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            with open(self.ndjson_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")

            logger.info(f"Result processed: Round {self.rounds}, Winner: {self.last_winner}")

        except Exception as e:
            logger.error(f"Handle result failed: {e}", exc_info=True)
            self.state = "error"

    def _apply_result_and_staking(self, evt: Dict):
        """處理結果後重置狀態（舊版策略邏輯已廢棄）

        注意：Martingale 和盈虧計算現由 LineOrchestrator 處理
        這裡只做基本的狀態重置
        """
        try:
            # 重置結果標記
            self.session_ctx["last_result_ready"] = False
            self.current_plan = None

            logger.debug(f"Applied result for round {self.rounds} (盈虧計算由 LineOrchestrator 處理)")

        except Exception as e:
            logger.error(f"Apply result failed: {e}", exc_info=True)

    def get_status(self) -> Dict:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry,
            "current_state": self.state,
            "rounds": self.rounds,
            "net": self.net,
            "last_winner": self.last_winner
        }

    def force_execute_sequence(self):
        """強制執行點擊順序（用於測試）"""
        # 防止併發執行
        if not self._exec_lock.acquire(blocking=False):
            logger.info("force_execute_sequence: 已有執行中，跳過")
            return False

        try:
            logger.info("強制執行點擊順序...")
            click_sequence = self.pos.get("click_sequence", [])
            if click_sequence:
                logger.info(f"發現點擊順序: {click_sequence}")
                self._execute_click_sequence(click_sequence)
                return True
            else:
                logger.warning("沒有找到點擊順序配置")
                return False
        except Exception as e:
            logger.error(f"force_execute_sequence 錯誤: {e}", exc_info=True)
            return False
        finally:
            self._exec_lock.release()