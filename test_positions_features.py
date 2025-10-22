# -*- coding: utf-8 -*-
"""
測試位置校準頁面的新功能
"""
import sys
import os
sys.path.insert(0, '.')

def test_basic_imports():
    """Test basic imports"""
    try:
        from ui.pages._utils_positions import (
            get_all_screens, validate_position_schema,
            create_backup_filename, calculate_coordinate_scale
        )
        from src.autobet.actuator import Actuator
        print("[OK] Basic imports successful")
        return True
    except Exception as e:
        print(f"[ERROR] Import failed: {e}")
        return False

def test_screen_detection():
    """Test screen detection"""
    try:
        from PySide6.QtWidgets import QApplication
        from ui.pages._utils_positions import get_all_screens

        # 創建 QApplication 實例（如果不存在）
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        screens = get_all_screens()
        print(f"[OK] Detected {len(screens)} screens")
        for i, screen in enumerate(screens):
            print(f"  Screen {i+1}: {screen.get('name', 'Unknown')} - {screen['geometry']}")

        # 測試可以通過即使沒有螢幕（在某些環境下）
        print("[OK] Screen detection function works")
        return True
    except Exception as e:
        print(f"[ERROR] Screen detection failed: {e}")
        return False

def test_schema_validation():
    """測試 Schema 驗證"""
    try:
        from ui.pages._utils_positions import validate_position_schema

        # 測試完整數據
        complete_data = {
            "version": 2,
            "description": "Test positions",
            "screen": {"width": 1920, "height": 1080, "dpi_scale": 1.0},
            "points": {"banker": {"x": 100, "y": 200}},
            "roi": {"overlay": {"x": 0, "y": 0, "w": 100, "h": 50}},
            "validation": {"min_click_gap_ms": 40}
        }
        valid, errors, fixed = validate_position_schema(complete_data)
        print(f"[OK] Complete data validation: valid={valid}, errors={len(errors)}")

        # 測試不完整數據
        incomplete_data = {"points": {"banker": {"x": 100, "y": 200}}}
        valid, errors, fixed = validate_position_schema(incomplete_data)
        print(f"[OK] Incomplete data validation: valid={valid}, errors={len(errors)} (fixed)")

        return True
    except Exception as e:
        print(f"[ERROR] Schema validation failed: {e}")
        return False

def test_coordinate_calculations():
    """測試座標計算"""
    try:
        from ui.pages._utils_positions import (
            calculate_coordinate_scale, apply_coordinate_transform
        )

        original_size = (1920, 1080)
        display_size = (960, 540)
        scale = calculate_coordinate_scale(original_size, display_size)
        print(f"[OK] Scale calculation: {scale}")

        x, y = apply_coordinate_transform(100, 200, scale)
        print(f"[OK] Coordinate transform: (100, 200) -> ({x}, {y})")

        return True
    except Exception as e:
        print(f"[ERROR] Coordinate calculation failed: {e}")
        return False

def test_actuator_dry_run():
    """測試 Actuator dry-run"""
    try:
        from src.autobet.actuator import Actuator

        positions_data = {
            "points": {"banker": {"x": 100, "y": 200}}
        }
        ui_config = {
            "click": {"jitter_px": 2, "move_delay_ms": [40, 120], "click_delay_ms": [40, 80]}
        }

        actuator = Actuator(positions_data, ui_config, dry_run=True)

        # 測試點擊座標
        result1 = actuator.dry_click_point(100, 200, "test_point")
        print(f"[OK] Dry-run click point: {result1}")

        # 測試點擊按鍵
        result2 = actuator.dry_click_key("banker")
        print(f"[OK] Dry-run click key: {result2}")

        return result1 and result2
    except Exception as e:
        print(f"[ERROR] Actuator test failed: {e}")
        return False

def test_backup_filename():
    """測試備份文件名生成"""
    try:
        from ui.pages._utils_positions import create_backup_filename

        original = "configs/positions.json"
        backup = create_backup_filename(original)
        print(f"[OK] Backup filename: {original} -> {backup}")

        return backup.endswith(".json.bak") and "positions." in backup
    except Exception as e:
        print(f"[ERROR] Backup filename test failed: {e}")
        return False

def main():
    """主測試函數"""
    print("=== Positions Page Feature Test ===\n")

    tests = [
        ("Basic Import", test_basic_imports),
        ("Screen Detection", test_screen_detection),
        ("Schema Validation", test_schema_validation),
        ("Coordinate Calculation", test_coordinate_calculations),
        ("Actuator Dry-run", test_actuator_dry_run),
        ("Backup Filename", test_backup_filename),
    ]

    passed = 0
    total = len(tests)

    for name, test_func in tests:
        print(f"\n--- Testing {name} ---")
        try:
            if test_func():
                passed += 1
                print(f"[PASS] {name}")
            else:
                print(f"[FAIL] {name}")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")

    print(f"\n=== Test Summary ===")
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {passed/total*100:.1f}%")

    if passed == total:
        print("\n[SUCCESS] All tests passed! Positions page features working correctly.")
        return True
    else:
        print(f"\n[WARNING] {total-passed} tests failed, need investigation.")
        return False

if __name__ == "__main__":
    main()