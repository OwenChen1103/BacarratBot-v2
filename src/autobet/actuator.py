# src/autobet/actuator.py
import time, random, logging, pyautogui
from typing import Dict, Tuple, List

logger = logging.getLogger(__name__)

class Actuator:
    def __init__(self, positions: Dict, ui_cfg: Dict, dry_run: bool = True, log_callback=None):
        self.pos = positions or {}
        self.ui = ui_cfg or {}
        self.dry = bool(dry_run)
        self.log_callback = log_callback  # 用於發送日誌到 UI
        pyautogui.FAILSAFE = True

    def _click_point(self, name: str) -> bool:
        pt = self.pos.get("points", {}).get(name)
        if not pt:
            logger.error(f"point missing: {name}")
            return False
        x, y = pt["x"], pt["y"]
        jitter = int(self.ui.get("click", {}).get("jitter_px", 2))
        rx = x + random.randint(-jitter, jitter)
        ry = y + random.randint(-jitter, jitter)

        mv = self.ui.get("click", {}).get("move_delay_ms", [40, 120])
        ck = self.ui.get("click", {}).get("click_delay_ms", [40, 80])

        # 乾跑模式使用極短延遲，避免卡住UI
        if self.dry:
            md = 0.02  # 20ms duration，避免過快但不阻塞
            cd = 0.02  # 20ms click delay
        else:
            md = random.randint(int(mv[0]), int(mv[1]))/1000.0
            cd = random.randint(int(ck[0]), int(ck[1]))/1000.0

        if self.dry:
            log_msg = f"移動滑鼠到 {name} -> ({rx},{ry}) [不點擊]"
            logger.info(log_msg)
            if self.log_callback:
                self.log_callback("INFO", "Actuator", log_msg)
            pyautogui.moveTo(rx, ry, duration=md)  # 乾跑使用快速移動
            time.sleep(cd)
            return True
        else:
            log_msg = f"移動滑鼠到 {name} -> ({rx},{ry}) 並點擊"
            logger.info(log_msg)
            if self.log_callback:
                self.log_callback("INFO", "Actuator", log_msg)
            pyautogui.moveTo(rx, ry, duration=md)
            pyautogui.click()
            time.sleep(cd)
            return True

    def click_chip_value(self, value: int) -> bool:
        name = f"chip_{value//1000}k" if value >= 1000 else f"chip_{value}"
        # 特殊處理：1000 => chip_1k, 100 => chip_100, 5000 => chip_5k...
        mapping = {
            100: "chip_100", 1000: "chip_1k", 5000: "chip_5k",
            10000: "chip_10k", 50000: "chip_50k"
        }
        key = mapping.get(value, name)
        return self._click_point(key)

    def click_bet(self, target: str) -> bool:
        return self._click_point(target)

    def confirm(self) -> bool:
        guard_ms = int(self.ui.get("safety", {}).get("pre_confirm_guard_ms", 120))
        time.sleep(guard_ms/1000.0)
        return self._click_point("confirm")

    def cancel(self) -> bool:
        return self._click_point("cancel")

    def dry_click_point(self, x: int, y: int, label: str = "") -> bool:
        """Dry-run 點擊指定座標（僅記錄，不實際點擊）"""
        jitter = int(self.ui.get("click", {}).get("jitter_px", 2))
        rx = x + random.randint(-jitter, jitter)
        ry = y + random.randint(-jitter, jitter)

        mv = self.ui.get("click", {}).get("move_delay_ms", [40, 120])
        cd = random.randint(int(mv[0]), int(mv[1]))/1000.0

        label_text = f" ({label})" if label else ""
        log_msg = f"移動滑鼠到{label_text} -> ({rx},{ry})"
        logger.info(f"[測試] {log_msg}")
        if self.log_callback:
            self.log_callback("INFO", "Actuator", log_msg)
        time.sleep(cd)  # 模擬點擊延遲
        return True

    def dry_click_key(self, key_name: str) -> bool:
        """Dry-run 點擊指定按鍵"""
        pt = self.pos.get("points", {}).get(key_name)
        if not pt:
            logger.error(f"[DRY] point missing: {key_name}")
            return False
        return self.dry_click_point(pt["x"], pt["y"], key_name)

    def move_to(self, x: int, y: int) -> bool:
        """移動游標到指定座標（不點擊）"""
        jitter = int(self.ui.get("click", {}).get("jitter_px", 2))
        rx = x + random.randint(-jitter, jitter)
        ry = y + random.randint(-jitter, jitter)

        mv = self.ui.get("click", {}).get("move_delay_ms", [40, 120])
        md = random.randint(int(mv[0]), int(mv[1]))/1000.0

        if self.dry:
            log_msg = f"移動滑鼠到 ({rx},{ry})"
            logger.info(f"[僅移動] {log_msg}")
            if self.log_callback:
                self.log_callback("INFO", "Actuator", log_msg)
            time.sleep(md)
            return True
        else:
            # 多種 fallback 方式
            moved = False

            # 1) pyautogui
            try:
                pyautogui.FAILSAFE = False
                pyautogui.moveTo(rx, ry, duration=0)
                moved = True
            except Exception:
                pass

            # 2) Win32 SetCursorPos fallback
            if not moved:
                try:
                    import ctypes
                    ctypes.windll.user32.SetCursorPos(int(rx), int(ry))
                    moved = True
                except Exception as e:
                    logger.warning(f"move_to fallback failed: {e}")

            time.sleep(md)
            return moved