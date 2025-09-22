#!/usr/bin/env python3
# run_gui.py - 百家樂自動投注機器人 GUI 啟動器
import sys
import os

# 添加專案根目錄到 Python 路徑
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def main():
    """啟動 GUI 應用程式"""
    try:
        from ui.app import main as ui_main
        ui_main()
    except ImportError as e:
        print(f"錯誤：無法載入 PySide6 模組")
        print(f"請執行：pip install PySide6")
        print(f"詳細錯誤：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"啟動 GUI 時發生錯誤：{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()