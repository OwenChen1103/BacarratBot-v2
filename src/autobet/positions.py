"""
位置管理模組 - 讀寫驗證 positions.json，處理螢幕縮放換算
"""

import json
import os
import logging
from typing import Dict, Any, Tuple, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Point:
    """螢幕點位"""
    x: int
    y: int
    template_w: Optional[int] = None
    template_h: Optional[int] = None


@dataclass
class ROI:
    """感興趣區域"""
    x: int
    y: int
    w: int
    h: int


class PositionsManager:
    """位置配置管理器"""

    def __init__(self, dpi_scale: float = 1.0):
        self.dpi_scale = dpi_scale
        self.config: Dict[str, Any] = {}
        self.points: Dict[str, Dict[str, Point]] = {}
        self.roi: Dict[str, ROI] = {}
        self.screen_info: Dict[str, Any] = {}

    def load_from_file(self, file_path: str) -> bool:
        """從檔案載入位置配置"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"位置配置檔案不存在: {file_path}")
                return False

            with open(file_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)

            # 驗證配置結構
            if not self._validate_config():
                return False

            # 載入螢幕資訊
            self.screen_info = self.config.get('screen', {})

            # 載入點位資訊並應用縮放
            self._load_points()

            # 載入 ROI 資訊並應用縮放
            self._load_roi()

            logger.info(f"成功載入位置配置: {file_path}")
            return True

        except Exception as e:
            logger.error(f"載入位置配置失敗: {e}")
            return False

    def _validate_config(self) -> bool:
        """驗證配置檔案結構"""
        required_sections = ['screen', 'points', 'roi']
        for section in required_sections:
            if section not in self.config:
                logger.error(f"配置檔案缺少必要區塊: {section}")
                return False

        # 檢查點位結構
        points = self.config['points']
        required_point_groups = ['chips', 'bets', 'controls']
        for group in required_point_groups:
            if group not in points:
                logger.error(f"點位配置缺少群組: {group}")
                return False

        # 檢查 ROI 結構
        roi_config = self.config['roi']
        if 'overlay' not in roi_config:
            logger.error("ROI 配置缺少 overlay")
            return False

        return True

    def _load_points(self):
        """載入並縮放點位"""
        self.points = {}
        points_config = self.config['points']

        for group_name, group_points in points_config.items():
            self.points[group_name] = {}
            for point_name, point_data in group_points.items():
                scaled_point = self._scale_point(point_data)
                self.points[group_name][point_name] = scaled_point

    def _load_roi(self):
        """載入並縮放 ROI"""
        self.roi = {}
        roi_config = self.config['roi']

        for roi_name, roi_data in roi_config.items():
            if isinstance(roi_data, dict):
                # 單個 ROI (如 overlay)
                if 'x' in roi_data and 'y' in roi_data:
                    self.roi[roi_name] = self._scale_roi(roi_data)
                else:
                    # ROI 群組 (如 stacks)
                    self.roi[roi_name] = {}
                    for sub_roi_name, sub_roi_data in roi_data.items():
                        self.roi[roi_name][sub_roi_name] = self._scale_roi(sub_roi_data)

    def _scale_point(self, point_data: Dict[str, Any]) -> Point:
        """縮放點位座標"""
        x = int(point_data['x'] * self.dpi_scale)
        y = int(point_data['y'] * self.dpi_scale)
        template_w = point_data.get('template_w')
        template_h = point_data.get('template_h')

        if template_w:
            template_w = int(template_w * self.dpi_scale)
        if template_h:
            template_h = int(template_h * self.dpi_scale)

        return Point(x=x, y=y, template_w=template_w, template_h=template_h)

    def _scale_roi(self, roi_data: Dict[str, Any]) -> ROI:
        """縮放 ROI 座標"""
        x = int(roi_data['x'] * self.dpi_scale)
        y = int(roi_data['y'] * self.dpi_scale)
        w = int(roi_data['w'] * self.dpi_scale)
        h = int(roi_data['h'] * self.dpi_scale)

        return ROI(x=x, y=y, w=w, h=h)

    def get_point(self, group: str, name: str) -> Optional[Point]:
        """取得指定點位"""
        return self.points.get(group, {}).get(name)

    def get_roi(self, name: str, sub_name: str = None) -> Optional[ROI]:
        """取得指定 ROI"""
        if sub_name:
            return self.roi.get(name, {}).get(sub_name)
        return self.roi.get(name)

    def get_chip_denominations(self) -> List[int]:
        """取得可用籌碼面額列表"""
        validation = self.config.get('validation', {})
        return validation.get('chip_denominations', [100, 1000, 5000, 10000, 50000])

    def get_bet_targets(self) -> List[str]:
        """取得可下注目標列表"""
        validation = self.config.get('validation', {})
        return validation.get('bet_targets', ['player', 'banker', 'tie', 'p_pair', 'b_pair', 'lucky6'])

    def get_required_templates(self) -> List[str]:
        """取得必要模板檔案列表"""
        validation = self.config.get('validation', {})
        return validation.get('required_templates', [])

    def validate_screen_environment(self, current_width: int, current_height: int) -> bool:
        """驗證螢幕環境是否匹配配置"""
        config_width = self.screen_info.get('width', 1920)
        config_height = self.screen_info.get('height', 1080)

        # 允許 5% 的誤差
        width_diff = abs(current_width - config_width) / config_width
        height_diff = abs(current_height - config_height) / config_height

        if width_diff > 0.05 or height_diff > 0.05:
            logger.warning(f"螢幕解析度不匹配 - 配置: {config_width}x{config_height}, 實際: {current_width}x{current_height}")
            return False

        return True

    def save_to_file(self, file_path: str) -> bool:
        """儲存位置配置到檔案"""
        try:
            # 反縮放回原始座標
            original_config = self._unscale_config()

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(original_config, f, indent=2, ensure_ascii=False)

            logger.info(f"位置配置已儲存: {file_path}")
            return True

        except Exception as e:
            logger.error(f"儲存位置配置失敗: {e}")
            return False

    def _unscale_config(self) -> Dict[str, Any]:
        """將縮放後的配置反向轉換為原始座標"""
        config = self.config.copy()

        # 反縮放點位
        for group_name, group_points in self.points.items():
            for point_name, point in group_points.items():
                config['points'][group_name][point_name]['x'] = int(point.x / self.dpi_scale)
                config['points'][group_name][point_name]['y'] = int(point.y / self.dpi_scale)
                if point.template_w:
                    config['points'][group_name][point_name]['template_w'] = int(point.template_w / self.dpi_scale)
                if point.template_h:
                    config['points'][group_name][point_name]['template_h'] = int(point.template_h / self.dpi_scale)

        # 反縮放 ROI
        for roi_name, roi_item in self.roi.items():
            if isinstance(roi_item, ROI):
                config['roi'][roi_name]['x'] = int(roi_item.x / self.dpi_scale)
                config['roi'][roi_name]['y'] = int(roi_item.y / self.dpi_scale)
                config['roi'][roi_name]['w'] = int(roi_item.w / self.dpi_scale)
                config['roi'][roi_name]['h'] = int(roi_item.h / self.dpi_scale)
            elif isinstance(roi_item, dict):
                for sub_roi_name, sub_roi in roi_item.items():
                    config['roi'][roi_name][sub_roi_name]['x'] = int(sub_roi.x / self.dpi_scale)
                    config['roi'][roi_name][sub_roi_name]['y'] = int(sub_roi.y / self.dpi_scale)
                    config['roi'][roi_name][sub_roi_name]['w'] = int(sub_roi.w / self.dpi_scale)
                    config['roi'][roi_name][sub_roi_name]['h'] = int(sub_roi.h / self.dpi_scale)

        return config