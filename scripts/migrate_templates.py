#!/usr/bin/env python3
"""
模板檔案搬移工具 - 將 templates/ 根目錄的 PNG 檔案分類搬移到子目錄
"""
import os
import shutil
import glob
import sys

# 修復 Windows 控制台編碼問題
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

def migrate_templates():
    """執行模板搬移"""
    BASE = "templates"
    SUBS = {"chips": [], "bets": [], "controls": []}

    # 確保子目錄存在
    os.makedirs(os.path.join(BASE, "chips"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "bets"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "controls"), exist_ok=True)

    # 找出根目錄的所有 PNG 檔案
    root_pngs = [p for p in glob.glob(os.path.join(BASE, "*.png"))]

    if not root_pngs:
        print("沒有找到需要搬移的 PNG 檔案")
        return

    print(f"Found {len(root_pngs)} PNG files to migrate:")

    for p in root_pngs:
        name = os.path.basename(p).lower()
        print(f"Processing file: {name}")

        # 粗分流規則（可再手動調整）
        if any(k in name for k in ["chip", "100", "1k", "5k", "10k", "50k"]):
            dst = os.path.join(BASE, "chips", os.path.basename(p))
        elif any(k in name for k in ["banker", "player", "tie", "pair", "lucky", "b.png", "p.png", "t.png"]):
            dst = os.path.join(BASE, "bets", os.path.basename(p))
        elif any(k in name for k in ["confirm", "cancel", "ok", "anchor", "overlay"]):
            dst = os.path.join(BASE, "controls", os.path.basename(p))
        else:
            # Default to controls, can be adjusted later in UI
            dst = os.path.join(BASE, "controls", os.path.basename(p))

        print(f"Move: {p} -> {dst}")
        try:
            shutil.move(p, dst)
            print(f"Success: {os.path.basename(p)}")
        except Exception as e:
            print(f"Error: {e}")

    print("\nMigration completed! Please check 'templates/chips|bets|controls' directories")

    # 顯示搬移結果
    for subdir in ["chips", "bets", "controls"]:
        files = glob.glob(os.path.join(BASE, subdir, "*.png"))
        print(f"  {subdir}/: {len(files)} 個檔案")
        for f in files:
            print(f"    - {os.path.basename(f)}")

if __name__ == "__main__":
    migrate_templates()