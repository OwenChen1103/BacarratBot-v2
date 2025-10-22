#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
系統健康檢查 CLI 工具

使用方法:
    python scripts/health_check.py                    # 基本健康檢查
    python scripts/health_check.py --json             # 輸出 JSON 格式
    python scripts/health_check.py --output report.json  # 保存到文件
"""

import sys
import os
import json
import argparse
from pathlib import Path

# 添加項目根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.autobet.health import HealthChecker, HealthStatus


def main():
    """主函數"""
    parser = argparse.ArgumentParser(
        description="BacarratBot 系統健康檢查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/health_check.py                    # 基本健康檢查
  python scripts/health_check.py --json             # JSON 格式輸出
  python scripts/health_check.py --output report.json  # 保存到文件
  python scripts/health_check.py --performance      # 包含性能檢查（需要運行中的系統）
        """
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式輸出結果"
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        help="將結果保存到指定文件"
    )

    parser.add_argument(
        "--performance", "-p",
        action="store_true",
        help="包含性能檢查（需要運行中的系統）"
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="靜默模式，只輸出錯誤"
    )

    args = parser.parse_args()

    # 創建健康檢查器
    checker = HealthChecker(project_root)

    # 執行健康檢查
    try:
        report = checker.check_all(include_performance=args.performance)
    except Exception as e:
        print(f"❌ 健康檢查失敗: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 輸出結果
    if args.json:
        # JSON 格式
        output = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
        print(output)
    elif not args.quiet:
        # 人類可讀格式
        checker.print_report(report)

    # 保存到文件
    if args.output:
        output_path = Path(args.output)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
            if not args.quiet:
                print(f"\n✅ 報告已保存到: {output_path}")
        except Exception as e:
            print(f"❌ 保存報告失敗: {e}", file=sys.stderr)
            sys.exit(1)

    # 根據健康狀態設置退出碼
    if report.overall_status == HealthStatus.HEALTHY:
        sys.exit(0)
    elif report.overall_status == HealthStatus.DEGRADED:
        sys.exit(1)  # 警告
    elif report.overall_status == HealthStatus.UNHEALTHY:
        sys.exit(2)  # 錯誤
    else:
        sys.exit(3)  # 未知


if __name__ == "__main__":
    main()
