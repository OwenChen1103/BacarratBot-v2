# src/autobet/autobet_engine.py
import os, csv, json, time, logging, threading
from typing import Dict, Optional
from .detectors import OverlayDetectorWrapper as OverlayDetector, ProductionOverlayDetector
from .planner import build_click_plan
from .actuator import Actuator
from .risk import IdempotencyGuard, check_limits

logger = logging.getLogger(__name__)

class AutoBetEngine:
    def __init__(self, dry_run: bool = True, log_callback=None):
        self.dry = bool(dry_run)
        self.log_callback = log_callback
        self.enabled = False
        self.ui: Dict = {}
        self.pos: Dict = {}
        self.strategy: Dict = {}
        self.overlay: Optional[OverlayDetector] = None
        self.act: Optional[Actuator] = None
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
            self.act = Actuator(self.pos, self.ui, dry_run=self.dry, log_callback=self.log_callback)

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
                    logger.info("在 betting_open 狀態，準備執行下注計畫")
                    # 構建下注計畫並檢查風控
                    if self._prepare_betting_plan():
                        self.state = "placing_bets"
                        self._emit_state_change()
                        self._execute_betting_plan()
                    else:
                        logger.warning("下注計畫準備失敗")
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

    def _prepare_betting_plan(self) -> bool:
        """準備下注計畫並檢查風控"""
        try:
            logger.info("開始準備下注計畫...")
            
            # 檢查是否有自定義點擊順序
            click_sequence = self.pos.get("click_sequence", [])
            if click_sequence:
                logger.info(f"發現自定義點擊順序: {click_sequence}")
                self.current_plan = click_sequence  # 直接使用點擊順序
                return True
            
            # 使用策略生成計畫
            unit = int(self.strategy.get("unit", 1000))
            targets = self.strategy.get("targets", ["banker"])
            split = self.strategy.get("split_units", {"banker": 1})
            targets_units = {t: int(split.get(t, 1)) for t in targets}
            
            logger.info(f"策略配置: unit={unit}, targets={targets}, split_units={split}")

            plan = build_click_plan(unit, targets_units)
            plan_repr = json.dumps(plan, ensure_ascii=False)
            round_id = f"NOID-{int(time.time())}"

            # 風控檢查
            per_round_amount = unit * sum(targets_units.values())
            ok, reason = check_limits(self.strategy.get("limits", {}), per_round_amount, self.net)
            if not ok:
                logger.warning(f"Risk blocked: {reason}")
                self.state = "paused"
                return False

            # 冪等檢查
            if not self.guard.accept(round_id, plan_repr):
                logger.info("Idempotent reject (same plan in same round)")
                self.state = "waiting_round"
                return False

            self.current_plan = plan
            logger.info(f"下注計畫準備完成: {plan}")
            return True

        except Exception as e:
            logger.error(f"Prepare betting plan failed: {e}", exc_info=True)
            return False

    def _execute_betting_plan(self):
        """執行下注計畫"""
        if not self.current_plan:
            logger.warning("沒有下注計畫可執行")
            return

        logger.info(f"開始執行下注計畫: {self.current_plan}")

        # 檢查是否是點擊順序（字串列表）
        if isinstance(self.current_plan, list) and len(self.current_plan) > 0 and isinstance(self.current_plan[0], str):
            logger.info("使用自定義點擊順序執行")
            self._execute_click_sequence(self.current_plan)
        else:
            logger.info(f"使用策略計畫執行: {len(self.current_plan)} 個動作")
            for kind, val in self.current_plan:
                if kind == "chip":
                    self.act.click_chip_value(int(val))
                elif kind == "bet":
                    self.act.click_bet(val)
                # 在模擬模式下添加短間隔
                if self.dry:
                    time.sleep(self.dry_step_delay_ms / 1000.0)

    def trigger_if_open(self) -> bool:
        """在檢測到可下注時立即嘗試執行一次（由外部偵測器提示）。
        回傳是否成功觸發執行。"""
        try:
            # 簡單檢查：只執行點擊順序，不管複雜狀態
            click_sequence = self.pos.get("click_sequence", [])
            if not click_sequence:
                logger.warning("沒有找到點擊順序配置")
                return False

            logger.info(f"觸發執行點擊順序: {click_sequence}")
            self._execute_click_sequence(click_sequence)
            return True

        except Exception as e:
            logger.error(f"trigger_if_open 發生錯誤: {e}", exc_info=True)
            return False

    def _execute_click_sequence(self, sequence: list):
        """執行自定義點擊順序"""
        logger.info(f"開始執行點擊順序: {' → '.join(sequence)}")

        for i, action in enumerate(sequence):
            action_desc = self._get_action_description(action)
            logger.info(f"步驟 {i+1}/{len(sequence)}: {action_desc}")

            # 在模擬模式下先延遲（讓用戶看到步驟提示）
            if self.dry and i > 0:  # 第一個步驟不延遲
                time.sleep(self.dry_step_delay_ms / 1000.0)

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
        """應用結果並更新馬丁格爾等遞增邏輯"""
        try:
            # MVP: 簡單的勝負統計，暫不計算實際賠率
            # 後續可根據策略和賠率計算實際損益

            # 重置結果標記
            self.session_ctx["last_result_ready"] = False
            self.current_plan = None

            logger.debug(f"Applied result for round {self.rounds}")

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