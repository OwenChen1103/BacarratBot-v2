#!/usr/bin/env python3
# run_gui.py
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def main():
    try:
        from ui.app import run
        sys.exit(run())
    except ImportError as e:
        print(f"Error: Cannot load PySide6 module")
        print(f"Please run: pip install PySide6")
        print(f"Detail: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"GUI startup error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()