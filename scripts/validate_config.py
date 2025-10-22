#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置驗證工具

驗證所有配置文件的正確性，包括：
1. positions.json - 螢幕座標邊界檢查
2. chip_profiles/*.json - 籌碼配置與限制檢查
3. line_strategies/*.json - 策略序列與資金限制檢查
4. .env - 環境變數範圍檢查

使用方法:
    python scripts/validate_config.py
    python scripts/validate_config.py --verbose
    python scripts/validate_config.py --fix  # 自動修復簡單問題
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

# 設置 UTF-8 編碼輸出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class Severity(Enum):
    """問題嚴重程度"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ValidationIssue:
    """驗證問題"""
    severity: Severity
    category: str
    file_path: str
    message: str
    suggestion: Optional[str] = None


class ConfigValidator:
    """配置驗證器"""

    def __init__(self, project_root: Path, verbose: bool = False):
        self.project_root = project_root
        self.verbose = verbose
        self.issues: List[ValidationIssue] = []

    def add_issue(self, severity: Severity, category: str, file_path: str,
                  message: str, suggestion: Optional[str] = None):
        """添加驗證問題"""
        issue = ValidationIssue(severity, category, file_path, message, suggestion)
        self.issues.append(issue)
        if self.verbose:
            self._print_issue(issue)

    def _print_issue(self, issue: ValidationIssue):
        """打印問題"""
        severity_symbols = {
            Severity.INFO: "ℹ️",
            Severity.WARNING: "⚠️",
            Severity.ERROR: "❌",
            Severity.CRITICAL: "🔥"
        }
        symbol = severity_symbols.get(issue.severity, "❓")
        print(f"{symbol} [{issue.severity.value}] {issue.category}")
        print(f"   文件: {issue.file_path}")
        print(f"   問題: {issue.message}")
        if issue.suggestion:
            print(f"   建議: {issue.suggestion}")
        print()

    def validate_all(self) -> int:
        """驗證所有配置，返回錯誤數量"""
        print("=" * 70)
        print("配置驗證工具")
        print("=" * 70)
        print()

        # 驗證各個配置文件
        self.validate_positions()
        self.validate_chip_profiles()
        self.validate_strategies()
        self.validate_env()

        # 生成報告
        self.print_report()

        # 返回錯誤數量
        error_count = sum(1 for issue in self.issues
                         if issue.severity in [Severity.ERROR, Severity.CRITICAL])
        return error_count

    def validate_positions(self):
        """驗證 positions.json"""
        positions_file = self.project_root / "configs" / "positions.json"

        if not positions_file.exists():
            self.add_issue(
                Severity.ERROR,
                "Positions",
                str(positions_file),
                "配置文件不存在",
                "從 positions.sample.json 複製並修改"
            )
            return

        try:
            with open(positions_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            self.add_issue(
                Severity.CRITICAL,
                "Positions",
                str(positions_file),
                f"JSON 格式錯誤: {e}",
                "檢查 JSON 語法"
            )
            return

        # 檢查螢幕尺寸
        screen = config.get("screen", {})
        width = screen.get("width", 0)
        height = screen.get("height", 0)

        if width <= 0 or height <= 0:
            self.add_issue(
                Severity.ERROR,
                "Positions",
                str(positions_file),
                f"螢幕尺寸無效: {width}x{height}",
                "設置正確的螢幕解析度"
            )

        # 檢查所有點位是否在螢幕範圍內
        points = config.get("points", {})
        for name, point in points.items():
            x, y = point.get("x", 0), point.get("y", 0)
            if not (0 <= x <= width and 0 <= y <= height):
                self.add_issue(
                    Severity.WARNING,
                    "Positions",
                    str(positions_file),
                    f"點位 '{name}' 超出螢幕範圍: ({x}, {y})",
                    f"調整至 0-{width}x0-{height} 範圍內"
                )

        # 檢查所有 ROI 是否在螢幕範圍內
        roi = config.get("roi", {})
        for name, rect in roi.items():
            x, y = rect.get("x", 0), rect.get("y", 0)
            w, h = rect.get("w", 0), rect.get("h", 0)

            if x + w > width or y + h > height:
                self.add_issue(
                    Severity.WARNING,
                    "Positions",
                    str(positions_file),
                    f"ROI '{name}' 超出螢幕範圍: ({x}, {y}, {w}, {h})",
                    f"調整至螢幕範圍內"
                )

            if w <= 0 or h <= 0:
                self.add_issue(
                    Severity.ERROR,
                    "Positions",
                    str(positions_file),
                    f"ROI '{name}' 尺寸無效: {w}x{h}",
                    "寬高必須大於 0"
                )

        # 檢查 DPI 縮放係數
        dpi_scale = screen.get("dpi_scale", 1.0)
        if not (0.5 <= dpi_scale <= 3.0):
            self.add_issue(
                Severity.WARNING,
                "Positions",
                str(positions_file),
                f"DPI 縮放係數異常: {dpi_scale}",
                "通常應在 0.5 到 3.0 之間"
            )

    def validate_chip_profiles(self):
        """驗證 chip_profiles/*.json"""
        chip_profiles_dir = self.project_root / "configs" / "chip_profiles"

        if not chip_profiles_dir.exists():
            self.add_issue(
                Severity.ERROR,
                "ChipProfiles",
                str(chip_profiles_dir),
                "chip_profiles 目錄不存在"
            )
            return

        # 至少要有一個 profile
        profiles = list(chip_profiles_dir.glob("*.json"))
        if not profiles:
            self.add_issue(
                Severity.ERROR,
                "ChipProfiles",
                str(chip_profiles_dir),
                "未找到任何籌碼配置文件",
                "至少需要一個 .json 配置文件"
            )
            return

        # 驗證每個 profile
        for profile_file in profiles:
            self._validate_chip_profile(profile_file)

    def _validate_chip_profile(self, profile_file: Path):
        """驗證單個籌碼配置文件"""
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            self.add_issue(
                Severity.CRITICAL,
                "ChipProfiles",
                str(profile_file),
                f"JSON 格式錯誤: {e}"
            )
            return

        # 檢查必要字段
        required_fields = ["profile_name", "chips", "bet_positions", "constraints"]
        for field in required_fields:
            if field not in config:
                self.add_issue(
                    Severity.ERROR,
                    "ChipProfiles",
                    str(profile_file),
                    f"缺少必要字段: {field}"
                )

        # 檢查籌碼配置
        chips = config.get("chips", [])
        if not chips:
            self.add_issue(
                Severity.ERROR,
                "ChipProfiles",
                str(profile_file),
                "沒有配置任何籌碼"
            )
        else:
            calibrated_chips = [c for c in chips if c.get("calibrated", False)]
            if not calibrated_chips:
                self.add_issue(
                    Severity.WARNING,
                    "ChipProfiles",
                    str(profile_file),
                    "沒有任何已校準的籌碼",
                    "至少需要一個已校準的籌碼"
                )

            # 檢查籌碼值是否合理
            for chip in chips:
                value = chip.get("value", 0)
                if value <= 0:
                    self.add_issue(
                        Severity.ERROR,
                        "ChipProfiles",
                        str(profile_file),
                        f"籌碼 {chip.get('label', '?')} 的值無效: {value}"
                    )

                # 檢查已校準的籌碼座標
                if chip.get("calibrated", False):
                    x, y = chip.get("x", 0), chip.get("y", 0)
                    if x == 0 and y == 0:
                        self.add_issue(
                            Severity.WARNING,
                            "ChipProfiles",
                            str(profile_file),
                            f"籌碼 {chip.get('label', '?')} 標記為已校準但座標為 (0, 0)"
                        )

        # 檢查下注位置
        bet_positions = config.get("bet_positions", {})
        required_positions = ["banker", "player", "confirm"]
        for pos in required_positions:
            if pos not in bet_positions:
                self.add_issue(
                    Severity.ERROR,
                    "ChipProfiles",
                    str(profile_file),
                    f"缺少必要的下注位置: {pos}"
                )
            elif not bet_positions[pos].get("calibrated", False):
                self.add_issue(
                    Severity.WARNING,
                    "ChipProfiles",
                    str(profile_file),
                    f"下注位置 '{pos}' 未校準"
                )

        # 檢查限制
        constraints = config.get("constraints", {})
        min_bet = constraints.get("min_bet", 0)
        max_bet = constraints.get("max_bet", 0)

        if min_bet <= 0:
            self.add_issue(
                Severity.ERROR,
                "ChipProfiles",
                str(profile_file),
                f"最小下注金額無效: {min_bet}"
            )

        if max_bet <= min_bet:
            self.add_issue(
                Severity.ERROR,
                "ChipProfiles",
                str(profile_file),
                f"最大下注金額 ({max_bet}) 必須大於最小下注金額 ({min_bet})"
            )

        # 檢查籌碼組合是否能達到最小下注
        if chips:
            min_chip_value = min(c.get("value", float('inf')) for c in chips
                                if c.get("calibrated", False))
            if min_chip_value > min_bet:
                self.add_issue(
                    Severity.WARNING,
                    "ChipProfiles",
                    str(profile_file),
                    f"最小籌碼值 ({min_chip_value}) 大於最小下注額 ({min_bet})",
                    "確保有足夠小的籌碼"
                )

    def validate_strategies(self):
        """驗證 line_strategies/*.json"""
        strategies_dir = self.project_root / "configs" / "line_strategies"

        if not strategies_dir.exists():
            self.add_issue(
                Severity.WARNING,
                "Strategies",
                str(strategies_dir),
                "line_strategies 目錄不存在",
                "如果使用 Line 策略系統，需要創建此目錄"
            )
            return

        strategies = list(strategies_dir.glob("*.json"))
        if not strategies:
            self.add_issue(
                Severity.WARNING,
                "Strategies",
                str(strategies_dir),
                "未找到任何策略配置文件"
            )
            return

        # 驗證每個策略
        for strategy_file in strategies:
            self._validate_strategy(strategy_file)

    def _validate_strategy(self, strategy_file: Path):
        """驗證單個策略配置"""
        try:
            with open(strategy_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            self.add_issue(
                Severity.CRITICAL,
                "Strategies",
                str(strategy_file),
                f"JSON 格式錯誤: {e}"
            )
            return

        # 檢查必要字段
        if "entry" not in config:
            self.add_issue(
                Severity.ERROR,
                "Strategies",
                str(strategy_file),
                "缺少 entry 配置"
            )

        if "staking" not in config:
            self.add_issue(
                Severity.ERROR,
                "Strategies",
                str(strategy_file),
                "缺少 staking 配置"
            )
            return

        # 檢查下注序列
        staking = config.get("staking", {})
        sequence = staking.get("sequence", [])

        if not sequence:
            self.add_issue(
                Severity.ERROR,
                "Strategies",
                str(strategy_file),
                "下注序列為空"
            )
            return

        # 檢查序列值是否合理
        for i, amount in enumerate(sequence, 1):
            if amount <= 0:
                self.add_issue(
                    Severity.ERROR,
                    "Strategies",
                    str(strategy_file),
                    f"下注序列第 {i} 層金額無效: {amount}"
                )

        # 檢查序列總和（最壞情況）
        max_loss = sum(sequence)
        if max_loss > 100000:  # 警告閾值
            self.add_issue(
                Severity.WARNING,
                "Strategies",
                str(strategy_file),
                f"下注序列總金額過大: {max_loss}",
                "確認這是預期的風險承受範圍"
            )

        # 檢查序列是否遞增（常見模式）
        if staking.get("advance_on") == "loss" and len(sequence) > 1:
            for i in range(len(sequence) - 1):
                if sequence[i] >= sequence[i + 1]:
                    self.add_issue(
                        Severity.INFO,
                        "Strategies",
                        str(strategy_file),
                        f"下注序列非遞增: {sequence[i]} → {sequence[i+1]}",
                        "通常虧損加注應該遞增"
                    )
                    break

        # 檢查風險限制
        risk = config.get("risk", {})
        levels = risk.get("levels", [])

        for level in levels:
            scope = level.get("scope", "")
            take_profit = level.get("take_profit")
            stop_loss = level.get("stop_loss")

            if take_profit is not None and take_profit <= 0:
                self.add_issue(
                    Severity.WARNING,
                    "Strategies",
                    str(strategy_file),
                    f"止盈目標 ({scope}) 應為正數: {take_profit}"
                )

            if stop_loss is not None and stop_loss >= 0:
                self.add_issue(
                    Severity.WARNING,
                    "Strategies",
                    str(strategy_file),
                    f"止損限制 ({scope}) 應為負數: {stop_loss}"
                )

            # 檢查止盈是否遠大於最大損失
            if take_profit and stop_loss and abs(stop_loss) > take_profit * 2:
                self.add_issue(
                    Severity.WARNING,
                    "Strategies",
                    str(strategy_file),
                    f"止損額 ({abs(stop_loss)}) 遠大於止盈額 ({take_profit})",
                    "檢查風險/收益比是否合理"
                )

    def validate_env(self):
        """驗證 .env 環境變數"""
        env_file = self.project_root / ".env"

        if not env_file.exists():
            self.add_issue(
                Severity.WARNING,
                "Environment",
                str(env_file),
                ".env 文件不存在",
                "從 .env.example 複製並修改"
            )
            return

        # 讀取環境變數
        env_vars = {}
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
        except Exception as e:
            self.add_issue(
                Severity.ERROR,
                "Environment",
                str(env_file),
                f"讀取失敗: {e}"
            )
            return

        # 檢查 DRY_RUN
        dry_run = env_vars.get("DRY_RUN", "1")
        if dry_run not in ["0", "1"]:
            self.add_issue(
                Severity.ERROR,
                "Environment",
                str(env_file),
                f"DRY_RUN 值無效: {dry_run}",
                "應為 0 或 1"
            )

        # 檢查 SCREEN_DPI_SCALE
        dpi_scale = env_vars.get("SCREEN_DPI_SCALE", "1.0")
        try:
            dpi_value = float(dpi_scale)
            if not (0.5 <= dpi_value <= 3.0):
                self.add_issue(
                    Severity.WARNING,
                    "Environment",
                    str(env_file),
                    f"SCREEN_DPI_SCALE 值異常: {dpi_value}",
                    "通常應在 0.5 到 3.0 之間"
                )
        except ValueError:
            self.add_issue(
                Severity.ERROR,
                "Environment",
                str(env_file),
                f"SCREEN_DPI_SCALE 格式錯誤: {dpi_scale}"
            )

        # 檢查 LOG_LEVEL
        log_level = env_vars.get("LOG_LEVEL", "INFO")
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level not in valid_levels:
            self.add_issue(
                Severity.WARNING,
                "Environment",
                str(env_file),
                f"LOG_LEVEL 值無效: {log_level}",
                f"應為 {', '.join(valid_levels)} 之一"
            )

        # 檢查 EVENT_SOURCE_MODE
        event_mode = env_vars.get("EVENT_SOURCE_MODE", "demo")
        valid_modes = ["sse", "ndjson", "demo"]
        if event_mode not in valid_modes:
            self.add_issue(
                Severity.WARNING,
                "Environment",
                str(env_file),
                f"EVENT_SOURCE_MODE 值無效: {event_mode}",
                f"應為 {', '.join(valid_modes)} 之一"
            )

        # 檢查 DEMO_ROUND_INTERVAL_SEC
        demo_interval = env_vars.get("DEMO_ROUND_INTERVAL_SEC", "15")
        try:
            interval_value = int(demo_interval)
            if not (1 <= interval_value <= 300):
                self.add_issue(
                    Severity.WARNING,
                    "Environment",
                    str(env_file),
                    f"DEMO_ROUND_INTERVAL_SEC 值異常: {interval_value}",
                    "建議在 1 到 300 秒之間"
                )
        except ValueError:
            self.add_issue(
                Severity.ERROR,
                "Environment",
                str(env_file),
                f"DEMO_ROUND_INTERVAL_SEC 格式錯誤: {demo_interval}"
            )

    def print_report(self):
        """打印驗證報告"""
        print()
        print("=" * 70)
        print("驗證報告")
        print("=" * 70)
        print()

        if not self.issues:
            print("✅ 所有配置文件驗證通過，未發現問題！")
            print()
            return

        # 按嚴重程度分組
        by_severity = {}
        for issue in self.issues:
            severity = issue.severity
            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(issue)

        # 打印統計
        print(f"總計發現 {len(self.issues)} 個問題：")
        for severity in [Severity.CRITICAL, Severity.ERROR, Severity.WARNING, Severity.INFO]:
            if severity in by_severity:
                count = len(by_severity[severity])
                print(f"  {severity.value}: {count}")
        print()

        # 如果沒有在 verbose 模式下打印過，現在打印
        if not self.verbose:
            print("-" * 70)
            print()
            for issue in self.issues:
                self._print_issue(issue)

        # 總結
        critical_count = len(by_severity.get(Severity.CRITICAL, []))
        error_count = len(by_severity.get(Severity.ERROR, []))

        if critical_count > 0:
            print("🔥 發現嚴重問題，必須立即修復！")
        elif error_count > 0:
            print("❌ 發現錯誤，建議盡快修復")
        else:
            print("⚠️ 發現一些警告，建議檢查")

        print()


def main():
    """主函數"""
    import argparse

    parser = argparse.ArgumentParser(description="BacarratBot 配置驗證工具")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="詳細模式，實時打印問題")
    parser.add_argument("--fix", action="store_true",
                       help="自動修復簡單問題（暫未實現）")

    args = parser.parse_args()

    # 找到專案根目錄
    project_root = Path(__file__).parent.parent

    # 創建驗證器
    validator = ConfigValidator(project_root, verbose=args.verbose)

    # 執行驗證
    error_count = validator.validate_all()

    # 返回錯誤碼
    if error_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
