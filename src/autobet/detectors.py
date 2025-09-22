# src/autobet/detectors.py
import logging, pyautogui
import numpy as np
from typing import Dict

logger = logging.getLogger(__name__)

class OverlayDetector:
    def __init__(self, ui_cfg: Dict, positions: Dict):
        self.ui = ui_cfg or {}
        self.pos = positions or {}
        self._last_state = False
        self._streak = 0
        self._need = int(self.ui.get("overlay", {}).get("consecutive_required", 2))

    def overlay_is_open(self) -> bool:
        o = self.ui.get("overlay", {})
        roi = self.pos.get("roi", {}).get("overlay", None)
        if not roi:
            logger.warning("overlay ROI missing")
            return False
        x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
        shot = pyautogui.screenshot(region=(x, y, w, h))
        arr = np.array(shot)
        gray = (0.299*arr[:,:,0] + 0.587*arr[:,:,1] + 0.114*arr[:,:,2]).astype(np.float32)
        mean = float(np.mean(gray))
        open_lt = float(o.get("gray_open_lt", 120.0))
        cur = (mean < open_lt)  # 較暗＝下注開放
        if cur == self._last_state:
            self._streak += 1
        else:
            self._streak = 1
            self._last_state = cur
        return cur and self._streak >= self._need