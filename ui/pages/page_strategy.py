# ui/pages/page_strategy.py
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.autobet.lines.config import (
    AdvanceRule,
    CrossTableLayerConfig,
    CrossTableMode,
    DedupMode,
    RiskLevelAction,
    RiskLevelConfig,
    RiskScope,
    StackPolicy,
    StrategyDefinition,
    load_strategy_definitions,
    parse_strategy_definition,
)
from src.autobet.chip_planner import Chip, SmartChipPlanner, BettingPolicy
from src.autobet.chip_profile_manager import ChipProfileManager

from ..app_state import emit_toast


DEDUP_LABELS = {
    DedupMode.NONE: "不去重",
    DedupMode.OVERLAP: "重疊去重",
    DedupMode.STRICT: "嚴格去重",
}

ADVANCE_LABELS = {
    AdvanceRule.LOSS: "輸進下一層",
    AdvanceRule.WIN: "贏進下一層",
}

STACK_LABELS = {
    StackPolicy.NONE: "禁止疊注",
    StackPolicy.MERGE: "合併注單",
    StackPolicy.PARALLEL: "平行下單",
}

MODE_LABELS = {
    CrossTableMode.RESET: "每桌獨立層數",
    CrossTableMode.ACCUMULATE: "跨桌累進層數",
}

RISK_SCOPE_LABELS = {
    RiskScope.GLOBAL_DAY: "全域單日",
    RiskScope.TABLE: "桌別",
    RiskScope.TABLE_STRATEGY: "桌別×策略",
    RiskScope.ALL_TABLES_STRATEGY: "跨桌×策略",
    RiskScope.MULTI_STRATEGY: "多策略組",
}

RISK_ACTION_LABELS = {
    RiskLevelAction.PAUSE: "暫停",
    RiskLevelAction.STOP_ALL: "全面停用",
    RiskLevelAction.NOTIFY: "僅提醒",
}


