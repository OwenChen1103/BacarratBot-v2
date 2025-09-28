# ui/pages/_utils_positions.py
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtCore import QRect

def get_all_screens() -> List[Dict]:
    """獲取所有螢幕信息"""
    screens = []
    app = QGuiApplication.instance()
    if app:
        for i, screen in enumerate(app.screens()):
            geometry = screen.geometry()
            screens.append({
                'index': i,
                'name': screen.name(),
                'geometry': {
                    'x': geometry.x(),
                    'y': geometry.y(),
                    'width': geometry.width(),
                    'height': geometry.height()
                },
                'device_pixel_ratio': screen.devicePixelRatio(),
                'logical_dpi': screen.logicalDotsPerInch(),
                'physical_dpi': screen.physicalDotsPerInch()
            })
    return screens

def create_backup_filename(base_path: str) -> str:
    """創建備份文件名"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    name, ext = os.path.splitext(base_path)
    return f"{name}.{timestamp}{ext}.bak"

def validate_position_schema(data: Dict) -> Tuple[bool, List[str], Dict]:
    """驗證並修復 position schema"""
    errors = []
    fixed_data = data.copy()

    # 必要欄位檢查與修復
    default_schema = {
        "version": 2,
        "description": "GUI Positions Calibrator",
        "screen": {"width": 1920, "height": 1080, "dpi_scale": 1.0},
        "points": {},
        "roi": {
            "overlay": {"x": 1450, "y": 360, "w": 420, "h": 50},
            "player_stack": {"x": 720, "y": 670, "w": 120, "h": 60},
            "banker_stack": {"x": 1140, "y": 670, "w": 120, "h": 60},
            "tie_stack": {"x": 930, "y": 620, "w": 120, "h": 60}
        },
        "validation": {"min_click_gap_ms": 40}
    }

    for key, default_value in default_schema.items():
        if key not in fixed_data:
            fixed_data[key] = default_value
            errors.append(f"缺少 {key} 欄位，已補預設值")
        elif key == "screen" and not isinstance(fixed_data[key], dict):
            fixed_data[key] = default_value
            errors.append(f"{key} 格式錯誤，已重設為預設值")
        elif key == "points" and not isinstance(fixed_data[key], dict):
            fixed_data[key] = {}
            errors.append(f"{key} 格式錯誤，已重設為空字典")

    # 檢查必要點位
    required_points = ["banker", "chip_1k", "confirm"]
    missing_points = [p for p in required_points if p not in fixed_data.get("points", {})]
    if missing_points:
        errors.append(f"缺少必備點位: {', '.join(missing_points)}")

    return len(errors) == 0, errors, fixed_data

def calculate_coordinate_scale(original_size: Tuple[int, int], display_size: Tuple[int, int]) -> float:
    """計算座標縮放比例"""
    if display_size[0] == 0:
        return 1.0
    return original_size[0] / display_size[0]

def apply_coordinate_transform(x: int, y: int, scale: float) -> Tuple[int, int]:
    """應用座標轉換"""
    return int(x * scale), int(y * scale)

def get_magnifier_region(pixmap, center_x: int, center_y: int, size: int = 50) -> 'QPixmap':
    """獲取放大鏡區域"""
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import QRect

    if not pixmap or pixmap.isNull():
        return QPixmap()

    # 計算放大鏡區域
    half_size = size // 2
    x = max(0, min(center_x - half_size, pixmap.width() - size))
    y = max(0, min(center_y - half_size, pixmap.height() - size))

    rect = QRect(x, y, size, size)
    return pixmap.copy(rect)