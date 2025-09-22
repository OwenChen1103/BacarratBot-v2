#!/usr/bin/env python3
"""
互動式位置捕獲工具 - 點兩下取點，生成 positions.json
"""

import os
import sys
import json
import time
import pyautogui
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Dict, Any, List, Tuple

# 禁用 pyautogui 安全機制
pyautogui.FAILSAFE = False


class PositionCapture:
    """位置捕獲器"""

    def __init__(self):
        self.positions = {
            "version": 2,
            "description": "百家樂遊戲元素位置配置",
            "screen": {
                "width": 0,
                "height": 0,
                "dpi_scale": 1.0,
                "last_updated": ""
            },
            "points": {
                "chips": {},
                "bets": {},
                "controls": {}
            },
            "roi": {
                "overlay": {},
                "stacks": {}
            },
            "validation": {
                "chip_denominations": [100, 1000, 5000, 10000, 50000],
                "bet_targets": ["player", "banker", "tie", "p_pair", "b_pair", "lucky6"],
                "required_templates": []
            }
        }

        self.capture_sequence = [
            # 籌碼位置
            ("chips", "chip_100", "100 面額籌碼"),
            ("chips", "chip_1k", "1K 面額籌碼"),
            ("chips", "chip_5k", "5K 面額籌碼"),
            ("chips", "chip_10k", "10K 面額籌碼"),
            ("chips", "chip_50k", "50K 面額籌碼"),

            # 下注區域
            ("bets", "player", "閒家下注區"),
            ("bets", "banker", "莊家下注區"),
            ("bets", "tie", "和局下注區"),
            ("bets", "p_pair", "閒對下注區"),
            ("bets", "b_pair", "莊對下注區"),
            ("bets", "lucky6", "幸運6下注區"),

            # 控制按鈕
            ("controls", "confirm", "確認按鈕"),
            ("controls", "cancel", "取消按鈕"),

            # ROI 區域（特殊處理）
            ("roi", "overlay", "下注期狀態橫條（左上角）"),
            ("roi", "overlay_end", "下注期狀態橫條（右下角）"),

            # 籌碼堆疊區域
            ("stacks", "player_stack", "閒家籌碼堆疊區"),
            ("stacks", "banker_stack", "莊家籌碼堆疊區"),
            ("stacks", "tie_stack", "和局籌碼堆疊區"),
            ("stacks", "p_pair_stack", "閒對籌碼堆疊區"),
            ("stacks", "b_pair_stack", "莊對籌碼堆疊區"),
            ("stacks", "lucky6_stack", "幸運6籌碼堆疊區"),
        ]

        self.current_step = 0
        self.captured_points = {}
        self.roi_corners = {}

    def start_capture(self):
        """開始捕獲流程"""
        # 取得螢幕尺寸
        screen_width, screen_height = pyautogui.size()
        self.positions["screen"]["width"] = screen_width
        self.positions["screen"]["height"] = screen_height

        print(f"螢幕解析度: {screen_width}x{screen_height}")
        print("位置捕獲工具已啟動")
        print("=" * 50)

        # 顯示說明
        self._show_instructions()

        # 開始捕獲流程
        for i, (group, name, description) in enumerate(self.capture_sequence):
            self.current_step = i
            success = self._capture_point(group, name, description)

            if not success:
                print("捕獲已取消")
                return False

        # 處理特殊的 ROI 區域
        self._process_roi_areas()

        # 設置時間戳
        from datetime import datetime
        self.positions["screen"]["last_updated"] = datetime.now().isoformat()

        # 儲存結果
        return self._save_positions()

    def _show_instructions(self):
        """顯示操作說明"""
        instructions = """
位置捕獲操作說明：

1. 確保百家樂遊戲視窗完全可見
2. 按照提示依序點擊各個元素
3. 每個元素需要雙擊來確認位置
4. 按 ESC 可以跳過當前元素
5. 按 Ctrl+C 可以完全退出

建議順序：
- 先捕獲籌碼位置（底部籌碼列）
- 再捕獲下注區域（主要遊戲區域）
- 然後捕獲控制按鈕（確認/取消）
- 最後捕獲狀態區域（overlay 和 stack）

準備就緒後按 Enter 開始...
        """
        print(instructions)
        input()

    def _capture_point(self, group: str, name: str, description: str) -> bool:
        """捕獲單個點位"""
        print(f"\n[{self.current_step + 1}/{len(self.capture_sequence)}] {description}")
        print("請雙擊目標位置...")

        try:
            if group == "roi" and name in ["overlay", "overlay_end"]:
                return self._capture_roi_corner(name, description)
            elif group == "stacks":
                return self._capture_stack_region(name, description)
            else:
                return self._capture_regular_point(group, name, description)

        except KeyboardInterrupt:
            print("\n捕獲已中斷")
            return False

    def _capture_regular_point(self, group: str, name: str, description: str) -> bool:
        """捕獲普通點位"""
        while True:
            try:
                # 等待雙擊
                print("等待雙擊...", end="", flush=True)
                click_pos = self._wait_for_double_click()

                if click_pos is None:
                    print("\n跳過此項目")
                    return True

                x, y = click_pos
                print(f"\n捕獲位置: ({x}, {y})")

                # 確認
                confirm = input("確認此位置? (y/n/r=重新捕獲): ").strip().lower()
                if confirm == 'y':
                    self.positions["points"][group][name] = {
                        "x": x,
                        "y": y,
                        "template_w": 60,  # 預設模板尺寸
                        "template_h": 40
                    }
                    print(f"✓ {description} 位置已儲存")
                    return True
                elif confirm == 'n':
                    print("跳過此項目")
                    return True
                # confirm == 'r' 時重新捕獲

            except Exception as e:
                print(f"捕獲錯誤: {e}")
                return False

    def _capture_roi_corner(self, name: str, description: str) -> bool:
        """捕獲 ROI 角點"""
        while True:
            try:
                print("等待雙擊...", end="", flush=True)
                click_pos = self._wait_for_double_click()

                if click_pos is None:
                    print("\n跳過此項目")
                    return True

                x, y = click_pos
                print(f"\n捕獲位置: ({x}, {y})")

                confirm = input("確認此位置? (y/n/r=重新捕獲): ").strip().lower()
                if confirm == 'y':
                    self.roi_corners[name] = (x, y)
                    print(f"✓ {description} 角點已儲存")
                    return True
                elif confirm == 'n':
                    print("跳過此項目")
                    return True

            except Exception as e:
                print(f"捕獲錯誤: {e}")
                return False

    def _capture_stack_region(self, name: str, description: str) -> bool:
        """捕獲籌碼堆疊區域"""
        while True:
            try:
                print("請點擊籌碼堆疊區域的中心位置...")
                print("等待雙擊...", end="", flush=True)
                click_pos = self._wait_for_double_click()

                if click_pos is None:
                    print("\n跳過此項目")
                    return True

                x, y = click_pos
                print(f"\n捕獲位置: ({x}, {y})")

                confirm = input("確認此位置? (y/n/r=重新捕獲): ").strip().lower()
                if confirm == 'y':
                    # 為 stack 區域設置固定尺寸
                    stack_name = name.replace("_stack", "")
                    if "stacks" not in self.positions["roi"]:
                        self.positions["roi"]["stacks"] = {}

                    self.positions["roi"]["stacks"][name] = {
                        "x": x - 30,  # 中心點向左偏移
                        "y": y - 20,  # 中心點向上偏移
                        "w": 60,
                        "h": 40
                    }
                    print(f"✓ {description} 區域已儲存")
                    return True
                elif confirm == 'n':
                    print("跳過此項目")
                    return True

            except Exception as e:
                print(f"捕獲錯誤: {e}")
                return False

    def _wait_for_double_click(self, timeout: float = 30.0) -> Tuple[int, int]:
        """等待雙擊事件"""
        start_time = time.time()
        last_click_time = 0
        last_click_pos = None

        while time.time() - start_time < timeout:
            try:
                # 檢查是否有滑鼠點擊
                current_pos = pyautogui.position()
                current_time = time.time()

                # 檢測滑鼠按鈕狀態（簡化實作）
                if pyautogui.mouseDown():
                    # 檢查是否為雙擊
                    if (last_click_pos and
                        abs(current_pos[0] - last_click_pos[0]) < 10 and
                        abs(current_pos[1] - last_click_pos[1]) < 10 and
                        current_time - last_click_time < 0.5):

                        return current_pos

                    last_click_pos = current_pos
                    last_click_time = current_time

                time.sleep(0.1)

            except KeyboardInterrupt:
                return None

        return None

    def _process_roi_areas(self):
        """處理 ROI 區域"""
        if "overlay" in self.roi_corners and "overlay_end" in self.roi_corners:
            x1, y1 = self.roi_corners["overlay"]
            x2, y2 = self.roi_corners["overlay_end"]

            # 確保左上角到右下角
            x = min(x1, x2)
            y = min(y1, y2)
            w = abs(x2 - x1)
            h = abs(y2 - y1)

            self.positions["roi"]["overlay"] = {
                "x": x,
                "y": y,
                "w": w,
                "h": h
            }

            print(f"✓ Overlay ROI 已生成: ({x}, {y}, {w}, {h})")

    def _save_positions(self) -> bool:
        """儲存位置配置"""
        try:
            # 選擇儲存位置
            output_file = self._choose_output_file()
            if not output_file:
                print("未選擇輸出檔案")
                return False

            # 儲存 JSON
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.positions, f, indent=2, ensure_ascii=False)

            print(f"✓ 位置配置已儲存: {output_file}")

            # 顯示統計
            self._show_statistics()

            return True

        except Exception as e:
            print(f"儲存失敗: {e}")
            return False

    def _choose_output_file(self) -> str:
        """選擇輸出檔案"""
        try:
            # 嘗試使用 tkinter 檔案對話框
            root = tk.Tk()
            root.withdraw()

            file_path = filedialog.asksaveasfilename(
                title="儲存位置配置",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialfile="positions.json"
            )

            root.destroy()
            return file_path

        except:
            # 備選方案：使用預設檔名
            default_file = "positions.json"
            use_default = input(f"使用預設檔名 '{default_file}'? (y/n): ").strip().lower()
            return default_file if use_default == 'y' else ""

    def _show_statistics(self):
        """顯示捕獲統計"""
        print("\n" + "=" * 50)
        print("捕獲統計:")

        for group, items in self.positions["points"].items():
            if items:
                print(f"  {group}: {len(items)} 個點位")

        if self.positions["roi"].get("overlay"):
            print(f"  overlay ROI: 已設置")

        if self.positions["roi"].get("stacks"):
            print(f"  stack ROIs: {len(self.positions['roi']['stacks'])} 個")

        print("=" * 50)


def main():
    """主函數"""
    print("百家樂位置捕獲工具")
    print("=" * 30)

    try:
        capture = PositionCapture()
        success = capture.start_capture()

        if success:
            print("\n🎉 位置捕獲完成！")
            print("\n下一步:")
            print("1. 檢查生成的 positions.json 檔案")
            print("2. 運行 check_templates.py 驗證模板匹配")
            print("3. 執行 test_dryrun.py 進行測試")
        else:
            print("\n❌ 位置捕獲失敗或已取消")

    except KeyboardInterrupt:
        print("\n\n用戶中斷，程式結束")
    except Exception as e:
        print(f"\n程式錯誤: {e}")


if __name__ == "__main__":
    main()