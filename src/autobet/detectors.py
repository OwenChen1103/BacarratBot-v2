# src/autobet/detectors.py
import logging, pyautogui
import numpy as np
import cv2
import time
from typing import Dict, List, Tuple, Optional
from collections import deque
from enum import Enum
import os

logger = logging.getLogger(__name__)

# 確認載入檔案位置
logger.warning("detectors.py LOADED from: %s", __file__)

class OverlayDetector:
    def __init__(self, ui_cfg: Dict, positions: Dict):
        self.ui = ui_cfg or {}
        self.pos = positions or {}
        self._last_state = False
        self._streak = 0

        # 優先從 positions 的 overlay_params 讀取配置，否則回退到 ui
        overlay_params = self.pos.get("overlay_params", {})
        ui_overlay = self.ui.get("overlay", {})
        self._need = int(overlay_params.get("consecutive_required", ui_overlay.get("consecutive_required", 2)))

    def overlay_is_open(self) -> bool:
        # 優先從 positions 的 overlay_params 讀取配置
        overlay_params = self.pos.get("overlay_params", {})
        ui_overlay = self.ui.get("overlay", {})

        roi = self.pos.get("roi", {}).get("overlay", None)
        if not roi:
            logger.warning("overlay ROI missing")
            return False
        x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
        shot = pyautogui.screenshot(region=(x, y, w, h))
        arr = np.array(shot)
        gray = (0.299*arr[:,:,0] + 0.587*arr[:,:,1] + 0.114*arr[:,:,2]).astype(np.float32)
        mean = float(np.mean(gray))

        # 使用 overlay_params 或回退到 ui 配置
        open_lt = float(overlay_params.get("gray_open_lt", ui_overlay.get("gray_open_lt", 120.0)))
        cur = (mean < open_lt)  # 較暗＝下注開放
        if cur == self._last_state:
            self._streak += 1
        else:
            self._streak = 1
            self._last_state = cur
        
        result = cur and self._streak >= self._need
        
        # 添加調試日誌（每50次檢測記錄一次，避免日誌過多）
        if not hasattr(self, '_debug_counter'):
            self._debug_counter = 0
        self._debug_counter += 1
        
        if self._debug_counter % 50 == 0:  # 每50次記錄一次
            logger.info(f"Overlay檢測: mean={mean:.1f}, threshold={open_lt}, cur={cur}, streak={self._streak}/{self._need}, result={result}")
        
        return result


