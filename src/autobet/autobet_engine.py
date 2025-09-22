# src/autobet/autobet_engine.py
import os, csv, json, time, logging, threading
from typing import Dict, Optional
from .detectors import OverlayDetector
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
        if not self.enabled:
            self.state = "stopped"
            return
        # overlay 判斷
        is_open = self.overlay.overlay_is_open() if self.overlay else False
        if is_open and self.state in ("idle","waiting_round","eval_result"):
            self._do_betting_cycle()
        elif not is_open and self.state in ("placing_bets", "betting_open"):
            # 下注期關閉，自動回 idle
            self.state = "in_round"

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
        # 更新統計
        self.rounds += 1
        self.last_winner = evt.get("winner")
        # MVP：不計賠率，僅記錄局數；之後可依賠率調整 self.net
        self.state = "eval_result"
        # 寫會話紀錄
        row = [int(time.time()*1000), self.state, evt.get("round_id"), self.last_winner, "-", "-", self.net]
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)
        with open(self.ndjson_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        # 準備下一輪
        self.state = "waiting_round"

    def get_status(self) -> Dict:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry,
            "current_state": self.state,
            "rounds": self.rounds,
            "net": self.net,
            "last_winner": self.last_winner
        }