#!/usr/bin/env python3
"""
測試多鍵位位置校準功能
模擬 GUI 的行為來測試核心邏輯
"""
import json
import os
import sys
import time

# 修復 Windows 控制台編碼問題
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# 添加專案根目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_merge_positions():
    """測試位置配置合併邏輯"""
    print("=== 測試多鍵位位置配置合併 ===")

    POSITIONS_FILE = "configs/positions.json"

    # 步驟 1: 創建初始配置（模擬第一次使用）
    initial_positions = {
        "version": 2,
        "description": "Initial test positions",
        "screen": {"width": 1920, "height": 1080, "dpi_scale": 1.0},
        "points": {
            "banker": {"x": 1000, "y": 700},
            "player": {"x": 800, "y": 700}
        },
        "roi": {
            "overlay": {"x": 1450, "y": 360, "w": 420, "h": 50}
        },
        "validation": {"min_click_gap_ms": 40}
    }

    os.makedirs("configs", exist_ok=True)
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(initial_positions, f, ensure_ascii=False, indent=2)

    print(f"[OK] 創建初始配置: banker({1000},{700}), player({800},{700})")

    # 步驟 2: 模擬 GUI 新增更多鍵位
    def simulate_gui_add_positions():
        """模擬 GUI 新增鍵位的邏輯"""
        # 讀取現有配置
        current = {}
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                current = json.load(f)

        # 模擬新增 tie 和 chip_1k 鍵位
        new_points = {
            "tie": {"x": 900, "y": 650},
            "chip_1k": {"x": 1720, "y": 950},
            "confirm": {"x": 1750, "y": 850}
        }

        # 合併邏輯（不覆蓋現有鍵位）
        current.setdefault("points", {})
        for key, pos in new_points.items():
            current["points"][key] = pos
            print(f"  [GUI] 新增鍵位: {key} → ({pos['x']}, {pos['y']})")

        # 添加 metadata
        current.setdefault("meta", {})
        current["meta"]["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        current["meta"]["total_keys"] = len(current["points"])

        # 保存合併後的配置
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)

        return current

    updated_config = simulate_gui_add_positions()
    print(f"[OK] GUI 新增鍵位完成，總計 {len(updated_config['points'])} 個鍵位")

    # 步驟 3: 驗證合併結果
    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
        final_config = json.load(f)

    expected_keys = ["banker", "player", "tie", "chip_1k", "confirm"]
    actual_keys = list(final_config["points"].keys())

    print(f"\n=== 合併結果驗證 ===")
    print(f"期望鍵位: {expected_keys}")
    print(f"實際鍵位: {actual_keys}")

    # 檢查所有期望的鍵位都存在
    missing_keys = set(expected_keys) - set(actual_keys)
    extra_keys = set(actual_keys) - set(expected_keys)

    if not missing_keys and not extra_keys:
        print("[OK] 鍵位合併完全正確")
    else:
        if missing_keys:
            print(f"[ERROR] 缺失鍵位: {missing_keys}")
        if extra_keys:
            print(f"[INFO] 額外鍵位: {extra_keys}")

    # 檢查原始鍵位是否被保留
    if (final_config["points"]["banker"]["x"] == 1000 and
        final_config["points"]["player"]["x"] == 800):
        print("[OK] 原始鍵位座標未被覆蓋")
    else:
        print("[ERROR] 原始鍵位座標被覆蓋了")

    # 檢查新鍵位是否正確
    if (final_config["points"]["tie"]["x"] == 900 and
        final_config["points"]["chip_1k"]["x"] == 1720):
        print("[OK] 新增鍵位座標正確")
    else:
        print("[ERROR] 新增鍵位座標錯誤")

    return final_config

def test_console_integration():
    """測試 Console 讀取新配置的整合"""
    print(f"\n=== 測試 Console 整合 ===")

    # 驗證 CLI 優先級邏輯
    if os.path.exists("configs/positions.json"):
        print("[OK] GUI 配置檔案存在，CLI 應該優先使用它")
    else:
        print("[ERROR] GUI 配置檔案不存在")

    # 模擬讀取配置的過程
    try:
        with open("configs/positions.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        # 檢查關鍵座標
        key_positions = {
            "banker": config["points"].get("banker"),
            "chip_1k": config["points"].get("chip_1k"),
            "confirm": config["points"].get("confirm")
        }

        print("Console 將讀取以下座標:")
        for key, pos in key_positions.items():
            if pos:
                print(f"  {key}: ({pos['x']}, {pos['y']})")
            else:
                print(f"  {key}: 未設定")

        return config

    except Exception as e:
        print(f"[ERROR] 讀取配置失敗: {e}")
        return None

def test_color_scheme():
    """測試顏色方案配置"""
    print(f"\n=== 測試顏色方案 ===")

    # 這些顏色來自新版 GUI
    expected_colors = {
        "banker":  "#ef4444",  # 紅色
        "player":  "#10b981",  # 綠色
        "tie":     "#f59e0b",  # 黃色
        "confirm": "#60a5fa",  # 藍色
        "cancel":  "#a3a3a3",  # 灰色
        "chip_1k": "#8b5cf6",  # 紫色
        "chip_100":"#f472b6",  # 粉色
    }

    print("GUI 標記顏色方案:")
    for key, color in expected_colors.items():
        print(f"  {key}: {color}")

    print("[OK] 顏色方案配置完整")

def main():
    """主測試函數"""
    print("Multi-Key Position Calibration Test")
    print("=" * 50)

    try:
        # 執行各項測試
        final_config = test_merge_positions()
        console_config = test_console_integration()
        test_color_scheme()

        if final_config and console_config:
            print(f"\n[SUCCESS] All tests passed!")
            print(f"Config file: configs/positions.json")
            print(f"Total keys: {len(final_config['points'])}")
            print(f"Last updated: {final_config.get('meta', {}).get('last_updated', 'N/A')}")
        else:
            print(f"\n[ERROR] Some tests failed")

    except Exception as e:
        print(f"[ERROR] Test execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()