# src/autobet/autobet_engine.py
import os, csv, json, time, logging, threading
from typing import Dict, Optional
from .detectors import OverlayDetectorWrapper as OverlayDetector, ProductionOverlayDetector
from .planner import build_click_plan
from .actuator import Actuator
from .risk import IdempotencyGuard, check_limits

logger = logging.getLogger(__name__)

class AutoBetEngine:
    def __init__(self, dry_run: bool = True):
        self.dry = bool(dry_run)
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

    def initialize_components(self) -> bool:
        try:
            self.overlay = OverlayDetector(self.ui, self.pos)
            self.act = Actuator(self.pos, self.ui, dry_run=self.dry)

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

            if self.state == "idle":
                if is_open:
                    self.state = "betting_open"
                    self._emit_state_change()

            elif self.state == "betting_open":
                if is_open:
                    # 構建下注計畫並檢查風控
                    if self._prepare_betting_plan():
                        self.state = "placing_bets"
                        self._emit_state_change()
                        self._execute_betting_plan()
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
        logger.debug(f"State changed to: {self.state}")

    def _prepare_betting_plan(self) -> bool:
        """準備下注計畫並檢查風控"""
        try:
            unit = int(self.strategy.get("unit", 1000))
            targets = self.strategy.get("targets", ["banker"])
            split = self.strategy.get("split_units", {"banker": 1})
            targets_units = {t: int(split.get(t, 1)) for t in targets}

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
            return True

        except Exception as e:
            logger.error(f"Prepare betting plan failed: {e}", exc_info=True)
            return False

    def _execute_betting_plan(self):
        """執行下注計畫"""
        if not self.current_plan:
            return

        logger.info(f"Executing betting plan: {len(self.current_plan)} actions")
        for kind, val in self.current_plan:
            if kind == "chip":
                self.act.click_chip_value(int(val))
            elif kind == "bet":
                self.act.click_bet(val)

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