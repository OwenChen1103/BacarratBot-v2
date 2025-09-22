#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, time
from typing import Dict, Optional
import numpy as np
import cv2
import pyautogui
from collections import deque
from PySide6.QtCore import QObject, Signal, QTimer

from .actuator import Actuator

class AutoBetEngine(QObject):
    # signals
    log_message = Signal(str)
    state_changed = Signal(str)
    betting_plan_ready = Signal(dict)
    session_stats_updated = Signal(dict)
    risk_alert = Signal(str, str)

    def __init__(self, dry_run: bool=True, parent=None):
        super().__init__(parent)
        self.enabled = False
        self.state = "stopped"
        self.dry_run = dry_run
        self.positions: Optional[Dict] = None
        self.strategy: Optional[Dict] = None
        self.actuator: Optional[Actuator] = None

        self.last_winner = None
        self.rounds_played = 0
        self.net_profit = 0
        self.step_idx = 0
        self._seen_rounds = set()
        self._betting_open = False
        self._last_targets = set()

        # 穩定判斷機制
        self._open_votes = deque(maxlen=5)  # 最近5次判斷
        self._hysteresis_state = "closed"  # "open" or "closed"
        self._last_state_change = 0  # 上次狀態改變時間
        self._placed_rounds = set()  # 已下注的回合ID
        self._current_round_id = None  # 當前回合ID

        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._tick)

    # external control
    def set_enabled(self, v: bool):
        self.enabled = v
        if v:
            self._set_state("idle"); self.timer.start()
            self.log_message.emit("AutoBet 啟動")
        else:
            self.timer.stop(); self._set_state("stopped")
            self.log_message.emit("AutoBet 停止")

    def set_dry_run(self, v: bool):
        self.dry_run = v
        if self.actuator: self.actuator.set_dry_run(v)
        self.log_message.emit(f"切換為{'乾跑' if v else '實戰'}")

    def load_positions(self, path: str) -> bool:
        with open(path, "r", encoding="utf-8") as f:
            self.positions = json.load(f)
        self.actuator = Actuator(self.positions, self.dry_run)
        self.log_message.emit(f"載入 positions: {path}")
        return True

    def load_strategy(self, path: str) -> bool:
        with open(path, "r", encoding="utf-8") as f:
            self.strategy = json.load(f)
        self.log_message.emit(f"載入 strategy: {path}")
        return True

    # monitor hooks
    def on_round_detected(self, evt: Dict):
        rtype = evt.get("type") or "RESULT"
        if rtype == "REVOKE":
            # REVOKE時要處理已下注記錄的回滾
            rid = evt.get("round_id")
            if rid and rid in self._placed_rounds:
                self._placed_rounds.remove(rid)
                self.log_message.emit(f"撤回回合 {rid}，清除下注記錄")
            self.step_idx = max(0, self.step_idx-1)
            self.log_message.emit("收到撤回，退階")
            return
        if rtype == "RESULT":
            rid = evt.get("round_id") or str(evt.get("ts") or time.time())
            self._seen_rounds.add(rid)
            self.last_winner = evt.get("winner")
            self.rounds_played += 1
            # 這裡先不算損益，等你接實際投注金額
            self.session_stats_updated.emit({
                "net_profit": self.net_profit,
                "rounds_played": self.rounds_played
            })
            self._set_state("waiting_round")
        elif rtype == "NEW_ROUND":
            # 新回合開始時設置當前回合ID
            rid = evt.get("round_id") or str(evt.get("ts") or time.time())
            self._current_round_id = rid
            self.log_message.emit(f"新回合開始: {rid}")

    def on_environment_warning(self, msg: str):
        self._set_state("paused"); self.risk_alert.emit("WARNING", msg)

    # core loop
    def _tick(self):
        if not (self.enabled and self.positions and self.strategy and self.actuator):
            return

        self._betting_open = self._is_betting_open()

        if self.state in ("stopped","paused"):
            return

        if self.state in ("idle","waiting_round"):
            if self._betting_open: self._set_state("betting_open")

        if self.state == "betting_open":
            plan = self._make_plan()
            if plan and plan["total_amount"] > 0:
                self.betting_plan_ready.emit(plan)
                self._set_state("placing_bets")
                ok = self._execute_plan(plan)
                self._set_state("in_round" if ok else "in_round")
            elif not self._betting_open:
                self._set_state("waiting_round")

    # vision
    def _is_betting_open_raw(self) -> bool:
        """原始下注期判斷（僅灰度均值）"""
        roi = (self.positions or {}).get("roi", {}).get("overlay")
        if not roi:
            return False
        x,y,w,h = roi["x"],roi["y"],roi["w"],roi["h"]
        im = pyautogui.screenshot(region=(x,y,w,h))
        gray = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
        m = float(gray.mean())
        # 簡化：越暗視為無紫條→可下注
        return m < 120.0

    def _is_betting_open(self) -> bool:
        """穩定的下注期判斷：去抖+遲滯"""
        raw_result = self._is_betting_open_raw()
        current_time = time.time()

        # 記錄投票
        self._open_votes.append(1 if raw_result else 0)

        # 需要至少3次投票才開始判斷
        if len(self._open_votes) < 3:
            return self._hysteresis_state == "open"

        # 計算支持開放的票數
        open_votes = sum(self._open_votes)
        total_votes = len(self._open_votes)

        # 遲滯邏輯：開/關使用不同門檻
        if self._hysteresis_state == "closed":
            # 需要更強的證據才開放 (至少4/5票支持)
            if open_votes >= max(4, total_votes * 0.8):
                self._hysteresis_state = "open"
                self._last_state_change = current_time
                self.log_message.emit("下注期開放")
        else:  # currently "open"
            # 需要更強的證據才關閉 (至少4/5票反對)
            if open_votes <= min(1, total_votes * 0.2):
                self._hysteresis_state = "closed"
                self._last_state_change = current_time
                self.log_message.emit("下注期關閉")

        return self._hysteresis_state == "open"

    def _can_confirm_safely(self) -> bool:
        """檢查是否可以安全確認下注（距離關窗有足夠時間）"""
        if not self._is_betting_open():
            return False

        # 獲取策略中的安全確認時間（默認600ms）
        safe_ms = (self.strategy.get("timing", {}).get("safe_confirm_ms", 600))

        # 如果剛剛從開放變為關閉（但current check還是開放），給更多緩衝
        time_since_change = (time.time() - self._last_state_change) * 1000
        if time_since_change < safe_ms:
            return False

        return True

    # plan
    def _staking(self, key, default=None):
        return (self.strategy.get("staking") or {}).get(key, default)

    def _make_plan(self) -> Optional[Dict]:
        unit = int(self.strategy.get("unit", 100))
        targets = list(self.strategy.get("targets") or [])
        if not targets: return None

        # 簡單 filters
        for f in self.strategy.get("filters", []):
            cond = f.get("when")
            if not cond: continue
            ctx = {"last_winner": self.last_winner}
            try:
                if eval(cond, {}, ctx):
                    targets = f.get("override_targets", targets)
            except Exception:
                pass

        st = self.strategy.get("staking", {"type":"fixed","base_units":1})
        base = int(st.get("base_units", 1))
        if st.get("type") == "martingale":
            units = base * (2 ** max(0, self.step_idx))
        else:
            units = base

        split = self.strategy.get("split_units") or {t:1 for t in targets}
        target_units = {t: int(split.get(t,1)) * units for t in targets}
        total_units = sum(target_units.values())
        total_amount = total_units * unit
        cap = int((self.strategy.get("limits") or {}).get("per_round_cap", 10**9))
        total_amount = min(total_amount, cap)
        self._last_targets = set(target_units.keys())
        return {"total_amount": total_amount, "targets": target_units, "unit": unit}

    # execute
    def _execute_plan(self, plan: Dict) -> bool:
        # 同局冪等檢查
        rid = self._current_round_id
        if rid and rid in self._placed_rounds:
            self.log_message.emit("本局已下單，跳過")
            return False

        amt = int(plan["total_amount"])
        if amt <= 0:
            self.log_message.emit("計畫金額=0 略過")
            return False

        actual = self.actuator.select_chips_for_amount(amt)
        if actual <= 0:
            self.log_message.emit("拆籌碼=0 略過")
            return False

        # 下注並驗證
        success = self._place_bets_with_verification(plan["targets"])
        if not success:
            self.log_message.emit("下注失敗，取消")
            self.actuator.cancel()
            return False

        if self.dry_run:
            self.log_message.emit("[DRY] 不按『確定』")
            # 即使是乾跑也要記錄已下注，防止重複
            if rid:
                self._placed_rounds.add(rid)
            return True

        # 實戰：使用安全確認機制
        if not self._can_confirm_safely():
            self.log_message.emit("關窗臨界或時間不足 放棄送單")
            self.actuator.cancel()
            return False

        self.actuator.confirm()
        self.log_message.emit("已送單")

        # 記錄已下注的回合
        if rid:
            self._placed_rounds.add(rid)

        return True

    def _place_bets_with_verification(self, targets: Dict[str, int]) -> bool:
        """下注並驗證，支持重試機制"""
        max_retries = (self.strategy.get("limits", {}).get("max_retries", 1))

        for tgt, units in targets.items():
            units = int(units)
            if units <= 0:
                continue

            for attempt in range(max_retries + 1):
                # 下注
                for _ in range(units):
                    self.actuator.bet_on(tgt)

                # 驗證（乾跑模式跳過驗證）
                if self.dry_run or self.actuator.verify_stack(tgt):
                    self.log_message.emit(f"在 {tgt} 下注 {units} 單位 成功")
                    break
                else:
                    self.log_message.emit(f"在 {tgt} 下注驗證失敗 (嘗試 {attempt + 1}/{max_retries + 1})")
                    if attempt < max_retries:
                        # 重試前稍微等待
                        time.sleep(0.1)
                    else:
                        self.log_message.emit(f"在 {tgt} 下注最終失敗，放棄")
                        return False

        return True

    # util
    def _set_state(self, s: str):
        if self.state != s:
            self.state = s
            self.state_changed.emit(s)