class OverlayPhase(str, Enum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    DEALING = "dealing"
    RESULT = "result"
    UNKNOWN = "unknown"


class RobustOverlayDetector:
    """
    強化的覆蓋層檢測器
    實現 HSV 顏色閘控、字形匹配（邊緣 NCC + Dice）、滯後決策
    """

    def __init__(self, config: Dict):
        self.config = config

        # 滯後參數
        self.open_threshold = config.get("open_threshold", 0.55)
        self.close_threshold = config.get("close_threshold", 0.45)
        self.k_open = config.get("k_open", 2)
        self.k_close = config.get("k_close", 2)

        # 多尺度參數
        self.scales = config.get("scales", [0.9, 1.0, 1.1, 1.2])

        # ROI 設定
        self.overlay_roi = None
        self.timer_roi = None

        # 模板快取（一次性預處理）
        self.template_cache = {}  # {name: {"gray": ..., "edge": ..., "mask": ...}}

        # 狀態計數器
        self.open_counter = 0
        self.close_counter = 0
        self.current_state = "UNKNOWN"

        # 歷史記錄（用於閃爍檢測）
        self.v_history = deque(maxlen=int(1.2 * 1000 / 120))  # 1.2s @ 120ms

        # HSV 顏色閘控閾值
        self.color_gates = {
            "GREEN": {"hue_range": (90, 150), "s_min": 0.35},
            "PINK": {"hue_range": (300, 360, 0, 15), "s_min": 0.35},
            "RED": {"hue_range": (0, 15), "s_min": 0.55},
            "ORANGE": {"hue_range": (20, 40), "s_min": 0.45}
        }

    def set_rois(self, overlay_roi: Dict, timer_roi: Dict):
        """設定 ROI 區域"""
        self.overlay_roi = overlay_roi
        self.timer_roi = timer_roi

    def load_templates(self, qing_path: str, jie_path: str, fa_path: str):
        """載入字模板並預處理（一次性建構邊緣、遮罩）"""
        template_paths = {
            "請": qing_path,
            "結": jie_path,
            "將結": jie_path,  # 使用同一個模板
            "發牌": fa_path
        }

        for name, path in template_paths.items():
            if path and os.path.exists(path):
                try:
                    # 載入原始模板（BGR 或 BGRA）
                    tpl_bgr = cv2.imread(path, cv2.IMREAD_COLOR)
                    if tpl_bgr is None:
                        logger.warning(f"Failed to load template: {path}")
                        continue

                    # 轉換為 HSV 並建構遮罩
                    tpl_hsv = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2HSV)
                    s_norm = tpl_hsv[:, :, 1] / 255.0
                    v_norm = tpl_hsv[:, :, 2] / 255.0

                    # 建構遮罩：S < 0.22 & V > 0.85 -> 白色/背景
                    white_mask = (s_norm < 0.22) & (v_norm > 0.85)
                    tpl_mask = (~white_mask).astype(np.uint8) * 255

                    # 形態學開運算
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                    tpl_mask = cv2.morphologyEx(tpl_mask, cv2.MORPH_OPEN, kernel)

                    # 轉換為灰階並計算邊緣
                    tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
                    tpl_edge = cv2.Canny(tpl_gray, 80, 160)

                    # 快取預處理結果
                    self.template_cache[name] = {
                        "gray": tpl_gray,
                        "edge": tpl_edge,
                        "mask": tpl_mask
                    }

                    logger.info(f"Loaded and cached template: {name}")

                except Exception as e:
                    logger.error(f"Error loading template {name}: {e}")

    def extract_roi(self, frame: np.ndarray, roi: Dict) -> Optional[np.ndarray]:
        """從幀中提取 ROI 區域（ORIGINAL 幀，無縮放）"""
        if not roi:
            return None

        h, w = frame.shape[:2]
        x, y, rw, rh = roi["x"], roi["y"], roi["w"], roi["h"]

        # 邊界檢查
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        rw = max(1, min(rw, w - x))
        rh = max(1, min(rh, h - y))

        return frame[y:y+rh, x:x+rw]

    def calculate_hsv_stats(self, roi_bgr: np.ndarray) -> Dict:
        """計算 HSV 統計信息（h_deg 在 0..360）"""
        if roi_bgr is None or roi_bgr.size == 0:
            return {"h_deg": 0, "s_mean": 0, "v_mean": 0}

        # 轉換為 HSV
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)

        # 計算統計值
        h_channel = hsv[:, :, 0]  # 0-179
        s_channel = hsv[:, :, 1] / 255.0  # 0-1
        v_channel = hsv[:, :, 2] / 255.0  # 0-1

        # Hue 平均值（轉換為 0-360 度）
        h_deg = float(np.mean(h_channel) * 2)
        s_mean = float(np.mean(s_channel))
        v_mean = float(np.mean(v_channel))

        return {
            "h_deg": h_deg,
            "s_mean": s_mean,
            "v_mean": v_mean
        }

    def apply_color_gate(self, h_deg: float, s_mean: float) -> List[str]:
        """應用顏色閘控，返回候選模板列表"""
        candidates = []

        # GREEN 閘控：請
        if 90 <= h_deg <= 150 and s_mean > 0.35:
            candidates.append("請")

        # PINK 閘控：將結
        if ((300 <= h_deg < 360) or (0 <= h_deg <= 15)) and s_mean > 0.35:
            candidates.extend(["將結", "結"])

        # RED 閘控：結束
        if 0 <= h_deg <= 15 and s_mean > 0.55:
            candidates.append("結")

        # ORANGE 閘控：發牌
        if 20 <= h_deg <= 40 and s_mean > 0.45:
            candidates.append("發牌")

        return candidates

    def evaluate_candidate(self, roi_bgr: np.ndarray, candidate: str) -> Tuple[float, float, float]:
        """評估單個候選者：返回 (edge_ncc, dice, score)"""
        if candidate not in self.template_cache:
            return 0.0, 0.0, 0.0

        try:
            # ROI 預處理
            roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
            roi_edge = cv2.Canny(roi_gray, 80, 160)

            # ROI 遮罩（同樣的白色檢測規則）
            roi_hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
            s_norm = roi_hsv[:, :, 1] / 255.0
            v_norm = roi_hsv[:, :, 2] / 255.0
            white_mask = (s_norm < 0.22) & (v_norm > 0.85)
            roi_mask = (~white_mask).astype(np.uint8) * 255
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            roi_mask = cv2.morphologyEx(roi_mask, cv2.MORPH_OPEN, kernel)

            # 取得模板
            tpl_data = self.template_cache[candidate]

            best_edge_ncc = 0.0
            best_dice = 0.0

            # 多尺度匹配
            for scale in self.scales:
                # 縮放模板
                tpl_gray = tpl_data["gray"]
                tpl_edge = tpl_data["edge"]
                tpl_mask = tpl_data["mask"]

                if scale != 1.0:
                    h, w = tpl_gray.shape
                    new_h, new_w = int(h * scale), int(w * scale)
                    if new_h <= 0 or new_w <= 0:
                        continue
                    tpl_gray_scaled = cv2.resize(tpl_gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    tpl_edge_scaled = cv2.resize(tpl_edge, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    tpl_mask_scaled = cv2.resize(tpl_mask, (new_w, new_h), interpolation=cv2.INTER_AREA)
                else:
                    tpl_edge_scaled = tpl_edge
                    tpl_mask_scaled = tpl_mask

                # 檢查尺寸
                if (tpl_edge_scaled.shape[0] > roi_edge.shape[0] or
                    tpl_edge_scaled.shape[1] > roi_edge.shape[1]):
                    continue

                # 邊緣 NCC（帶遮罩）
                if np.sum(tpl_mask_scaled) > 0:
                    ncc_result = cv2.matchTemplate(
                        roi_edge, tpl_edge_scaled, cv2.TM_CCORR_NORMED, mask=tpl_mask_scaled
                    )
                    _, max_ncc, _, best_loc = cv2.minMaxLoc(ncc_result)

                    if max_ncc > best_edge_ncc:
                        best_edge_ncc = max_ncc

                        # 在最佳位置計算 Dice
                        y, x = best_loc[1], best_loc[0]
                        h_tpl, w_tpl = tpl_mask_scaled.shape
                        roi_patch = roi_mask[y:y+h_tpl, x:x+w_tpl]

                        if roi_patch.shape == tpl_mask_scaled.shape:
                            intersection = np.sum((roi_patch > 0) & (tpl_mask_scaled > 0))
                            union = np.sum(roi_patch > 0) + np.sum(tpl_mask_scaled > 0) + 1e-6
                            dice = 2.0 * intersection / union
                            best_dice = max(best_dice, dice)

            # 組合分數：60% 邊緣 NCC + 40% Dice
            score = 0.6 * best_edge_ncc + 0.4 * best_dice
            return best_edge_ncc, best_dice, score

        except Exception as e:
            logger.error(f"Error evaluating candidate {candidate}: {e}")
            return 0.0, 0.0, 0.0

    def calculate_flicker(self, v_mean: float) -> float:
        """計算閃爍度並維護 V 均值歷史"""
        self.v_history.append(v_mean)

        if len(self.v_history) < 3:
            return 0.0

        values = np.array(self.v_history)

        # 可選：FFT 分析主頻率
        if len(values) >= 10:
            try:
                # 基礎閃爍檢測：變異係數
                mean_val = np.mean(values)
                std_val = np.std(values)
                if mean_val > 0:
                    return float(std_val / mean_val)
            except:
                pass

        return 0.0

    def check_timer_presence(self, frame: np.ndarray) -> Tuple[bool, float]:
        """檢查計時器是否存在"""
        timer_roi = self.extract_roi(frame, self.timer_roi)
        if timer_roi is None:
            return False, 0.0

        try:
            # 轉換為灰階並二值化
            gray = cv2.cvtColor(timer_roi, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

            # 計算白像素比例
            total_pixels = binary.size
            white_pixels = np.sum(binary == 255)
            white_ratio = white_pixels / total_pixels

            # 判斷是否在範圍內（從配置中取得）
            timer_white_range = self.config.get("timer_white_range", [0.03, 0.20])
            min_ratio, max_ratio = timer_white_range
            timer_present = min_ratio <= white_ratio <= max_ratio

            return timer_present, float(white_ratio)

        except Exception as e:
            logger.error(f"Timer detection error: {e}")
            return False, 0.0

    def make_decision(self, best_candidate: str, best_score: float, color_gate: str) -> str:
        """滯後決策邏輯"""
        # 判斷是否滿足 OPEN 條件
        open_condition = (
            color_gate == "GREEN" and
            best_candidate == "請" and
            best_score >= self.open_threshold
        )

        # 判斷是否滿足 CLOSE 條件
        close_condition = (
            color_gate != "GREEN" or
            best_score < self.close_threshold
        )

        # 更新計數器
        if open_condition:
            self.open_counter += 1
            self.close_counter = 0
        elif close_condition:
            self.close_counter += 1
            self.open_counter = 0
        else:
            # 既不滿足開啟也不滿足關閉，維持計數器
            pass

        # 狀態轉換
        if self.open_counter >= self.k_open:
            self.current_state = "OPEN"
        elif self.close_counter >= self.k_close:
            self.current_state = "CLOSED"
        else:
            self.current_state = "UNKNOWN"

        return self.current_state

    def determine_color_gate(self, h_deg: float, s_mean: float) -> str:
        """決定顏色閘控類型"""
        if 90 <= h_deg <= 150 and s_mean > 0.35:
            return "GREEN"
        elif ((300 <= h_deg < 360) or (0 <= h_deg <= 15)) and s_mean > 0.35:
            return "PINK"
        elif 0 <= h_deg <= 15 and s_mean > 0.55:
            return "RED"
        elif 20 <= h_deg <= 40 and s_mean > 0.45:
            return "ORANGE"
        else:
            return "NONE"

    def process_frame(self, frame_bgr: np.ndarray) -> Dict:
        """處理單幀並返回檢測結果"""
        try:
            # 提取 Overlay ROI（ORIGINAL 幀）
            overlay_roi = self.extract_roi(frame_bgr, self.overlay_roi)
            if overlay_roi is None:
                return self._empty_result("Overlay ROI is None")

            # 計算 HSV 統計
            hsv_stats = self.calculate_hsv_stats(overlay_roi)
            h_deg = hsv_stats["h_deg"]
            s_mean = hsv_stats["s_mean"]
            v_mean = hsv_stats["v_mean"]

            # 顏色閘控
            color_gate = self.determine_color_gate(h_deg, s_mean)
            candidates = self.apply_color_gate(h_deg, s_mean)

            # 評估候選者
            best_candidate = "None"
            best_score = 0.0
            best_edge_ncc = 0.0
            best_dice = 0.0

            for candidate in candidates:
                edge_ncc, dice, score = self.evaluate_candidate(overlay_roi, candidate)
                if score > best_score:
                    best_score = score
                    best_candidate = candidate
                    best_edge_ncc = edge_ncc
                    best_dice = dice

            # 計算閃爍
            flicker_cv = self.calculate_flicker(v_mean)

            # 滯後決策
            decision = self.make_decision(best_candidate, best_score, color_gate)

            # 生成決策理由
            reason = self._generate_reason(color_gate, best_candidate, best_score, candidates)

            return {
                "h_deg": h_deg,
                "s_mean": s_mean,
                "v_mean": v_mean,
                "color_gate": color_gate,
                "candidates": candidates,
                "best_candidate": best_candidate,
                "best_score": best_score,
                "edge_ncc": best_edge_ncc,
                "dice": best_dice,
                "flicker_cv": flicker_cv,
                "decision": decision,
                "reason": reason,
                "open_counter": f"{self.open_counter}/{self.k_open}",
                "close_counter": f"{self.close_counter}/{self.k_close}",
                # 向後兼容的欄位
                "phase_smooth": decision,
                "hue_mode": h_deg,
                "sat_mean": s_mean,
                "val_mean": v_mean
            }

        except Exception as e:
            logger.error(f"Frame processing error: {e}")
            return self._empty_result(str(e))

    def _empty_result(self, reason: str) -> Dict:
        """返回空結果"""
        return {
            "h_deg": 0,
            "s_mean": 0,
            "v_mean": 0,
            "color_gate": "NONE",
            "candidates": [],
            "best_candidate": "None",
            "best_score": 0.0,
            "edge_ncc": 0.0,
            "dice": 0.0,
            "flicker_cv": 0.0,
            "decision": "UNKNOWN",
            "reason": reason,
            "open_counter": f"{self.open_counter}/{self.k_open}",
            "close_counter": f"{self.close_counter}/{self.k_close}",
            "phase_smooth": "UNKNOWN",
            "hue_mode": 0,
            "sat_mean": 0,
            "val_mean": 0
        }

    def _generate_reason(self, color_gate: str, best_candidate: str, best_score: float, candidates: List[str]) -> str:
        """生成決策理由"""
        if color_gate == "NONE":
            return "Hue not in any gate range"
        elif not candidates:
            return f"Gate={color_gate} but no candidates"
        elif best_score < self.close_threshold:
            return f"best_score={best_score:.2f}<close_th={self.close_threshold}"
        elif best_candidate == "請" and color_gate == "GREEN" and best_score >= self.open_threshold:
            return f"GREEN gate + 請 + score={best_score:.2f}≥open_th={self.open_threshold}"
        else:
            return f"Gate={color_gate}, best={best_candidate}, score={best_score:.2f}"


class ProductionOverlayDetector:
    """
    落地版覆蓋層檢測器
    專注於穩定的 OPEN/CLOSED 判斷，使用雙閾值+連續幀+色彩護欄
    """

    def __init__(self, config: Dict):
        self.config = config

        # 核心閾值（可配置）
        self.open_th = config.get("open_threshold", 0.70)  # NCC_請 閾值
        self.close_th = config.get("close_threshold", 0.45)  # 關閉閾值
        self.k_open = config.get("k_open", 5)  # 連續5幀才開啟
        self.k_close = config.get("k_close", 3)  # 連續3幀才關閉

        # 色彩護欄（GREEN 區間）
        self.green_hue_range = config.get("green_hue_range", [90, 150])
        self.green_sat_min = config.get("green_sat_min", 0.45)
        self.green_val_min = config.get("green_val_min", 0.55)

        # 安全策略
        self.max_open_wait_ms = config.get("max_open_wait_ms", 8000)  # 8秒無OPEN自動跳過
        self.cancel_on_close = config.get("cancel_on_close", True)

        # ROI
        self.overlay_roi = None
        self.timer_roi = None

        # 模板快取（僅「請」字）
        self.qing_templates = []  # 可存多個「請」的變種

        # 狀態
        self.current_state = "UNKNOWN"  # UNKNOWN, OPEN, CLOSED
        self.open_counter = 0
        self.close_counter = 0
        self.last_open_time = 0

        # 檢測歷史（供 UI 顯示）
        self.last_ncc_qing = 0.0
        self.last_hue = 0.0
        self.last_sat = 0.0
        self.last_val = 0.0
        self.last_in_green_gate = False

    def set_rois(self, overlay_roi: Dict, timer_roi: Dict):
        """設定 ROI 區域"""
        self.overlay_roi = overlay_roi
        self.timer_roi = timer_roi

    def load_qing_template(self, template_path: str):
        """載入「請」字模板"""
        if not template_path or not os.path.exists(template_path):
            logger.warning(f"Template not found: {template_path}")
            return

        try:
            # 載入並預處理模板
            tpl_bgr = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if tpl_bgr is None:
                return

            # 轉為灰階並增強對比度
            tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
            tpl_gray = cv2.equalizeHist(tpl_gray)  # 標準化亮度

            # 輕度模糊去噪
            tpl_gray = cv2.GaussianBlur(tpl_gray, (3, 3), 0.5)

            self.qing_templates.append(tpl_gray)
            logger.info(f"Loaded qing template: {template_path}")

        except Exception as e:
            logger.error(f"Error loading qing template: {e}")

    def extract_roi(self, frame: np.ndarray, roi: Dict) -> Optional[np.ndarray]:
        """提取 ROI 區域"""
        if not roi:
            return None

        h, w = frame.shape[:2]
        x, y, rw, rh = roi["x"], roi["y"], roi["w"], roi["h"]

        # 邊界檢查
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        rw = max(1, min(rw, w - x))
        rh = max(1, min(rh, h - y))

        return frame[y:y+rh, x:x+rw]

    def check_green_gate(self, roi_bgr: np.ndarray) -> Tuple[bool, float, float, float]:
        """檢查是否在 GREEN 色彩護欄內"""
        if roi_bgr is None or roi_bgr.size == 0:
            return False, 0.0, 0.0, 0.0

        try:
            # 轉換為 HSV
            hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)

            # 計算平均值
            h_channel = hsv[:, :, 0] * 2  # 轉為 0-360 度
            s_channel = hsv[:, :, 1] / 255.0
            v_channel = hsv[:, :, 2] / 255.0

            h_mean = float(np.mean(h_channel))
            s_mean = float(np.mean(s_channel))
            v_mean = float(np.mean(v_channel))

            # 檢查是否在 GREEN 區間
            h_min, h_max = self.green_hue_range
            in_green = (h_min <= h_mean <= h_max and
                       s_mean >= self.green_sat_min and
                       v_mean >= self.green_val_min)

            return in_green, h_mean, s_mean, v_mean

        except Exception as e:
            logger.error(f"Green gate check error: {e}")
            return False, 0.0, 0.0, 0.0

    def calculate_ncc_qing(self, roi_bgr: np.ndarray) -> float:
        """計算「請」字 NCC 分數"""
        if roi_bgr is None or roi_bgr.size == 0 or not self.qing_templates:
            return 0.0

        try:
            # ROI 預處理（與模板相同）
            roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
            roi_gray = cv2.equalizeHist(roi_gray)
            roi_gray = cv2.GaussianBlur(roi_gray, (3, 3), 0.5)

            max_ncc = 0.0

            # 測試所有「請」模板
            for template in self.qing_templates:
                # 多尺度匹配（±8%）
                for scale in [0.92, 1.0, 1.08]:
                    if scale != 1.0:
                        h, w = template.shape
                        new_h, new_w = int(h * scale), int(w * scale)
                        if new_h <= 0 or new_w <= 0 or new_h > roi_gray.shape[0] or new_w > roi_gray.shape[1]:
                            continue
                        scaled_template = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    else:
                        scaled_template = template

                    # 檢查尺寸
                    if (scaled_template.shape[0] > roi_gray.shape[0] or
                        scaled_template.shape[1] > roi_gray.shape[1]):
                        continue

                    # NCC 匹配
                    result = cv2.matchTemplate(roi_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
                    _, ncc_val, _, _ = cv2.minMaxLoc(result)

                    max_ncc = max(max_ncc, ncc_val)

            return float(max_ncc)

        except Exception as e:
            logger.error(f"NCC calculation error: {e}")
            return 0.0

    def process_frame(self, frame_bgr: np.ndarray) -> Dict:
        """處理單幀並更新狀態"""
        try:
            # 提取 Overlay ROI
            overlay_roi = self.extract_roi(frame_bgr, self.overlay_roi)
            if overlay_roi is None:
                return self._empty_result("Overlay ROI is None")

            # 色彩護欄檢查
            in_green, h_mean, s_mean, v_mean = self.check_green_gate(overlay_roi)

            # NCC_請 計算
            ncc_qing = self.calculate_ncc_qing(overlay_roi)

            # 記錄供 UI 顯示
            self.last_ncc_qing = ncc_qing
            self.last_hue = h_mean
            self.last_sat = s_mean
            self.last_val = v_mean
            self.last_in_green_gate = in_green

            # 決策邏輯
            open_hit = (in_green and ncc_qing >= self.open_th)
            close_hit = (not in_green or ncc_qing < self.close_th)

            # 更新計數器
            if open_hit:
                self.open_counter += 1
                self.close_counter = 0
            elif close_hit:
                self.close_counter += 1
                self.open_counter = 0
            else:
                # 既不滿足開啟也不滿足關閉，維持現狀但不重置計數器
                pass

            # 狀態轉換
            prev_state = self.current_state

            if self.open_counter >= self.k_open:
                self.current_state = "OPEN"
                if prev_state != "OPEN":
                    self.last_open_time = time.time() * 1000  # 記錄開啟時間

            elif self.close_counter >= self.k_close:
                self.current_state = "CLOSED"

            # 超時保護：太久沒看到 OPEN 就認為是 CLOSED
            current_time = time.time() * 1000
            if (self.current_state == "UNKNOWN" and
                self.last_open_time > 0 and
                current_time - self.last_open_time > self.max_open_wait_ms):
                self.current_state = "CLOSED"
                logger.info(f"Overlay timeout protection: UNKNOWN -> CLOSED after {self.max_open_wait_ms}ms")

            # 生成決策理由
            reason = self._generate_reason(in_green, ncc_qing, open_hit, close_hit)

            return {
                "decision": self.current_state,
                "ncc_qing": ncc_qing,
                "hue": h_mean,
                "sat": s_mean,
                "val": v_mean,
                "in_green_gate": in_green,
                "open_hit": open_hit,
                "close_hit": close_hit,
                "open_counter": f"{self.open_counter}/{self.k_open}",
                "close_counter": f"{self.close_counter}/{self.k_close}",
                "reason": reason,
                "is_open": self.current_state == "OPEN",  # 供引擎直接使用
                # 向後兼容
                "phase_smooth": self.current_state.lower(),
                "hue_mode": h_mean,
                "sat_mean": s_mean,
                "val_mean": v_mean
            }

        except Exception as e:
            logger.error(f"Frame processing error: {e}")
            return self._empty_result(str(e))

    def overlay_is_open(self) -> bool:
        """引擎直接調用的介面"""
        return self.current_state == "OPEN"

    def _empty_result(self, reason: str) -> Dict:
        """返回空結果"""
        return {
            "decision": "UNKNOWN",
            "ncc_qing": 0.0,
            "hue": 0.0,
            "sat": 0.0,
            "val": 0.0,
            "in_green_gate": False,
            "open_hit": False,
            "close_hit": False,
            "open_counter": f"{self.open_counter}/{self.k_open}",
            "close_counter": f"{self.close_counter}/{self.k_close}",
            "reason": reason,
            "is_open": False,
            "phase_smooth": "unknown",
            "hue_mode": 0.0,
            "sat_mean": 0.0,
            "val_mean": 0.0
        }

    def _generate_reason(self, in_green: bool, ncc_qing: float, open_hit: bool, close_hit: bool) -> str:
        """生成決策理由"""
        if open_hit:
            return f"GREEN_gate + NCC_請={ncc_qing:.2f}≥{self.open_th}"
        elif close_hit:
            if not in_green:
                return f"Hue not in GREEN range [{self.green_hue_range[0]},{self.green_hue_range[1]}]"
            else:
                return f"NCC_請={ncc_qing:.2f}<{self.close_th}"
        else:
            return f"NCC_請={ncc_qing:.2f} in transition zone"


class OverlayDetectorWrapper:
    """
    包裝器讓 ProductionOverlayDetector 與引擎的舊接口兼容
    """
    def __init__(self, ui_cfg: Dict, positions: Dict):
        self.ui = ui_cfg or {}
        self.pos = positions or {}

        # 1) 安全預設值 (優化為更快響應)
        defaults = {
            "open_threshold": 0.70,
            "close_threshold": 0.45,
            "k_open": 2,    # 從5降到2，加快可下注檢測
            "k_close": 2,   # 從3降到2，保持一致性
            "green_hue_range": [90, 150],  # 與 ProductionOverlayDetector 一致
            "green_sat_min": 0.45,
            "green_val_min": 0.55,
            "max_open_wait_ms": 8000,
            "cancel_on_close": True,
        }

        # 2) 從 ui.yaml / positions.json 讀取（誰有就用誰）
        ui_overlay = (self.ui or {}).get("overlay", {})              # 例如 ui.yaml 的 overlay.*
        pos_params = (self.pos or {}).get("overlay_params", {})      # 例如 positions.json 裡 overlay_params
        pos_thresh = pos_params.get("thresholds", {})                # 例如 {"open_threshold": 0.72, ...}

        # 兼容舊參數名稱映射
        legacy_mapping = {
            "ncc_threshold": "open_threshold",
            "consecutive_required": "k_open",
        }

        for old_name, new_name in legacy_mapping.items():
            if old_name in pos_params and new_name not in pos_thresh:
                pos_thresh[new_name] = pos_params[old_name]

        # 3) 合併：defaults <- ui <- positions
        cfg = {**defaults, **ui_overlay, **pos_thresh}

        try:
            self.detector = ProductionOverlayDetector(cfg)
            logger.info(
                "Overlay cfg: open_th=%.2f, close_th=%.2f, k_open=%d, k_close=%d, green=%s",
                cfg["open_threshold"], cfg["close_threshold"], cfg["k_open"], cfg["k_close"], cfg["green_hue_range"]
            )
        except Exception as e:
            logger.error(f"Failed to create ProductionOverlayDetector: {e}")
            # 創建一個簡單的 fallback 檢測器
            self.detector = self._create_fallback_detector()

        # 設定 ROI
        overlay_roi = self.pos.get("roi", {}).get("overlay", None)
        timer_roi = self.pos.get("roi", {}).get("timer", None)

        if overlay_roi and timer_roi:
            self.detector.set_rois(overlay_roi, timer_roi)

        # 載入模板（如果存在）
        overlay_params = self.pos.get("overlay_params", {})
        template_paths = overlay_params.get("template_paths", {})
        qing_path = template_paths.get("qing")

        if qing_path:
            self.detector.load_qing_template(qing_path)

        # 啟動檢測（模擬舊版行為）
        from time import monotonic
        self._last_frame_time = 0.0
        # 使用與EngineWorker相容的節拍，避免雙重節流
        frame_interval_ms = ui_overlay.get("timer_interval_ms", 150)  # 調整為150ms，減少檢測頻率
        self._frame_interval = frame_interval_ms / 1000.0

    def _clamp_roi(self, roi):
        """夾住ROI到螢幕邊界內"""
        import pyautogui
        sw, sh = pyautogui.size()
        x = max(0, min(roi["x"], sw - 1))
        y = max(0, min(roi["y"], sh - 1))
        w = max(1, min(roi["w"], sw - x))
        h = max(1, min(roi["h"], sh - y))
        return {"x": x, "y": y, "w": w, "h": h}

    def _create_fallback_detector(self):
        """創建簡單的回退檢測器"""
        class FallbackDetector:
            def overlay_is_open(self):
                return False
            def process_frame(self, frame):
                return {"is_open": False, "decision": "UNKNOWN"}
        return FallbackDetector()

    def health_check(self) -> tuple:
        """截圖健康檢查"""
        try:
            import pyautogui
            img = pyautogui.screenshot(region=(0, 0, 1, 1))
            return (img is not None), ""
        except Exception as e:
            return False, f"screenshot permission/compat error: {e}"

    def overlay_is_open(self) -> bool:
        """引擎調用的主要接口"""
        try:
            from time import monotonic, perf_counter
            t0 = perf_counter()

            current_time = monotonic()

            # 控制檢測頻率（避免過度頻繁）
            if current_time - self._last_frame_time < self._frame_interval:
                # 太頻繁，直接返回上次狀態
                try:
                    result = getattr(self, '_last_decision', False)
                    return result
                except Exception as e:
                    logger.warning(f"Detector overlay_is_open failed: {e}")
                    return False

            self._last_frame_time = current_time

            # 截取當前畫面並處理
            roi = self.pos.get("roi", {}).get("overlay", None)
            if not roi:
                logger.warning("overlay_is_open: overlay ROI missing")
                return False

            # 夾住ROI到螢幕邊界內
            roi = self._clamp_roi(roi)

            x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
            shot = pyautogui.screenshot(region=(x, y, w, h))
            arr = np.array(shot)

            # 轉換為 BGR 格式
            if arr.shape[2] == 4:  # RGBA
                frame_bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            else:  # RGB
                frame_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

            # 處理整個螢幕幀（不只是 ROI）
            full_shot = pyautogui.screenshot()
            full_arr = np.array(full_shot)
            if full_arr.shape[2] == 4:
                full_frame = cv2.cvtColor(full_arr, cv2.COLOR_RGBA2BGR)
            else:
                full_frame = cv2.cvtColor(full_arr, cv2.COLOR_RGB2BGR)

            # 處理幀並更新狀態
            result = self.detector.process_frame(full_frame)

            is_open = result.get("is_open", False)
            self._last_decision = is_open  # 儲存決策供下次快取使用

            # 釋放記憶體
            del full_frame, full_arr, shot, arr

            # 延遲量測日誌
            wrapper_ms = (perf_counter() - t0) * 1000
            if wrapper_ms > 50:  # 只記錄較慢的檢測
                logger.debug(f"wrapper_ms={wrapper_ms:.1f}")

            return is_open

        except Exception as e:
            logger.error(f"OverlayDetectorWrapper error: {e}", exc_info=True)
            return False


# 向後兼容：讓引擎使用新的包裝器
OverlayDetector = OverlayDetectorWrapper
OverlayMVPDetector = RobustOverlayDetector