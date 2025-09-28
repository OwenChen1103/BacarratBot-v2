#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# run_gui.py
import sys
import os
import locale

# Set encoding for Windows console
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def main():
    try:
        # Set locale for proper Unicode handling
        try:
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except:
            try:
                locale.setlocale(locale.LC_ALL, 'C.UTF-8')
            except:
                pass  # Use system default

        from ui.app import run
        sys.exit(run())
    except ImportError as e:
        print("Error: Cannot load PySide6 module")
        print("Please run: pip install PySide6")
        print(f"Detail: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"GUI startup error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()