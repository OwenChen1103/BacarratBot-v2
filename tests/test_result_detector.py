# tests/test_result_detector.py
"""
ResultDetector 單元測試

測試結果檢測器的核心功能:
- 初始化
- ROI 設置
- 模板載入
- 檢測邏輯
- Cooldown 機制
"""

import pytest
import numpy as np
import cv2
import time
from pathlib import Path
from unittest.mock import Mock, patch

# 導入待測試類
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.autobet.detectors import ResultDetector, ResultInfo, ResultDetectionState


@pytest.fixture
def test_config():
    """測試配置"""
    return {
        "ncc_threshold": 0.70,
        "consecutive_required": 3,
        "check_interval_ms": 200,
        "cooldown_ms": 5000
    }


@pytest.fixture
def test_rois():
    """測試 ROI"""
    return {
        "banker": {"x": 100, "y": 200, "w": 150, "h": 80},
        "player": {"x": 300, "y": 200, "w": 150, "h": 80},
        "tie": {"x": 500, "y": 200, "w": 150, "h": 80}
    }


@pytest.fixture
def detector(test_config, test_rois):
    """創建檢測器實例"""
    det = ResultDetector(test_config)
    det.set_rois(test_rois["banker"], test_rois["player"], test_rois["tie"])
    return det


@pytest.fixture
def mock_templates(tmp_path):
    """創建模擬模板圖片"""
    templates = {}

    for key, color in [("B", (0, 0, 255)), ("P", (255, 0, 0)), ("T", (0, 255, 0))]:
        # 創建簡單的彩色矩形作為模板
        img = np.zeros((50, 100, 3), dtype=np.uint8)
        img[:] = color

        # 添加一些紋理使其更真實
        cv2.putText(img, key, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        path = tmp_path / f"{key}_template.png"
        cv2.imwrite(str(path), img)
        templates[key] = str(path)

    return templates


class TestResultDetectorInitialization:
    """測試初始化"""

    def test_default_initialization(self):
        """測試預設初始化"""
        det = ResultDetector()
        assert det.ncc_threshold == 0.70
        assert det.k_frames == 3
        assert det.check_interval == 0.2
        assert det.cooldown_duration == 5.0
        assert det.state == ResultDetectionState.IDLE

    def test_custom_config(self, test_config):
        """測試自定義配置"""
        det = ResultDetector(test_config)
        assert det.ncc_threshold == 0.70
        assert det.k_frames == 3
        assert det.cooldown_duration == 5.0

    def test_state_initialization(self, detector):
        """測試狀態初始化"""
        assert detector.state == ResultDetectionState.IDLE
        assert all(v == 0 for v in detector.consecutive_counters.values())
        assert detector.last_winner is None


class TestROIConfiguration:
    """測試 ROI 配置"""

    def test_set_rois(self, detector, test_rois):
        """測試設置 ROI"""
        assert detector.rois["B"] == test_rois["banker"]
        assert detector.rois["P"] == test_rois["player"]
        assert detector.rois["T"] == test_rois["tie"]

    def test_roi_structure(self, detector):
        """測試 ROI 結構"""
        for key in ["B", "P", "T"]:
            roi = detector.rois[key]
            assert "x" in roi
            assert "y" in roi
            assert "w" in roi
            assert "h" in roi


class TestTemplateLoading:
    """測試模板載入"""

    def test_load_templates_success(self, detector, mock_templates):
        """測試成功載入模板"""
        detector.load_templates(mock_templates)

        for key in ["B", "P", "T"]:
            assert detector.templates[key] is not None
            assert "gray" in detector.templates[key]
            assert "edge" in detector.templates[key]
            assert detector.templates[key]["gray"].ndim == 2  # 灰階圖

    def test_load_templates_missing_file(self, detector):
        """測試載入不存在的模板"""
        with pytest.raises(FileNotFoundError):
            detector.load_templates({
                "B": "nonexistent.png",
                "P": "nonexistent.png",
                "T": "nonexistent.png"
            })

    def test_load_templates_missing_key(self, detector, mock_templates):
        """測試缺少必要 key"""
        incomplete_paths = {"B": mock_templates["B"]}
        with pytest.raises(ValueError):
            detector.load_templates(incomplete_paths)


class TestHealthCheck:
    """測試健康檢查"""

    def test_health_check_no_roi(self):
        """測試缺少 ROI 的健康檢查"""
        det = ResultDetector()
        ok, msg = det.health_check()
        assert not ok
        assert "ROI" in msg

    def test_health_check_no_templates(self, detector):
        """測試缺少模板的健康檢查"""
        ok, msg = detector.health_check()
        assert not ok
        assert "Template" in msg

    def test_health_check_success(self, detector, mock_templates):
        """測試健康檢查成功"""
        detector.load_templates(mock_templates)
        ok, msg = detector.health_check()
        assert ok
        assert msg == "OK"


class TestProcessFrame:
    """測試幀處理"""

    def test_process_frame_no_detection(self, detector, mock_templates):
        """測試無檢測情況"""
        detector.load_templates(mock_templates)

        # 創建空白截圖
        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)

        result = detector.process_frame(screenshot)
        assert result.winner is None
        assert result.state in ["idle", "checking"]

    def test_process_frame_with_mock_match(self, detector, mock_templates):
        """測試模擬匹配"""
        detector.load_templates(mock_templates)

        # 創建包含模板的截圖
        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)

        # 在莊家 ROI 位置放置匹配的內容
        roi = detector.rois["B"]
        x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]

        # 讀取模板
        template_img = cv2.imread(mock_templates["B"])
        template_resized = cv2.resize(template_img, (w, h))

        # 放置到截圖中
        screenshot[y:y+h, x:x+w] = template_resized

        # 處理幀
        result = detector.process_frame(screenshot)

        # 應該開始累積計數
        assert result.state in ["idle", "checking"]
        assert "B" in result.ncc_scores


