# tests/test_table_id_normalization.py
"""測試桌號標準化邏輯"""

import sys
from pathlib import Path

# 添加專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ui.workers.engine_worker import TABLE_DISPLAY_MAP, DISPLAY_TO_CANONICAL_MAP


def test_table_mapping():
    """測試桌號映射"""
    print("=" * 60)
    print("測試桌號映射")
    print("=" * 60)

    # 測試 canonical -> display
    print("\n1. Canonical ID -> Display Name:")
    print("-" * 40)
    for canonical, display in TABLE_DISPLAY_MAP.items():
        print(f"  {canonical:8s} -> {display}")

    # 測試 display -> canonical
    print("\n2. Display Name -> Canonical ID:")
    print("-" * 40)
    for display, canonical in DISPLAY_TO_CANONICAL_MAP.items():
        print(f"  {display:8s} -> {canonical}")

    # 驗證雙向映射
    print("\n3. 驗證雙向映射一致性:")
    print("-" * 40)
    errors = []
    for canonical, display in TABLE_DISPLAY_MAP.items():
        reverse = DISPLAY_TO_CANONICAL_MAP.get(display)
        if reverse != canonical:
            errors.append(f"  ❌ {canonical} -> {display} -> {reverse}")
        else:
            print(f"  ✅ {canonical} <-> {display}")

    if errors:
        print("\n錯誤:")
        for error in errors:
            print(error)
        return False

    print("\n✅ 所有映射一致")
    return True


def test_normalize_table_id():
    """測試桌號標準化函數"""
    print("\n" + "=" * 60)
    print("測試桌號標準化")
    print("=" * 60)

    # 模擬 _normalize_table_id 邏輯
    def normalize_table_id(table_id: str) -> str:
        if not table_id:
            return table_id
        table_id_str = str(table_id).strip()
        canonical = DISPLAY_TO_CANONICAL_MAP.get(table_id_str)
        if canonical:
            return canonical
        return table_id_str

    test_cases = [
        # (輸入, 預期輸出, 描述)
        ("BG_135", "WG10", "Display name -> Canonical ID"),
        ("WG10", "WG10", "Canonical ID -> Canonical ID"),
        ("BG125", "BG125", "真實 BG 桌 -> 不變"),
        ("BG_131", "WG7", "Display name -> Canonical ID"),
        ("WG15", "WG15", "未映射的 WG 桌 -> 不變"),
        ("UNKNOWN", "UNKNOWN", "未知桌號 -> 不變"),
    ]

    print("\n測試案例:")
    print("-" * 40)
    all_passed = True
    for input_id, expected, description in test_cases:
        result = normalize_table_id(input_id)
        passed = result == expected
        status = "✅" if passed else "❌"
        print(f"{status} {input_id:10s} -> {result:10s} (預期: {expected:10s}) - {description}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n✅ 所有測試通過")
    else:
        print("\n❌ 部分測試失敗")

    return all_passed


def test_is_selected_table():
    """測試桌號匹配邏輯"""
    print("\n" + "=" * 60)
    print("測試桌號匹配")
    print("=" * 60)

    # 模擬 _is_selected_table 邏輯（內部已統一使用 canonical ID）
    def is_selected_table(table_id: str, selected_table: str) -> bool:
        if not selected_table:
            return True
        if not table_id:
            return False
        return str(table_id).strip() == str(selected_table).strip()

    test_cases = [
        # (T9推送的table_id, 用戶選擇的桌號（已標準化為canonical）, 預期結果, 描述)
        ("WG10", "WG10", True, "Canonical 匹配 Canonical"),
        ("WG10", "WG7", False, "不同 Canonical"),
        ("BG125", "BG125", True, "真實 BG 桌匹配"),
        ("WG10", None, True, "未選擇桌號時接受所有"),
        ("WG7", "WG7", True, "WG7 匹配"),
    ]

    print("\n測試案例（假設 _selected_table 已標準化為 canonical ID）:")
    print("-" * 60)
    all_passed = True
    for table_id, selected, expected, description in test_cases:
        result = is_selected_table(table_id, selected)
        passed = result == expected
        status = "✅" if passed else "❌"
        print(f"{status} T9={table_id:8s}, selected={str(selected):8s} -> {result:5} (預期: {expected:5}) - {description}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n✅ 所有測試通過")
    else:
        print("\n❌ 部分測試失敗")

    return all_passed


def test_real_scenario():
    """測試真實場景：用戶選擇 BG_135，T9 推送 WG10"""
    print("\n" + "=" * 60)
    print("真實場景測試")
    print("=" * 60)

    # 模擬完整流程
    def normalize_table_id(table_id: str) -> str:
        if not table_id:
            return table_id
        table_id_str = str(table_id).strip()
        canonical = DISPLAY_TO_CANONICAL_MAP.get(table_id_str)
        if canonical:
            return canonical
        return table_id_str

    def is_selected_table(table_id: str, selected_table: str) -> bool:
        if not selected_table:
            return True
        if not table_id:
            return False
        return str(table_id).strip() == str(selected_table).strip()

    print("\n場景: 用戶在 UI 選擇 BG_135，T9 持續推送 WG10 的事件")
    print("-" * 60)

    # 1. 用戶選擇桌號（Dashboard 傳入可能是 display name）
    user_selection = "BG_135"
    print(f"\n1️⃣  用戶選擇: {user_selection}")

    # 2. set_selected_table 標準化為 canonical ID
    canonical_selected = normalize_table_id(user_selection)
    print(f"2️⃣  標準化後: {canonical_selected}")

    # 3. T9 推送事件
    t9_events = [
        {"table_id": "WG10", "round_id": "11203", "winner": "P"},
        {"table_id": "WG10", "round_id": "11207", "winner": "B"},
        {"table_id": "WG10", "round_id": "11231", "winner": "P"},
        {"table_id": "WG7", "round_id": "11250", "winner": "T"},  # 不同桌號
    ]

    print(f"\n3️⃣  T9 推送事件:")
    all_correct = True
    for event in t9_events:
        table_id = event["table_id"]
        round_id = event["round_id"]
        winner = event["winner"]

        # 檢查是否匹配
        is_match = is_selected_table(table_id, canonical_selected)
        expected = (table_id == "WG10")  # 只有 WG10 應該通過

        status = "✅ 接受" if is_match else "❌ 過濾"
        correct = (is_match == expected)
        result_mark = "✅" if correct else "❌"

        print(f"  {result_mark} {status} - table={table_id}, round={round_id}, winner={winner}")

        if not correct:
            all_correct = False
            print(f"      ⚠️  預期: {'接受' if expected else '過濾'}, 實際: {'接受' if is_match else '過濾'}")

    if all_correct:
        print("\n✅ 場景測試通過！所有 WG10 事件都被正確接受，其他桌號被過濾")
    else:
        print("\n❌ 場景測試失敗！")

    return all_correct


if __name__ == "__main__":
    import sys
    import io
    # 強制 UTF-8 輸出
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    print("\n" + "=" * 60)
    print("Table ID Normalization Test Suite")
    print("=" * 60)

    results = []
    results.append(("桌號映射", test_table_mapping()))
    results.append(("標準化邏輯", test_normalize_table_id()))
    results.append(("匹配邏輯", test_is_selected_table()))
    results.append(("真實場景", test_real_scenario()))

    print("\n" + "=" * 60)
    print("測試總結")
    print("=" * 60)
    for name, passed in results:
        status = "✅ 通過" if passed else "❌ 失敗"
        print(f"{status} - {name}")

    all_passed = all(result for _, result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有測試通過！")
    else:
        print("❌ 部分測試失敗，請檢查")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)
