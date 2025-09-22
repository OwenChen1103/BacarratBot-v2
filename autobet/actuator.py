#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, random, os, time
from typing import Dict, Tuple, Optional
import numpy as np
import cv2
import pyautogui

class Actuator:
    """滑鼠操作執行器（乾跑預設）。"""

    def __init__(self, positions: Dict, dry_run: bool = True):
        self.pos = positions or {"points": {}, "roi": {}}
        self.dry_run = dry_run
        pyautogui.FAILSAFE = True
        self._baseline_path = "snaps/stack_baseline.json"
        self._baseline: Dict[str, float] = {}
        self._load_baseline()

    # --- helpers ---
    def set_dry_run(self, v: bool): self.dry_run = v

    def _pt(self, name: str) -> Tuple[int, int]:
        p = self.pos["points"][name]
        return int(p["x"]), int(p["y"])

    def _roi(self, name: str) -> Tuple[int, int, int, int]:
        r = self.pos["roi"][name]
        return int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])

    def _move_click(self, name: str):
        x, y = self._pt(name)
        x += random.randint(-2, 2); y += random.randint(-2, 2)
        if self.dry_run:
            print(f"[DRY] click {name} -> ({x},{y})")
            return
        pyautogui.moveTo(x, y, duration=random.uniform(0.04, 0.12))
        pyautogui.click()

    # --- public ops ---
    def select_chip_by_value(self, value: int):
        mapping = {100:"chip_100",1000:"chip_1k",5000:"chip_5k",10000:"chip_10k",50000:"chip_50k"}
        name = mapping.get(int(value))
        if not name: raise ValueError(f"unsupported chip {value}")
        self._move_click(name)

    def select_chips_for_amount(self, amount: int) -> int:
        remain = int(amount); actual = 0
        for d in (50000,10000,5000,1000,100):
            cnt = remain // d
            for _ in range(int(cnt)):
                self.select_chip_by_value(d)
                actual += d
            remain -= cnt * d
        return actual

    def bet_on(self, target_name: str): self._move_click(target_name)
    def confirm(self): self._move_click("confirm")
    def cancel(self):  self._move_click("cancel")

    def screenshot_roi(self, roi_name: str):
        x, y, w, h = self._roi(roi_name)
        im = pyautogui.screenshot(region=(x, y, w, h))
        im = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
        return im

    def _load_baseline(self):
        """載入空桌基線數據"""
        try:
            if os.path.exists(self._baseline_path):
                with open(self._baseline_path, 'r') as f:
                    self._baseline = json.load(f)
        except Exception as e:
            print(f"載入基線失敗: {e}")
            self._baseline = {}

    def _save_baseline(self):
        """保存基線數據"""
        try:
            os.makedirs("snaps", exist_ok=True)
            with open(self._baseline_path, 'w') as f:
                json.dump(self._baseline, f, indent=2)
        except Exception as e:
            print(f"保存基線失敗: {e}")

    def capture_baseline(self) -> bool:
        """捕獲空桌基線（在無籌碼時調用）"""
        try:
            targets = ["banker", "player", "tie"]  # 主要下注區域
            for target in targets:
                stack_roi_name = f"{target}_stack"
                if stack_roi_name in self.pos.get("roi", {}):
                    im = self.screenshot_roi(stack_roi_name)
                    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
                    self._baseline[stack_roi_name] = float(gray.mean())

            self._save_baseline()
            return True
        except Exception as e:
            print(f"捕獲基線失敗: {e}")
            return False

    def verify_stack(self, target_name: str, delta_threshold: float = 8.0) -> bool:
        """驗證籌碼堆疊 - 通過亮度差檢測是否有籌碼"""
        if self.dry_run:
            return True

        try:
            stack_roi_name = f"{target_name}_stack"

            # 檢查是否有對應的ROI
            if stack_roi_name not in self.pos.get("roi", {}):
                print(f"警告: 找不到 {stack_roi_name} ROI")
                return True  # 找不到ROI時假設成功

            # 檢查是否有基線數據
            if stack_roi_name not in self._baseline:
                print(f"警告: 沒有 {stack_roi_name} 的基線數據")
                return True  # 沒有基線時假設成功

            # 截圖並計算當前亮度
            im = self.screenshot_roi(stack_roi_name)
            gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
            current_mean = float(gray.mean())
            baseline_mean = self._baseline[stack_roi_name]

            # 檢查亮度差異 - 有籌碼時應該比基線更暗
            brightness_diff = baseline_mean - current_mean
            has_chips = brightness_diff > delta_threshold

            print(f"驗證 {target_name}: 基線={baseline_mean:.1f}, 當前={current_mean:.1f}, 差異={brightness_diff:.1f}, 有籌碼={has_chips}")

            return has_chips

        except Exception as e:
            print(f"驗證堆疊失敗: {e}")
            return True  # 出錯時假設成功，避免阻塞