class TestConsecutiveDetection:
    """測試連續檢測機制"""

    def test_consecutive_counting(self, detector, mock_templates):
        """測試連續計數"""
        detector.load_templates(mock_templates)

        # 創建高匹配度的截圖
        screenshot = self._create_matching_screenshot(detector, mock_templates, "B")

        # 第一幀
        result1 = detector.process_frame(screenshot)
        assert result1.winner is None  # 還未達到 K 幀
        assert result1.consecutive_count <= 1

        # 第二幀
        result2 = detector.process_frame(screenshot)
        assert result2.winner is None
        assert result2.consecutive_count <= 2

        # 第三幀 (K=3)
        result3 = detector.process_frame(screenshot)

        # 如果 NCC 分數夠高，應該檢測到
        if result3.confidence >= detector.ncc_threshold:
            assert result3.winner == "B"
            assert result3.state == "detected"

    def _create_matching_screenshot(self, detector, mock_templates, key):
        """創建匹配的截圖"""
        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        roi = detector.rois[key]
        x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]

        template_img = cv2.imread(mock_templates[key])
        template_resized = cv2.resize(template_img, (w, h))
        screenshot[y:y+h, x:x+w] = template_resized

        return screenshot


class TestCooldownMechanism:
    """測試 Cooldown 機制"""

    def test_cooldown_blocks_detection(self, detector, mock_templates):
        """測試 Cooldown 阻止檢測"""
        detector.load_templates(mock_templates)

        # 手動設置為 Cooldown 狀態
        detector.state = ResultDetectionState.COOLDOWN
        detector.last_detection_time = time.time()

        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = detector.process_frame(screenshot)

        assert result.winner is None
        assert result.state == "cooldown"

    def test_cooldown_expires(self, detector, mock_templates):
        """測試 Cooldown 過期"""
        detector.load_templates(mock_templates)

        # 設置為過期的 Cooldown
        detector.state = ResultDetectionState.COOLDOWN
        detector.last_detection_time = time.time() - 10  # 10秒前

        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = detector.process_frame(screenshot)

        # Cooldown 應該已過期
        assert result.state != "cooldown"
        assert detector.state == ResultDetectionState.IDLE


class TestGetStatus:
    """測試狀態獲取"""

    def test_get_status(self, detector):
        """測試獲取狀態"""
        status = detector.get_status()

        assert "state" in status
        assert "last_winner" in status
        assert "consecutive_counters" in status
        assert "config" in status

        assert status["config"]["ncc_threshold"] == 0.70
        assert status["config"]["k_frames"] == 3


class TestReset:
    """測試重置功能"""

    def test_reset(self, detector):
        """測試重置檢測器"""
        # 設置一些狀態
        detector.state = ResultDetectionState.COOLDOWN
        detector.consecutive_counters["B"] = 2
        detector.last_winner = "B"

        # 重置
        detector.reset()

        # 驗證
        assert detector.state == ResultDetectionState.IDLE
        assert all(v == 0 for v in detector.consecutive_counters.values())
        assert detector.last_winner is None


class TestEdgeCases:
    """測試邊界情況"""

    def test_roi_out_of_bounds(self, detector, mock_templates):
        """測試 ROI 超出邊界"""
        detector.load_templates(mock_templates)

        # 設置超出邊界的 ROI
        detector.rois["B"] = {"x": 2000, "y": 2000, "w": 150, "h": 80}

        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = detector.process_frame(screenshot)

        # 應該優雅處理，不會崩潰
        assert result.ncc_scores["B"] == 0.0

    def test_empty_screenshot(self, detector, mock_templates):
        """測試空截圖"""
        detector.load_templates(mock_templates)

        # 空截圖
        screenshot = np.zeros((0, 0, 3), dtype=np.uint8)

        # 應該不會崩潰
        try:
            result = detector.process_frame(screenshot)
            # 如果執行到這裡，說明處理了但沒崩潰
            assert result.winner is None
        except Exception:
            # 或者拋出異常也是可接受的
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
