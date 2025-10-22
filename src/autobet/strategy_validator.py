# src/autobet/strategy_validator.py
"""策略配置驗證系統"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any

from .lines.config import (
    StrategyDefinition,
    DedupMode,
    AdvanceRule,
    StackPolicy,
    CrossTableMode,
    RiskScope,
    RiskLevelAction,
)


class ValidationLevel(Enum):
    """驗證訊息等級"""
    ERROR = "error"  # 嚴重錯誤,無法執行
    WARNING = "warning"  # 警告,可能有問題
    INFO = "info"  # 資訊,建議優化
    SUCCESS = "success"  # 通過驗證


@dataclass
class ValidationMessage:
    """驗證訊息"""
    level: ValidationLevel
    category: str  # 分類: pattern, staking, risk, logic
    message: str
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """驗證結果"""
    is_valid: bool
    messages: List[ValidationMessage]
    risk_assessment: Dict[str, Any]

    def has_errors(self) -> bool:
        return any(m.level == ValidationLevel.ERROR for m in self.messages)

    def has_warnings(self) -> bool:
        return any(m.level == ValidationLevel.WARNING for m in self.messages)

    def get_messages_by_level(self, level: ValidationLevel) -> List[ValidationMessage]:
        return [m for m in self.messages if m.level == level]


class StrategyValidator:
    """策略驗證器"""

    # Pattern 語法正則表達式
    PATTERN_REGEX = re.compile(r"^([BPT]+)\s+then\s+bet\s+([BP])$", re.IGNORECASE)

    @classmethod
    def validate(cls, definition: StrategyDefinition) -> ValidationResult:
        """完整驗證策略定義"""
        messages = []

        # 1. Pattern 語法驗證
        messages.extend(cls._validate_pattern(definition))

        # 2. Staking 配置驗證
        messages.extend(cls._validate_staking(definition))

        # 3. 風控配置驗證
        messages.extend(cls._validate_risk(definition))

        # 4. 邏輯衝突檢測
        messages.extend(cls._validate_logic_conflicts(definition))

        # 5. 風險評估
        risk_assessment = cls._assess_risk(definition)

        # 判斷是否通過
        is_valid = not any(m.level == ValidationLevel.ERROR for m in messages)

        return ValidationResult(
            is_valid=is_valid,
            messages=messages,
            risk_assessment=risk_assessment
        )

    @classmethod
    def _validate_pattern(cls, definition: StrategyDefinition) -> List[ValidationMessage]:
        """驗證 Pattern 語法"""
        messages = []
        pattern = definition.entry.pattern.strip()

        if not pattern:
            messages.append(ValidationMessage(
                level=ValidationLevel.ERROR,
                category="pattern",
                message="Entry Pattern 不可為空",
                suggestion="請輸入有效的進場條件,例如: 'BB then bet P'"
            ))
            return messages

        # 檢查語法
        match = cls.PATTERN_REGEX.match(pattern)
        if not match:
            messages.append(ValidationMessage(
                level=ValidationLevel.ERROR,
                category="pattern",
                message=f"Pattern 語法錯誤: '{pattern}'",
                suggestion="格式應為: '[BPT]+ then bet [BP]'\n例如: 'BB then bet P' 或 'PPP then bet B'"
            ))
            return messages

        # 成功
        condition_part = match.group(1)
        bet_part = match.group(2)

        messages.append(ValidationMessage(
            level=ValidationLevel.SUCCESS,
            category="pattern",
            message=f"✓ Pattern 語法正確: 觀察 {len(condition_part)} 手後押注 {'閒' if bet_part.upper() == 'P' else '莊'}",
        ))

        # 檢查條件長度
        if len(condition_part) > 10:
            messages.append(ValidationMessage(
                level=ValidationLevel.WARNING,
                category="pattern",
                message=f"條件長度過長 ({len(condition_part)} 手),可能降低觸發頻率",
                suggestion="考慮縮短條件以增加進場機會"
            ))

        # 檢查 Dedup 模式建議
        if definition.entry.dedup == DedupMode.NONE:
            messages.append(ValidationMessage(
                level=ValidationLevel.WARNING,
                category="pattern",
                message="使用 '不去重' 模式,可能產生重複信號",
                suggestion="建議使用 '重疊去重 (OVERLAP)' 避免重複下注"
            ))

        return messages

    @classmethod
    def _validate_staking(cls, definition: StrategyDefinition) -> List[ValidationMessage]:
        """驗證 Staking 配置"""
        messages = []
        staking = definition.staking

        # 檢查序列
        if not staking.sequence:
            messages.append(ValidationMessage(
                level=ValidationLevel.ERROR,
                category="staking",
                message="注碼序列不可為空",
                suggestion="至少設定一層注碼"
            ))
            return messages

        # 檢查序列值
        sequence = [abs(x) for x in staking.sequence]
        if any(x <= 0 for x in sequence):
            messages.append(ValidationMessage(
                level=ValidationLevel.ERROR,
                category="staking",
                message="注碼金額必須大於 0",
                suggestion="請檢查所有層級的金額設定"
            ))

        # 計算總風險
        total_risk = sum(sequence)
        max_single = max(sequence)

        messages.append(ValidationMessage(
            level=ValidationLevel.INFO,
            category="staking",
            message=f"📊 注碼序列: {len(sequence)} 層,總風險 {total_risk} 元,單手最高 {max_single} 元"
        ))

        # 檢查遞增比例
        if len(sequence) > 1:
            ratios = [sequence[i+1] / sequence[i] for i in range(len(sequence) - 1)]
            max_ratio = max(ratios)
            if max_ratio > 3:
                messages.append(ValidationMessage(
                    level=ValidationLevel.WARNING,
                    category="staking",
                    message=f"注碼遞增過快 (最大倍率 {max_ratio:.1f}x),風險較高",
                    suggestion="建議單層倍率不超過 2-3 倍"
                ))

        # 檢查 max_layers
        if staking.max_layers and staking.max_layers < len(sequence):
            messages.append(ValidationMessage(
                level=ValidationLevel.INFO,
                category="staking",
                message=f"最大層數限制 {staking.max_layers} 小於序列長度 {len(sequence)},將限制進層",
            ))

        # 檢查 per_hand_cap
        if staking.per_hand_cap and staking.per_hand_cap < max_single:
            messages.append(ValidationMessage(
                level=ValidationLevel.WARNING,
                category="staking",
                message=f"單手上限 {staking.per_hand_cap} 小於最大注碼 {max_single}",
                suggestion="調整單手上限或減少高層金額"
            ))

        return messages

    @classmethod
    def _validate_risk(cls, definition: StrategyDefinition) -> List[ValidationMessage]:
        """驗證風控配置"""
        messages = []
        levels = definition.risk.levels

        if not levels:
            messages.append(ValidationMessage(
                level=ValidationLevel.WARNING,
                category="risk",
                message="未設定任何風控層級",
                suggestion="建議至少設定一個停損/停利條件"
            ))
            return messages

        # 檢查每個層級
        for i, level in enumerate(levels):
            level_name = f"風控層級 {i+1} ({level.scope.value})"

            # 檢查至少有一個條件
            if not level.take_profit and not level.stop_loss and not level.max_drawdown_losses:
                messages.append(ValidationMessage(
                    level=ValidationLevel.WARNING,
                    category="risk",
                    message=f"{level_name}: 未設定任何觸發條件",
                    suggestion="設定停利、停損或連輸限制"
                ))

            # 檢查停利停損關係
            if level.take_profit and level.stop_loss:
                ratio = level.take_profit / abs(level.stop_loss)
                if ratio < 1:
                    messages.append(ValidationMessage(
                        level=ValidationLevel.WARNING,
                        category="risk",
                        message=f"{level_name}: 停利 ({level.take_profit}) 小於停損 ({abs(level.stop_loss)}),風報比不佳",
                        suggestion="建議停利至少等於停損,理想為 1.5-2 倍"
                    ))

        messages.append(ValidationMessage(
            level=ValidationLevel.SUCCESS,
            category="risk",
            message=f"✓ 已設定 {len(levels)} 個風控層級"
        ))

        return messages

    @classmethod
    def _validate_logic_conflicts(cls, definition: StrategyDefinition) -> List[ValidationMessage]:
        """檢測邏輯衝突"""
        messages = []
        staking = definition.staking

        # 衝突 1: advance_on=LOSS + reset_on_loss=True
        if staking.advance_on == AdvanceRule.LOSS and staking.reset_on_loss:
            messages.append(ValidationMessage(
                level=ValidationLevel.WARNING,
                category="logic",
                message="邏輯衝突: '輸進下一層' 與 '輸了重置' 同時啟用",
                suggestion="這會導致永遠在第一層。建議只保留其中一個設定"
            ))

        # 衝突 2: advance_on=WIN + reset_on_win=True
        if staking.advance_on == AdvanceRule.WIN and staking.reset_on_win:
            messages.append(ValidationMessage(
                level=ValidationLevel.WARNING,
                category="logic",
                message="邏輯衝突: '贏進下一層' 與 '贏了重置' 同時啟用",
                suggestion="這會導致永遠在第一層。建議只保留其中一個設定"
            ))

        # 建議 3: 反向押注 + DedupMode.STRICT
        if staking.sequence and staking.sequence[0] < 0:  # 反向押注
            if definition.entry.dedup == DedupMode.STRICT:
                messages.append(ValidationMessage(
                    level=ValidationLevel.INFO,
                    category="logic",
                    message="使用 '反向押注' + '嚴格去重',可能減少進場機會",
                    suggestion="考慮使用 '重疊去重' 增加觸發頻率"
                ))

        # 建議 4: 單層序列 + advance_on
        if len([abs(x) for x in staking.sequence]) == 1:
            messages.append(ValidationMessage(
                level=ValidationLevel.INFO,
                category="logic",
                message="只有單層注碼,進層規則無效",
                suggestion="增加多層注碼以啟用層級管理"
            ))

        return messages

    @classmethod
    def _assess_risk(cls, definition: StrategyDefinition) -> Dict[str, Any]:
        """風險評估"""
        sequence = [abs(x) for x in definition.staking.sequence]

        total_risk = sum(sequence)
        max_single = max(sequence)
        avg_bet = total_risk / len(sequence)

        # 評估風險等級
        risk_level = "低"
        if total_risk > 10000:
            risk_level = "高"
        elif total_risk > 3000:
            risk_level = "中"

        # 評估進層速度
        speed = "緩慢"
        if len(sequence) > 1:
            ratios = [sequence[i+1] / sequence[i] for i in range(len(sequence) - 1)]
            avg_ratio = sum(ratios) / len(ratios)
            if avg_ratio > 2.5:
                speed = "激進"
            elif avg_ratio > 1.8:
                speed = "中等"

        return {
            "total_risk": total_risk,
            "max_single_bet": max_single,
            "avg_bet": avg_bet,
            "layer_count": len(sequence),
            "risk_level": risk_level,
            "progression_speed": speed,
            "has_risk_control": len(definition.risk.levels) > 0,
            "dedup_safe": definition.entry.dedup != DedupMode.NONE,
        }
