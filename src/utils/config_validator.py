# src/utils/config_validator.py
"""
配置驗證器 - 檢查系統配置完整性
"""
import os
import json
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """驗證結果"""
    complete: bool
    message: str
    details: List[str]
    missing_items: List[str]


class ConfigValidator:
    """配置完整性驗證器"""

    def __init__(self):
        self.chip_profile_path = "configs/chip_profiles/default.json"
        self.positions_path = "configs/positions.json"
        self.strategy_path = "configs/strategy.json"

    def validate_all(self) -> Dict[str, ValidationResult]:
        """
        驗證所有配置

        Returns:
            Dict包含各部分的驗證結果:
            {
                'chip_profile': ValidationResult,
                'positions': ValidationResult,
                'strategy': ValidationResult,
                'overlay': ValidationResult,
                'overall': ValidationResult
            }
        """
        results = {}

        # 1. 驗證ChipProfile
        results['chip_profile'] = self.validate_chip_profile()

        # 2. 驗證位置校準
        results['positions'] = self.validate_positions()

        # 3. 驗證策略設定
        results['strategy'] = self.validate_strategy()

        # 4. 驗證Overlay檢測
        results['overlay'] = self.validate_overlay()

        # 5. 總體評估
        all_complete = all(r.complete for r in results.values())
        completed_count = sum(1 for r in results.values() if r.complete)
        total_count = len(results)

        if all_complete:
            overall_message = f"✅ 所有配置已完成 ({completed_count}/{total_count})"
        else:
            overall_message = f"⚠️ 配置未完成 ({completed_count}/{total_count})"

        missing_modules = [
            name for name, result in results.items()
            if not result.complete
        ]

        results['overall'] = ValidationResult(
            complete=all_complete,
            message=overall_message,
            details=[f"{name}: {result.message}" for name, result in results.items()],
            missing_items=missing_modules
        )

        return results

    def validate_chip_profile(self) -> ValidationResult:
        """
        驗證ChipProfile配置

        檢查項目:
        - 文件是否存在
        - 至少2顆籌碼已設定金額
        - 至少2顆籌碼已校準位置
        - 下注位置(banker, player, confirm)已校準
        """
        details = []
        missing = []

        # 檢查文件存在
        if not os.path.exists(self.chip_profile_path):
            return ValidationResult(
                complete=False,
                message="❌ 籌碼配置文件不存在",
                details=["請先在「籌碼設定」頁面創建配置"],
                missing_items=["chip_profile_file"]
            )

        try:
            with open(self.chip_profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 檢查籌碼設定
            chips = data.get('chips', [])
            calibrated_chips = [
                chip for chip in chips
                if chip.get('calibrated', False) and chip.get('value', 0) > 0
            ]

            if len(calibrated_chips) < 2:
                details.append(f"❌ 僅{len(calibrated_chips)}顆籌碼已校準，至少需要2顆")
                missing.append("chips_calibration")
            else:
                details.append(f"✅ {len(calibrated_chips)}顆籌碼已校準")

            # 檢查下注位置
            bet_positions = data.get('bet_positions', {})
            required_positions = ['banker', 'player', 'confirm']
            calibrated_positions = [
                pos for pos in required_positions
                if bet_positions.get(pos, {}).get('calibrated', False)
            ]

            if len(calibrated_positions) < len(required_positions):
                missing_pos = set(required_positions) - set(calibrated_positions)
                details.append(f"❌ 下注位置未完成: {', '.join(missing_pos)}")
                missing.append("bet_positions")
            else:
                details.append("✅ 所有必要下注位置已校準")

            # 檢查cancel位置（可選但建議）
            if not bet_positions.get('cancel', {}).get('calibrated', False):
                details.append("⚠️ 建議校準「取消」按鈕")

            complete = len(missing) == 0
            message = "✅ 籌碼配置完整" if complete else f"⚠️ 籌碼配置不完整 ({len(missing)}項缺失)"

            return ValidationResult(
                complete=complete,
                message=message,
                details=details,
                missing_items=missing
            )

        except Exception as e:
            return ValidationResult(
                complete=False,
                message=f"❌ 讀取籌碼配置失敗",
                details=[str(e)],
                missing_items=["chip_profile_error"]
            )

    def validate_positions(self) -> ValidationResult:
        """
        驗證positions.json中的ROI設定

        雖然ChipProfile已包含位置校準,
        但positions.json仍需要ROI設定供檢測使用
        """
        details = []
        missing = []

        if not os.path.exists(self.positions_path):
            return ValidationResult(
                complete=False,
                message="❌ positions.json不存在",
                details=["請先在「可下注判斷」或「位置校準」頁面創建"],
                missing_items=["positions_file"]
            )

        try:
            with open(self.positions_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 檢查ROI設定
            roi = data.get('roi', {})
            required_rois = ['overlay', 'timer']

            for roi_name in required_rois:
                roi_data = roi.get(roi_name)
                if not roi_data or not all(k in roi_data for k in ['x', 'y', 'w', 'h']):
                    details.append(f"❌ ROI '{roi_name}' 未設定")
                    missing.append(f"roi_{roi_name}")
                else:
                    details.append(f"✅ ROI '{roi_name}' 已設定")

            complete = len(missing) == 0
            message = "✅ ROI設定完整" if complete else f"⚠️ ROI設定不完整"

            return ValidationResult(
                complete=complete,
                message=message,
                details=details,
                missing_items=missing
            )

        except Exception as e:
            return ValidationResult(
                complete=False,
                message=f"❌ 讀取positions.json失敗",
                details=[str(e)],
                missing_items=["positions_error"]
            )

    def validate_strategy(self) -> ValidationResult:
        """
        驗證策略配置

        檢查strategy.json是否存在且有效
        """
        details = []
        missing = []

        if not os.path.exists(self.strategy_path):
            return ValidationResult(
                complete=False,
                message="❌ 策略配置不存在",
                details=["請先在「策略設定」頁面創建策略"],
                missing_items=["strategy_file"]
            )

        try:
            with open(self.strategy_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 檢查必要欄位（兼容 target 和 targets）
            required_fields = {
                'target_or_targets': ['target', 'targets'],  # 二選一
                'unit': ['unit'],
            }

            for field_name, field_options in required_fields.items():
                found = any(opt in data for opt in field_options)
                if not found:
                    details.append(f"❌ 缺少欄位: {' 或 '.join(field_options)}")
                    missing.append(f"strategy_{field_name}")
                else:
                    found_field = next(opt for opt in field_options if opt in data)
                    details.append(f"✅ {found_field} 已設定")

            # 檢查unit是否合理
            unit = data.get('unit', 0)
            if unit <= 0:
                details.append(f"❌ 單位金額無效: {unit}")
                missing.append("strategy_unit_invalid")

            complete = len(missing) == 0
            message = "✅ 策略配置完整" if complete else f"⚠️ 策略配置不完整"

            return ValidationResult(
                complete=complete,
                message=message,
                details=details,
                missing_items=missing
            )

        except Exception as e:
            return ValidationResult(
                complete=False,
                message=f"❌ 讀取策略配置失敗",
                details=[str(e)],
                missing_items=["strategy_error"]
            )

    def validate_overlay(self) -> ValidationResult:
        """
        驗證Overlay檢測配置

        檢查:
        - overlay_params存在
        - template_paths設定
        - 模板文件存在
        """
        details = []
        missing = []

        if not os.path.exists(self.positions_path):
            return ValidationResult(
                complete=False,
                message="❌ positions.json不存在",
                details=["請先設定positions.json"],
                missing_items=["positions_file"]
            )

        try:
            with open(self.positions_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 檢查overlay_params
            overlay_params = data.get('overlay_params', {})
            if not overlay_params:
                return ValidationResult(
                    complete=False,
                    message="❌ Overlay參數未設定",
                    details=["請在「可下注判斷」頁面設定檢測參數"],
                    missing_items=["overlay_params"]
                )

            # 檢查template_paths
            template_paths = overlay_params.get('template_paths', {})
            qing_path = template_paths.get('qing')

            if not qing_path:
                details.append("❌ 檢測模板路徑未設定")
                missing.append("template_path")
            elif not os.path.exists(qing_path):
                details.append(f"❌ 檢測模板不存在: {qing_path}")
                missing.append("template_file")
            else:
                details.append(f"✅ 檢測模板已設定: {os.path.basename(qing_path)}")

            # 檢查NCC閾值
            ncc_threshold = overlay_params.get('ncc_threshold', 0)
            if ncc_threshold <= 0:
                details.append(f"❌ NCC閾值未設定")
                missing.append("ncc_threshold")
            else:
                details.append(f"✅ NCC閾值: {ncc_threshold}")

            complete = len(missing) == 0
            message = "✅ 檢測配置完整" if complete else f"⚠️ 檢測配置不完整"

            return ValidationResult(
                complete=complete,
                message=message,
                details=details,
                missing_items=missing
            )

        except Exception as e:
            return ValidationResult(
                complete=False,
                message=f"❌ 讀取Overlay配置失敗",
                details=[str(e)],
                missing_items=["overlay_error"]
            )

    def get_config_summary(self) -> Dict[str, Any]:
        """
        獲取配置摘要信息

        Returns:
            {
                'completion_rate': float,  # 0.0 - 1.0
                'completed_modules': int,
                'total_modules': int,
                'ready_for_battle': bool,
                'missing_critical': List[str],
                'suggestions': List[str]
            }
        """
        results = self.validate_all()

        # 計算完成度
        modules = ['chip_profile', 'positions', 'strategy', 'overlay']
        completed = sum(1 for m in modules if results[m].complete)
        total = len(modules)
        completion_rate = completed / total if total > 0 else 0

        # 收集缺失項目
        missing_critical = []
        for module in modules:
            if not results[module].complete:
                missing_critical.extend(results[module].missing_items)

        # 生成建議
        suggestions = []
        if not results['chip_profile'].complete:
            suggestions.append("請先完成籌碼設定和校準")
        if not results['positions'].complete:
            suggestions.append("請設定ROI區域")
        if not results['strategy'].complete:
            suggestions.append("請設定投注策略")
        if not results['overlay'].complete:
            suggestions.append("請設定檢測模板")

        ready = results['overall'].complete

        return {
            'completion_rate': completion_rate,
            'completed_modules': completed,
            'total_modules': total,
            'ready_for_battle': ready,
            'missing_critical': missing_critical,
            'suggestions': suggestions,
            'results': results
        }


# 便捷函數
def quick_validate() -> Tuple[bool, str, List[str]]:
    """
    快速驗證配置

    Returns:
        (ready, message, issues)
    """
    validator = ConfigValidator()
    summary = validator.get_config_summary()

    ready = summary['ready_for_battle']
    completion = summary['completion_rate'] * 100

    if ready:
        message = f"✅ 配置完整 ({completion:.0f}%)，可以開始實戰"
    else:
        message = f"⚠️ 配置未完成 ({completion:.0f}%)"

    issues = summary['suggestions']

    return ready, message, issues