class RiskTableWidget(QTableWidget):
    headers = ["層級", "停利", "停損", "連輸限制", "動作", "冷卻秒"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(0, len(self.headers), parent)
        self.setHorizontalHeaderLabels(self.headers)
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setStyleSheet(
            """
            QTableWidget {
                background-color: #111827;
                border: 1px solid #374151;
                color: #f3f4f6;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #1f2937;
                color: #d1d5db;
                padding: 6px;
                border: 1px solid #374151;
            }
            """
        )

    def add_row(self, level: Optional[RiskLevelConfig] = None) -> None:
        row = self.rowCount()
        self.insertRow(row)

        scope_combo = QComboBox()
        for scope in RiskScope:
            scope_combo.addItem(RISK_SCOPE_LABELS[scope], scope.value)
        if level:
            scope_combo.setCurrentIndex(scope_combo.findData(level.scope.value))

        take_profit = self._make_double_box(level.take_profit if level else None)
        stop_loss = self._make_double_box(level.stop_loss if level else None)
        max_losses = self._make_int_box(level.max_drawdown_losses if level else None)

        action_combo = QComboBox()
        for action in RiskLevelAction:
            action_combo.addItem(RISK_ACTION_LABELS[action], action.value)
        if level:
            action_combo.setCurrentIndex(action_combo.findData(level.action.value))

        cooldown = self._make_double_box(level.cooldown_sec if level else None)

        self.setCellWidget(row, 0, scope_combo)
        self.setCellWidget(row, 1, take_profit)
        self.setCellWidget(row, 2, stop_loss)
        self.setCellWidget(row, 3, max_losses)
        self.setCellWidget(row, 4, action_combo)
        self.setCellWidget(row, 5, cooldown)

    @staticmethod
    def _make_double_box(value: Optional[float]) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(-1e6, 1e6)
        box.setDecimals(2)
        box.setSingleStep(10.0)
        box.setSpecialValueText("--")
        if value is None:
            box.setValue(box.minimum())
        else:
            box.setValue(float(value))
        return box

    @staticmethod
    def _make_int_box(value: Optional[int]) -> QSpinBox:
        box = QSpinBox()
        box.setRange(0, 100)
        box.setSpecialValueText("--")
        if value is None:
            box.setValue(box.minimum())
        else:
            box.setValue(int(value))
        return box

    def load_levels(self, levels: List[RiskLevelConfig]) -> None:
        self.setRowCount(0)
        for level in levels:
            self.add_row(level)

    def levels(self) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for row in range(self.rowCount()):
            scope_combo = self.cellWidget(row, 0)
            take_profit = self.cellWidget(row, 1)
            stop_loss = self.cellWidget(row, 2)
            max_losses = self.cellWidget(row, 3)
            action_combo = self.cellWidget(row, 4)
            cooldown = self.cellWidget(row, 5)

            def val(box: QDoubleSpinBox) -> Optional[float]:
                if box.specialValueText() and box.value() == box.minimum():
                    return None
                return float(box.value())

            def ival(box: QSpinBox) -> Optional[int]:
                if box.specialValueText() and box.value() == box.minimum():
                    return None
                return int(box.value())

            entry = {
                "scope": scope_combo.currentData(),
                "take_profit": val(take_profit),
                "stop_loss": val(stop_loss),
                "max_drawdown_losses": ival(max_losses),
                "action": action_combo.currentData(),
                "cooldown_sec": val(cooldown),
            }
            result.append(entry)
        return result


class StrategyPage(QWidget):
    """Line 策略設定頁"""

    strategy_changed = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        directory = os.getenv("LINE_STRATEGY_DIR", "configs/line_strategies")
        self.strategy_dir = Path(directory)
        self.strategy_dir.mkdir(parents=True, exist_ok=True)

        self.definitions: Dict[str, StrategyDefinition] = {}
        self.current_key: Optional[str] = None
        self.current_data: Dict[str, Any] = {}

        self._build_ui()
        self.reload_strategies()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        header = QLabel("🧠 策略設定")
        header.setFont(QFont("Microsoft YaHei UI", 18, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                background-color: #1f2937;
                color: #f9fafb;
                border-radius: 10px;
                padding: 16px;
            }
        """)
        main_layout.addWidget(header)

        toolbar = QHBoxLayout()
        self.reload_btn = QPushButton("重新整理")
        self.new_btn = QPushButton("新增策略")
        self.duplicate_btn = QPushButton("複製策略")
        self.delete_btn = QPushButton("刪除策略")
        self.open_dir_btn = QPushButton("開啟資料夾")
        for btn in (self.reload_btn, self.new_btn, self.duplicate_btn, self.delete_btn, self.open_dir_btn):
            btn.setStyleSheet("QPushButton { padding: 6px 12px; border-radius: 6px; background-color: #374151; color: #f3f4f6; }")
        toolbar.addWidget(self.reload_btn)
        toolbar.addWidget(self.new_btn)
        toolbar.addWidget(self.duplicate_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.open_dir_btn)
        main_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, 1)

        self.strategy_list = QListWidget()
        self.strategy_list.setStyleSheet("""
            QListWidget {
                background-color: #111827;
                border: 1px solid #374151;
                color: #f3f4f6;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
        """)
        splitter.addWidget(self.strategy_list)

        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        detail_layout.addWidget(scroll)

        self.detail_widget = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_widget)
        self.detail_layout.setSpacing(12)
        self.detail_layout.setContentsMargins(4, 4, 4, 40)
        scroll.setWidget(self.detail_widget)

        splitter.addWidget(detail_container)
        splitter.setSizes([220, 680])

        self._build_entry_section()
        self._build_staking_section()
        self._build_cross_table_section()
        self._build_risk_section()

        self.detail_layout.addStretch()

        action_bar = QHBoxLayout()
        self.save_btn = QPushButton("儲存變更")
        self.save_as_btn = QPushButton("另存為...")
        self.revert_btn = QPushButton("還原")
        for btn in (self.save_btn, self.save_as_btn, self.revert_btn):
            btn.setStyleSheet("QPushButton { padding: 8px 16px; border-radius: 6px; background-color: #0e7490; color: white; }")
        action_bar.addWidget(self.save_btn)
        action_bar.addWidget(self.save_as_btn)
        action_bar.addWidget(self.revert_btn)
        action_bar.addStretch()
        main_layout.addLayout(action_bar)

        self.reload_btn.clicked.connect(self.reload_strategies)
        self.new_btn.clicked.connect(self.create_strategy)
        self.duplicate_btn.clicked.connect(self.duplicate_strategy)
        self.delete_btn.clicked.connect(self.delete_strategy)
        self.open_dir_btn.clicked.connect(self.open_directory)
        self.save_btn.clicked.connect(self.save_current_strategy)
        self.save_as_btn.clicked.connect(lambda: self.save_current_strategy(save_as=True))
        self.revert_btn.clicked.connect(self.revert_changes)
        self.strategy_list.itemSelectionChanged.connect(self._on_strategy_selected)

    # ------------------------------------------------------------------
    def _build_entry_section(self) -> None:
        group = QGroupBox("進場設定")
        form = QFormLayout(group)
        self.entry_pattern = QLineEdit()
        self.entry_window = QDoubleSpinBox()
        self.entry_window.setRange(0.0, 3600.0)
        self.entry_window.setSuffix(" 秒")
        self.entry_dedup = QComboBox()
        for mode in DedupMode:
            self.entry_dedup.addItem(DEDUP_LABELS[mode], mode.value)
        self.entry_first_trigger = QSpinBox()
        self.entry_first_trigger.setRange(0, 10)

        form.addRow("Pattern:", self.entry_pattern)
        form.addRow("有效視窗:", self.entry_window)
        form.addRow("去重模式:", self.entry_dedup)
        form.addRow("首次觸發層:", self.entry_first_trigger)
        self.detail_layout.addWidget(group)

    def _build_staking_section(self) -> None:
        group = QGroupBox("注碼序列")
        layout = QVBoxLayout(group)

        # 模式切換（金額/單位）
        mode_layout = QHBoxLayout()
        mode_label = QLabel("序列模式:")
        mode_label.setStyleSheet("font-weight: bold; color: #f3f4f6;")
        self.mode_amount_radio = QPushButton("💰 金額模式 (推薦)")
        self.mode_unit_radio = QPushButton("🔢 單位模式 (進階)")

        self.mode_amount_radio.setCheckable(True)
        self.mode_unit_radio.setCheckable(True)
        self.mode_amount_radio.setChecked(True)

        for btn in [self.mode_amount_radio, self.mode_unit_radio]:
            btn.setStyleSheet("""
                QPushButton {
                    padding: 8px 16px;
                    border-radius: 6px;
                    background-color: #374151;
                    color: #9ca3af;
                    border: 2px solid #374151;
                }
                QPushButton:checked {
                    background-color: #2563eb;
                    color: #ffffff;
                    border: 2px solid #3b82f6;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #4b5563;
                }
            """)

        self.mode_amount_radio.clicked.connect(lambda: self._switch_mode("amount"))
        self.mode_unit_radio.clicked.connect(lambda: self._switch_mode("unit"))

        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_amount_radio)
        mode_layout.addWidget(self.mode_unit_radio)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # 單位模式的基礎單位設定
        self.base_unit_container = QWidget()
        base_unit_layout = QHBoxLayout(self.base_unit_container)
        base_unit_layout.setContentsMargins(0, 0, 0, 0)
        base_unit_label = QLabel("基礎單位:")
        self.base_unit_spinbox = QSpinBox()
        self.base_unit_spinbox.setRange(100, 100000)
        self.base_unit_spinbox.setValue(100)
        self.base_unit_spinbox.setSuffix(" 元")
        self.base_unit_spinbox.valueChanged.connect(self._update_recipe_preview)
        base_unit_layout.addWidget(base_unit_label)
        base_unit_layout.addWidget(self.base_unit_spinbox)
        base_unit_layout.addStretch()
        self.base_unit_container.setVisible(False)  # 預設隱藏
        layout.addWidget(self.base_unit_container)

        # 序列輸入
        form = QFormLayout()
        self.sequence_edit = QLineEdit()
        self.sequence_edit.setPlaceholderText("例: 1000, 2000, 4000, 8000")
        self.sequence_edit.textChanged.connect(self._update_recipe_preview)

        self.advance_combo = QComboBox()
        for rule in AdvanceRule:
            self.advance_combo.addItem(ADVANCE_LABELS[rule], rule.value)
        self.reset_on_win = QCheckBox("贏後重置")
        self.reset_on_loss = QCheckBox("輸後重置")
        self.max_layers = QSpinBox()
        self.max_layers.setRange(0, 64)
        self.max_layers.setSpecialValueText("不限")
        self.per_hand_cap = QDoubleSpinBox()
        self.per_hand_cap.setRange(0.0, 1e6)
        self.per_hand_cap.setSpecialValueText("不限")
        self.stack_policy = QComboBox()
        for policy in StackPolicy:
            self.stack_policy.addItem(STACK_LABELS[policy], policy.value)

        form.addRow("序列 (逗號分隔):", self.sequence_edit)
        form.addRow("層數前進:", self.advance_combo)
        form.addRow("", self.reset_on_win)
        form.addRow("", self.reset_on_loss)
        form.addRow("最大層數:", self.max_layers)
        form.addRow("單手上限:", self.per_hand_cap)
        form.addRow("同手策略:", self.stack_policy)
        layout.addLayout(form)

        # 即時配方預覽
        preview_group = QGroupBox("📋 即時下注配方預覽")
        preview_group.setStyleSheet("""
            QGroupBox {
                background-color: #1f2937;
                border: 2px solid #3b82f6;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                font-weight: bold;
                color: #60a5fa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        preview_layout = QVBoxLayout(preview_group)

        self.recipe_preview_label = QLabel("請輸入序列以查看配方...")
        self.recipe_preview_label.setWordWrap(True)
        self.recipe_preview_label.setStyleSheet("""
            QLabel {
                color: #d1d5db;
                padding: 12px;
                background-color: #111827;
                border-radius: 6px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
            }
        """)
        preview_layout.addWidget(self.recipe_preview_label)

        layout.addWidget(preview_group)

        self.detail_layout.addWidget(group)

        # 初始化 ChipProfileManager
        try:
            self.chip_profile_manager = ChipProfileManager()
            self.chip_profile = self.chip_profile_manager.load_profile()
        except Exception as e:
            print(f"載入 ChipProfile 失敗: {e}")
            self.chip_profile = None

    def _build_cross_table_section(self) -> None:
        group = QGroupBox("跨桌設定")
        form = QFormLayout(group)
        self.cross_scope = QLineEdit()
        self.cross_mode = QComboBox()
        for mode in CrossTableMode:
            self.cross_mode.addItem(MODE_LABELS[mode], mode.value)
        form.addRow("共享範圍:", self.cross_scope)
        form.addRow("共享模式:", self.cross_mode)
        self.detail_layout.addWidget(group)

    def _build_risk_section(self) -> None:
        group = QGroupBox("風控階層")
        layout = QVBoxLayout(group)
        self.risk_table = RiskTableWidget()
        btn_row = QHBoxLayout()
        add_btn = QPushButton("新增層級")
        remove_btn = QPushButton("移除層級")
        for btn in (add_btn, remove_btn):
            btn.setStyleSheet("QPushButton { padding: 6px 10px; border-radius: 6px; background-color: #374151; color: #f3f4f6; }")
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addWidget(self.risk_table)
        self.detail_layout.addWidget(group)

        add_btn.clicked.connect(lambda: self.risk_table.add_row())
        remove_btn.clicked.connect(self._remove_risk_level)

    # ------------------------------------------------------------------
    def reload_strategies(self) -> None:
        try:
            self.definitions = load_strategy_definitions(self.strategy_dir)
        except Exception as exc:
            QMessageBox.critical(self, "載入失敗", f"讀取策略檔失敗: {exc}")
            self.definitions = {}

        self.strategy_list.clear()
        for key in sorted(self.definitions.keys()):
            item = QListWidgetItem(key)
            self.strategy_list.addItem(item)

        if self.strategy_list.count():
            self.strategy_list.setCurrentRow(0)
        else:
            self._clear_form()

    def _on_strategy_selected(self) -> None:
        items = self.strategy_list.selectedItems()
        if not items:
            self._clear_form()
            return
        key = items[0].text()
        definition = self.definitions.get(key)
        if not definition:
            return
        self.current_key = key
        self.current_data = asdict(definition)
        self._apply_to_form(self.current_data)

    # ------------------------------------------------------------------
    def _apply_to_form(self, data: Dict[str, Any]) -> None:
        entry = data.get("entry", {})
        self.entry_pattern.setText(entry.get("pattern", ""))
        self.entry_window.setValue(float(entry.get("valid_window_sec", 0) or 0))
        idx = self.entry_dedup.findData(entry.get("dedup", DedupMode.OVERLAP.value))
        self.entry_dedup.setCurrentIndex(max(idx, 0))
        self.entry_first_trigger.setValue(int(entry.get("first_trigger_layer", 1) or 1))

        staking = data.get("staking", {})
        sequence = staking.get("sequence", [])
        self.sequence_edit.setText(", ".join(str(x) for x in sequence))
        idx = self.advance_combo.findData(staking.get("advance_on", AdvanceRule.LOSS.value))
        self.advance_combo.setCurrentIndex(max(idx, 0))
        self.reset_on_win.setChecked(bool(staking.get("reset_on_win", True)))
        self.reset_on_loss.setChecked(bool(staking.get("reset_on_loss", False)))
        max_layers = staking.get("max_layers")
        if max_layers is None:
            self.max_layers.setValue(0)
        else:
            self.max_layers.setValue(int(max_layers))
        per_hand_cap = staking.get("per_hand_cap")
        if per_hand_cap is None:
            self.per_hand_cap.setValue(0.0)
        else:
            self.per_hand_cap.setValue(float(per_hand_cap))
        idx = self.stack_policy.findData(staking.get("stack_policy", StackPolicy.NONE.value))
        self.stack_policy.setCurrentIndex(max(idx, 0))

        cross = data.get("cross_table_layer", {})
        self.cross_scope.setText(str(cross.get("scope", "strategy_key")))
        idx = self.cross_mode.findData(cross.get("mode", CrossTableMode.RESET.value))
        self.cross_mode.setCurrentIndex(max(idx, 0))

        risk_levels = data.get("risk", {}).get("levels", [])
        defs = []
        for lvl in risk_levels:
            defs.append(
                RiskLevelConfig(
                    scope=RiskScope(lvl.get("scope", RiskScope.TABLE.value)),
                    take_profit=lvl.get("take_profit"),
                    stop_loss=lvl.get("stop_loss"),
                    max_drawdown_losses=lvl.get("max_drawdown_losses"),
                    action=RiskLevelAction(lvl.get("action", RiskLevelAction.PAUSE.value)),
                    cooldown_sec=lvl.get("cooldown_sec"),
                )
            )
        self.risk_table.load_levels(defs)

    def _collect_form(self) -> Dict[str, Any]:
        sequence = [int(x.strip()) for x in self.sequence_edit.text().split(",") if x.strip()]
        per_hand_cap = float(self.per_hand_cap.value())
        per_hand_cap_value = None if per_hand_cap == 0.0 else per_hand_cap
        max_layers_value = None if self.max_layers.value() == 0 else self.max_layers.value()

        data = {
            "strategy_key": self.current_key or "",
            "entry": {
                "pattern": self.entry_pattern.text().strip(),
                "valid_window_sec": float(self.entry_window.value()),
                "dedup": self.entry_dedup.currentData(),
                "first_trigger_layer": int(self.entry_first_trigger.value()),
            },
            "staking": {
                "sequence": sequence,
                "advance_on": self.advance_combo.currentData(),
                "reset_on_win": self.reset_on_win.isChecked(),
                "reset_on_loss": self.reset_on_loss.isChecked(),
                "max_layers": max_layers_value,
                "per_hand_cap": per_hand_cap_value,
                "stack_policy": self.stack_policy.currentData(),
            },
            "cross_table_layer": {
                "scope": self.cross_scope.text().strip() or "strategy_key",
                "mode": self.cross_mode.currentData(),
            },
            "risk": {"levels": self.risk_table.levels()},
            "metadata": self.current_data.get("metadata", {}),
        }
        return data

    # ------------------------------------------------------------------
    def create_strategy(self) -> None:
        key, ok = QInputDialog.getText(self, "新增策略", "策略鍵 (僅英數與底線):")
        if not ok or not key:
            return
        key = key.strip()
        if key in self.definitions:
            QMessageBox.warning(self, "重複", "策略鍵已存在")
            return

        default = {
            "strategy_key": key,
            "entry": {
                "pattern": "BB then bet P",
                "valid_window_sec": 8,
                "dedup": DedupMode.OVERLAP.value,
                "first_trigger_layer": 1,
            },
            "staking": {
                "sequence": [10, 20, 40],
                "advance_on": AdvanceRule.LOSS.value,
                "reset_on_win": True,
                "reset_on_loss": False,
                "max_layers": None,
                "per_hand_cap": None,
                "stack_policy": StackPolicy.NONE.value,
            },
            "cross_table_layer": asdict(CrossTableLayerConfig()),
            "risk": {"levels": []},
            "metadata": {},
        }
        self.definitions[key] = parse_strategy_definition(default)
        self.strategy_list.addItem(key)
        self.strategy_list.setCurrentRow(self.strategy_list.count() - 1)
        emit_toast(f"策略 {key} 已建立", "info")

    def duplicate_strategy(self) -> None:
        if not self.current_key:
            return
        key, ok = QInputDialog.getText(self, "複製策略", "新策略鍵:")
        if not ok or not key:
            return
        key = key.strip()
        if key in self.definitions:
            QMessageBox.warning(self, "重複", "策略鍵已存在")
            return
        data = self._collect_form()
        data["strategy_key"] = key
        definition = parse_strategy_definition(data)
        self.definitions[key] = definition
        self.strategy_list.addItem(key)
        self.strategy_list.setCurrentRow(self.strategy_list.count() - 1)
        emit_toast(f"已複製策略 {self.current_key} -> {key}", "success")

    def delete_strategy(self) -> None:
        if not self.current_key:
            return
        reply = QMessageBox.question(self, "刪除策略", f"確定要刪除 {self.current_key} 嗎？")
        if reply != QMessageBox.Yes:
            return
        path = self.strategy_dir / f"{self.current_key}.json"
        if path.exists():
            path.unlink()
        row = self.strategy_list.currentRow()
        self.strategy_list.takeItem(row)
        self.definitions.pop(self.current_key, None)
        self.current_key = None
        self._clear_form()
        emit_toast("策略已刪除", "info")

    def open_directory(self) -> None:
        try:
            os.startfile(self.strategy_dir)
        except Exception:
            QMessageBox.information(self, "資料夾位置", str(self.strategy_dir.resolve()))

    # ------------------------------------------------------------------
    def _clear_form(self) -> None:
        self.current_key = None
        self.current_data = {}
        self.entry_pattern.clear()
        self.entry_window.setValue(0.0)
        self.entry_dedup.setCurrentIndex(0)
        self.entry_first_trigger.setValue(1)
        self.sequence_edit.clear()
        self.advance_combo.setCurrentIndex(0)
        self.reset_on_win.setChecked(True)
        self.reset_on_loss.setChecked(False)
        self.max_layers.setValue(0)
        self.per_hand_cap.setValue(0.0)
        self.stack_policy.setCurrentIndex(0)
        self.cross_scope.setText("strategy_key")
        self.cross_mode.setCurrentIndex(0)
        self.risk_table.setRowCount(0)

    def revert_changes(self) -> None:
        if not self.current_key:
            return
        definition = self.definitions.get(self.current_key)
        if definition:
            self.current_data = asdict(definition)
            self._apply_to_form(self.current_data)
            emit_toast("已還原變更", "info")

    # ------------------------------------------------------------------
    def save_current_strategy(self, save_as: bool = False) -> None:
        if not self.current_key and not save_as:
            QMessageBox.information(self, "提示", "請先選擇或新增策略")
            return

        data = self._collect_form()
        if save_as or not self.current_key:
            key, ok = QInputDialog.getText(self, "另存為", "新的策略鍵:")
            if not ok or not key:
                return
            data["strategy_key"] = key.strip()
            self.current_key = data["strategy_key"]

        definition = parse_strategy_definition(data)
        self.definitions[self.current_key] = definition

        path = self.strategy_dir / f"{self.current_key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

        emit_toast(f"策略 {self.current_key} 已儲存", "success")
        if not any(self.strategy_list.item(i).text() == self.current_key for i in range(self.strategy_list.count())):
            self.strategy_list.addItem(self.current_key)
        self.strategy_changed.emit(data)

    def _remove_risk_level(self) -> None:
        if self.risk_table.rowCount() == 0:
            return
        self.risk_table.removeRow(self.risk_table.rowCount() - 1)

    # ------------------------------------------------------------------
    # 新增: 模式切換與配方預覽邏輯
    # ------------------------------------------------------------------

    def _switch_mode(self, mode: str) -> None:
        """切換金額/單位模式"""
        if mode == "amount":
            self.mode_amount_radio.setChecked(True)
            self.mode_unit_radio.setChecked(False)
            self.base_unit_container.setVisible(False)
            self.sequence_edit.setPlaceholderText("例: 1000, 2000, 4000, 8000")
        else:  # unit
            self.mode_amount_radio.setChecked(False)
            self.mode_unit_radio.setChecked(True)
            self.base_unit_container.setVisible(True)
            self.sequence_edit.setPlaceholderText("例: 10, 20, 40, 80")

        self._update_recipe_preview()

    def _update_recipe_preview(self) -> None:
        """更新配方預覽"""
        try:
            # 解析序列
            sequence_text = self.sequence_edit.text().strip()
            if not sequence_text:
                self.recipe_preview_label.setText("請輸入序列以查看配方...")
                return

            sequence = [int(x.strip()) for x in sequence_text.split(",") if x.strip()]
            if not sequence:
                self.recipe_preview_label.setText("請輸入有效的數字序列")
                return

            # 判斷模式並計算實際金額
            is_amount_mode = self.mode_amount_radio.isChecked()
            if is_amount_mode:
                amounts = sequence
            else:
                # 單位模式：乘以基礎單位
                base_unit = self.base_unit_spinbox.value()
                amounts = [x * base_unit for x in sequence]

            # 載入 ChipProfile 並建立 Planner
            if not self.chip_profile:
                self.recipe_preview_label.setText(
                    "⚠️ 未載入籌碼組合\n"
                    "請先在「籌碼設定」頁面設定並校準籌碼"
                )
                return

            calibrated_chips = self.chip_profile.get_calibrated_chips()
            if not calibrated_chips:
                self.recipe_preview_label.setText(
                    "⚠️ 沒有已校準的籌碼\n"
                    "請先在「籌碼設定」頁面校準至少一顆籌碼"
                )
                return

            planner = SmartChipPlanner(calibrated_chips, BettingPolicy())

            # 生成配方預覽
            preview_lines = []
            max_clicks = self.chip_profile.constraints.get("max_clicks_per_hand", 8)

            for i, amount in enumerate(amounts, 1):
                plan = planner.plan_bet(amount, max_clicks=max_clicks)

                if plan.success:
                    if not is_amount_mode:
                        preview_lines.append(
                            f"第 {i} 層 ({sequence[i-1]} 單位 = {amount} 元)"
                        )
                    else:
                        preview_lines.append(f"第 {i} 層 ({amount} 元)")

                    preview_lines.append(f"  → {plan.recipe}")

                    if plan.warnings:
                        for warning in plan.warnings:
                            preview_lines.append(f"  ⚠️  {warning}")
                else:
                    preview_lines.append(f"第 {i} 層 ({amount} 元)")
                    preview_lines.append(f"  ❌ {plan.reason}")

                preview_lines.append("")  # 空行分隔

            # 移除最後的空行
            if preview_lines and preview_lines[-1] == "":
                preview_lines.pop()

            self.recipe_preview_label.setText("\n".join(preview_lines))

        except ValueError:
            self.recipe_preview_label.setText("❌ 序列格式錯誤\n請輸入逗號分隔的數字")
        except Exception as e:
            self.recipe_preview_label.setText(f"❌ 配方預覽錯誤:\n{str(e)}")
