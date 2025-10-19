#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""配置檢查腳本"""

from src.utils.config_validator import ConfigValidator

def main():
    validator = ConfigValidator()
    results = validator.validate_all()
    summary = validator.get_config_summary()

    print("=" * 60)
    print("系統配置檢查報告")
    print("=" * 60)
    print(f"\n完成度: {int(summary['completion_rate']*100)}%")
    print(f"可以開始實戰: {'是' if summary['ready_for_battle'] else '否'}")
    print("\n" + "=" * 60)
    print("各模塊狀態:")
    print("=" * 60)

    for key, result in results.items():
        if key != 'overall':
            status = "✅" if result.complete else "❌"
            print(f"{status} {key}: {result.message}")

    if not summary['ready_for_battle']:
        print("\n" + "=" * 60)
        print("缺失的配置:")
        print("=" * 60)
        for item in summary['missing_critical']:
            print(f"  • {item}")

        print("\n" + "=" * 60)
        print("建議:")
        print("=" * 60)
        for suggestion in summary['suggestions']:
            print(f"  • {suggestion}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
