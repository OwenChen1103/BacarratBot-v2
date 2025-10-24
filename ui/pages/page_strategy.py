# ui/pages/page_strategy.py
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QEvent, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
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
    QTabWidget,
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
from ..design_system import FontStyle, Colors, Spacing, StyleSheet  # ✅ 導入設計系統
from ..widgets.pattern_input_widget import PatternInputWidget
from ..widgets.visual_pattern_builder import VisualPatternBuilder
from ..widgets.first_trigger_widget import FirstTriggerWidget
from ..widgets.dedup_mode_widget import DedupModeWidget
from ..widgets.staking_direction_widget import StakingDirectionWidget
from ..widgets.validation_panel_widget import ValidationPanelWidget
from ..widgets.cross_table_mode_widget import CrossTableModeWidget
from ..widgets.risk_control_widget import RiskControlWidget
from ..dialogs.template_selection_dialog import TemplateSelectionDialog
from ..dialogs.risk_template_dialog import RiskTemplateDialog
from ..dialogs.strategy_simulator_dialog import StrategySimulatorDialog
from src.autobet.strategy_validator import StrategyValidator


class WheelEventFilter(QObject):
    """事件過濾器：禁止滾輪改變 SpinBox 和 ComboBox 的值"""

    def eventFilter(self, obj, event):
        # 如果是滾輪事件且對象是 SpinBox 或 ComboBox，則忽略該事件
        if event.type() == QEvent.Wheel:
            if isinstance(obj, (QSpinBox, QDoubleSpinBox, QComboBox)):
                event.ignore()
                return True  # 事件已處理，不再傳遞
        return super().eventFilter(obj, event)


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
        # ✅ 使用設計系統顏色
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Colors.BG_INPUT};
                border: 1px solid {Colors.BORDER_DEFAULT};
                color: {Colors.TEXT_CRITICAL};
                border-radius: {Spacing.RADIUS_MD}px;
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_INPUT};
                color: {Colors.TEXT_NORMAL};
                padding: {Spacing.PADDING_SM}px;
                border: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)

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

        # 安裝滾輪事件過濾器
        self.wheel_filter = WheelEventFilter(self)

        self._build_ui()
        self._install_wheel_filter()
        self.reload_strategies()

    def _install_wheel_filter(self):
        """為所有 SpinBox 和 ComboBox 安裝滾輪事件過濾器"""
        for widget in self.findChildren(QSpinBox):
            widget.installEventFilter(self.wheel_filter)
            widget.setFocusPolicy(Qt.StrongFocus)
        for widget in self.findChildren(QDoubleSpinBox):
            widget.installEventFilter(self.wheel_filter)
            widget.setFocusPolicy(Qt.StrongFocus)
        for widget in self.findChildren(QComboBox):
            widget.installEventFilter(self.wheel_filter)
            widget.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # ✅ 使用設計系統的統一風格
        self.setStyleSheet(f"""
            StrategyPage {{
                background-color: {Colors.BG_TERTIARY};
            }}
            {StyleSheet.group_box()}
            QGroupBox QWidget {{
                background-color: transparent;
            }}
            QGroupBox QFrame {{
                background-color: transparent;
            }}
            QLabel {{
                background-color: transparent;
                color: {Colors.TEXT_IMPORTANT};
            }}
            QRadioButton, QCheckBox {{
                background-color: transparent;
                color: {Colors.TEXT_IMPORTANT};
            }}
            {StyleSheet.input_field()}
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(Spacing.MARGIN_MD)  # ✅ 使用設計系統間距

        # ✅ 優化標題：減小視覺權重（12pt 而非 18pt）
        header = QLabel("策略設定")  # 移除 emoji
        header.setFont(QFont(FontStyle.FAMILY_UI, FontStyle.SIZE_H1, QFont.Bold))  # 12pt
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(f"""
            QLabel {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_CRITICAL};
                border: 1px solid {Colors.BORDER_ELEVATED};
                border-radius: {Spacing.RADIUS_LG}px;
                padding: {Spacing.PADDING_MD}px;
            }}
        """)
        self.main_layout.addWidget(header)

        # ✅ 工具欄按鈕（統一使用幽靈按鈕樣式）
        toolbar = QHBoxLayout()
        self.reload_btn = QPushButton("重新整理")
        self.new_btn = QPushButton("新增策略")
        self.duplicate_btn = QPushButton("複製策略")
        self.delete_btn = QPushButton("刪除策略")
        self.open_dir_btn = QPushButton("開啟資料夾")
        for btn in (self.reload_btn, self.new_btn, self.duplicate_btn, self.delete_btn, self.open_dir_btn):
            btn.setStyleSheet(StyleSheet.button_ghost())  # ✅ 統一樣式
        toolbar.addWidget(self.reload_btn)
        toolbar.addWidget(self.new_btn)
        toolbar.addWidget(self.duplicate_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.open_dir_btn)
        self.main_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        self.main_layout.addWidget(splitter, 1)

        # 左側: 策略列表 + 搜尋/篩選
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(Spacing.MARGIN_SM)  # ✅ 使用設計系統間距

        # ✅ 搜尋框（使用設計系統樣式）
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜尋策略...")  # 移除 emoji
        self.search_box.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Colors.BG_INPUT};
                border: 2px solid {Colors.BORDER_DEFAULT};
                color: {Colors.TEXT_CRITICAL};
                border-radius: {Spacing.RADIUS_MD}px;
                padding: {Spacing.PADDING_SM}px;
                font-size: 10pt;
            }}
            QLineEdit:focus {{
                border-color: {Colors.BORDER_FOCUS};
            }}
        """)
        self.search_box.textChanged.connect(self._filter_strategies)
        list_layout.addWidget(self.search_box)

        # ✅ 標籤篩選與結果計數（使用設計系統）
        filter_row = QHBoxLayout()
        tag_label = QLabel("標籤:")
        tag_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt;")
        self.tag_filter = QComboBox()
        self.tag_filter.addItem("全部", "")
        # ComboBox 樣式已在頁面級 input_field() 定義，無需重複
        self.tag_filter.currentIndexChanged.connect(self._filter_strategies)
        filter_row.addWidget(tag_label)
        filter_row.addWidget(self.tag_filter, 1)

        # ✅ 清除篩選按鈕
        self.clear_filter_btn = QPushButton("清除")
        self.clear_filter_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {Spacing.PADDING_XS}px {Spacing.PADDING_SM}px;
                background-color: {Colors.BG_INPUT};
                color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Spacing.RADIUS_SM}px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_HOVER};
                color: {Colors.TEXT_CRITICAL};
            }}
        """)
        self.clear_filter_btn.clicked.connect(self._clear_filters)
        filter_row.addWidget(self.clear_filter_btn)
        list_layout.addLayout(filter_row)

        # ✅ 結果計數標籤
        self.result_count_label = QLabel("顯示 0 個策略")
        self.result_count_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; padding: {Spacing.PADDING_XS}px;")
        self.result_count_label.setAlignment(Qt.AlignRight)
        list_layout.addWidget(self.result_count_label)

        # ✅ 策略列表（使用設計系統）
        self.strategy_list = QListWidget()
        self.strategy_list.setStyleSheet(StyleSheet.list_widget())
        list_layout.addWidget(self.strategy_list)

        splitter.addWidget(list_container)

        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        # ✅ 使用設計系統的 Tab 樣式
        self.strategy_tabs = QTabWidget()
        self.strategy_tabs.setStyleSheet(StyleSheet.tab_widget())
        detail_layout.addWidget(self.strategy_tabs)

        # ✅ Tab 順序調整：核心功能優先（移除 emoji）

        # Tab 1: 進場條件（最重要 - 放第一）
        self.tab_entry, self.tab_entry_layout = self._create_scrollable_tab()
        self._build_entry_section()
        self.tab_entry_layout.addStretch()
        self.strategy_tabs.addTab(self.tab_entry, "進場條件")

        # Tab 2: 注碼管理
        self.tab_staking, self.tab_staking_layout = self._create_scrollable_tab()
        self._build_staking_section()
        self._build_cross_table_section()
        self.tab_staking_layout.addStretch()
        self.strategy_tabs.addTab(self.tab_staking, "注碼管理")

        # Tab 3: 風險控制
        self.tab_risk, self.tab_risk_layout = self._create_scrollable_tab()
        self._build_risk_section()
        self._build_validation_section()
        self.tab_risk_layout.addStretch()
        self.strategy_tabs.addTab(self.tab_risk, "風險控制")

        # Tab 4: 基本資訊（元資料 - 放最後）
        self.tab_basic, self.tab_basic_layout = self._create_scrollable_tab()
        self._build_metadata_section()
        self.tab_basic_layout.addStretch()
        self.strategy_tabs.addTab(self.tab_basic, "進階設定")

        splitter.addWidget(detail_container)
        splitter.setSizes([220, 680])

        # 建立動作按鈕列
        self._build_action_bar()

    def _create_scrollable_tab(self):
        """建立可滾動的 Tab 容器，返回 (tab_widget, content_layout)"""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        # ✅ 使用設計系統顏色
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Colors.BG_ELEVATED};
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {Colors.BG_ELEVATED};
            }}
        """)
        scroll.viewport().setStyleSheet(f"background-color: {Colors.BG_ELEVATED};")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet(f"background-color: {Colors.BG_ELEVATED};")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(Spacing.MARGIN_MD)  # ✅ 使用設計系統間距
        scroll_layout.setContentsMargins(
            Spacing.MARGIN_XS,
            Spacing.MARGIN_XS,
            Spacing.MARGIN_XS,
            Spacing.MARGIN_XS
        )

        scroll.setWidget(scroll_widget)
        tab_layout.addWidget(scroll)

        return tab, scroll_layout

    def _build_action_bar(self):
        """建立動作按鈕列"""
        action_bar = QHBoxLayout()

        # ✅ 模擬器按鈕（強調色）
        self.simulate_btn = QPushButton("測試模擬")  # 移除 emoji
        self.simulate_btn.setStyleSheet(StyleSheet.button_accent())

        # ✅ 主要動作按鈕（主色調）
        self.save_btn = QPushButton("儲存變更")
        self.save_as_btn = QPushButton("另存為...")
        self.save_btn.setStyleSheet(StyleSheet.button_primary())
        self.save_as_btn.setStyleSheet(StyleSheet.button_primary())

        # ✅ 次要按鈕（幽靈樣式）
        self.revert_btn = QPushButton("還原")
        self.revert_btn.setStyleSheet(StyleSheet.button_ghost())

        action_bar.addWidget(self.simulate_btn)
        action_bar.addStretch()
        action_bar.addWidget(self.save_btn)
        action_bar.addWidget(self.save_as_btn)
        action_bar.addWidget(self.revert_btn)
        self.main_layout.addLayout(action_bar)

        self.reload_btn.clicked.connect(self.reload_strategies)
        self.new_btn.clicked.connect(self.create_strategy)
        self.duplicate_btn.clicked.connect(self.duplicate_strategy)
        self.delete_btn.clicked.connect(self.delete_strategy)
        self.open_dir_btn.clicked.connect(self.open_directory)
        self.simulate_btn.clicked.connect(self.run_simulator)
        self.save_btn.clicked.connect(self.save_current_strategy)
        self.save_as_btn.clicked.connect(lambda: self.save_current_strategy(save_as=True))
        self.revert_btn.clicked.connect(self.revert_changes)
        self.strategy_list.itemSelectionChanged.connect(self._on_strategy_selected)

    # ------------------------------------------------------------------
    def _build_metadata_section(self) -> None:
        """建立策略元資料區塊"""
        group = QGroupBox("📋 策略資訊")
        layout = QVBoxLayout(group)

        # ✅ 描述（樣式已在頁面級定義，無需重複）
        desc_layout = QFormLayout()
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("簡短描述這個策略的用途...")
        desc_layout.addRow("描述:", self.description_edit)
        layout.addLayout(desc_layout)

        # ✅ 標籤
        tags_layout = QHBoxLayout()
        tags_label = QLabel("標籤:")
        tags_label.setStyleSheet(f"color: {Colors.TEXT_CRITICAL}; font-weight: bold;")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("例如: 馬丁, 保守, 雙跳 (用逗號分隔)")
        tags_layout.addWidget(tags_label)
        tags_layout.addWidget(self.tags_edit, 1)
        layout.addLayout(tags_layout)

        # ✅ 預設標籤快捷按鈕（統一樣式）
        quick_tags_layout = QHBoxLayout()
        quick_tags_label = QLabel("快速標籤:")
        quick_tags_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt;")
        quick_tags_layout.addWidget(quick_tags_label)

        for tag in ["馬丁", "反馬丁", "固定注碼", "保守", "激進", "雙跳", "追龍"]:
            btn = QPushButton(tag)
            btn.setStyleSheet(f"""
                QPushButton {{
                    padding: {Spacing.PADDING_XS}px {Spacing.PADDING_MD - 2}px;
                    background-color: {Colors.BG_INPUT};
                    color: {Colors.INFO_500};
                    border-radius: {Spacing.RADIUS_SM}px;
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    font-size: 9pt;
                }}
                QPushButton:hover {{
                    background-color: {Colors.BG_HOVER};
                }}
            """)
            btn.clicked.connect(lambda checked, t=tag: self._add_quick_tag(t))
            quick_tags_layout.addWidget(btn)

        quick_tags_layout.addStretch()
        layout.addLayout(quick_tags_layout)

        self.tab_basic_layout.addWidget(group)

    def _add_quick_tag(self, tag: str):
        """快速添加標籤"""
        current = self.tags_edit.text().strip()
        if current:
            tags = [t.strip() for t in current.split(",")]
            if tag not in tags:
                tags.append(tag)
                self.tags_edit.setText(", ".join(tags))
        else:
            self.tags_edit.setText(tag)

    # ------------------------------------------------------------------
    def _build_entry_section(self) -> None:
        group = QGroupBox("進場設定")
        layout = QVBoxLayout(group)

        # ✅ 使用單選按鈕替換嵌套 Tab（減少導航層級）
        mode_selector_layout = QHBoxLayout()
        mode_label = QLabel("編輯模式:")
        mode_label.setStyleSheet(f"color: {Colors.TEXT_CRITICAL}; font-weight: bold;")

        self.pattern_visual_btn = QPushButton("視覺化建構")
        self.pattern_text_btn = QPushButton("文字輸入")

        self.pattern_visual_btn.setCheckable(True)
        self.pattern_text_btn.setCheckable(True)
        self.pattern_visual_btn.setChecked(True)  # 預設視覺化模式

        # 使用與模式切換一致的樣式
        for btn in [self.pattern_visual_btn, self.pattern_text_btn]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    padding: {Spacing.PADDING_SM}px {Spacing.PADDING_LG}px;
                    border-radius: {Spacing.RADIUS_MD}px;
                    background-color: {Colors.BG_INPUT};
                    color: {Colors.TEXT_MUTED};
                    border: 2px solid {Colors.BORDER_DEFAULT};
                }}
                QPushButton:checked {{
                    background-color: {Colors.PRIMARY_500};
                    color: white;
                    border: 2px solid {Colors.PRIMARY_600};
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {Colors.BG_HOVER};
                }}
            """)

        self.pattern_visual_btn.clicked.connect(lambda: self._switch_pattern_mode("visual"))
        self.pattern_text_btn.clicked.connect(lambda: self._switch_pattern_mode("text"))

        mode_selector_layout.addWidget(mode_label)
        mode_selector_layout.addWidget(self.pattern_visual_btn)
        mode_selector_layout.addWidget(self.pattern_text_btn)
        mode_selector_layout.addStretch()
        layout.addLayout(mode_selector_layout)

        # ✅ 使用 QStackedWidget 切換不同的編輯器（而非嵌套 Tab）
        from PySide6.QtWidgets import QStackedWidget
        self.pattern_stack = QStackedWidget()

        # 視覺化建構器
        self.visual_pattern_builder = VisualPatternBuilder()
        self.visual_pattern_builder.pattern_changed.connect(self._on_visual_pattern_changed)
        self.pattern_stack.addWidget(self.visual_pattern_builder)

        # 文字輸入
        text_input_widget = QWidget()
        text_input_layout = QVBoxLayout(text_input_widget)
        text_input_layout.setContentsMargins(0, 0, 0, 0)
        self.entry_pattern_widget = PatternInputWidget()
        self.entry_pattern_widget.pattern_changed.connect(self._on_text_pattern_changed)
        text_input_layout.addWidget(self.entry_pattern_widget)
        text_input_layout.addStretch()
        self.pattern_stack.addWidget(text_input_widget)

        layout.addWidget(self.pattern_stack)

        # 有效視窗
        form = QFormLayout()
        self.entry_window = QDoubleSpinBox()
        self.entry_window.setRange(0.0, 3600.0)
        self.entry_window.setSuffix(" 秒")
        form.addRow("有效視窗:", self.entry_window)
        layout.addLayout(form)

        # 使用新的 Dedup Mode Widget 取代 ComboBox
        self.entry_dedup_widget = DedupModeWidget()
        layout.addWidget(self.entry_dedup_widget)

        # 使用新的 First Trigger Widget 取代 SpinBox
        self.entry_first_trigger_widget = FirstTriggerWidget()
        layout.addWidget(self.entry_first_trigger_widget)

        self.tab_entry_layout.addWidget(group)

    def _switch_pattern_mode(self, mode: str) -> None:
        """切換進場模式編輯器"""
        if mode == "visual":
            self.pattern_visual_btn.setChecked(True)
            self.pattern_text_btn.setChecked(False)
            self.pattern_stack.setCurrentIndex(0)  # 顯示視覺化建構器
        else:  # text
            self.pattern_visual_btn.setChecked(False)
            self.pattern_text_btn.setChecked(True)
            self.pattern_stack.setCurrentIndex(1)  # 顯示文字輸入

    def _on_visual_pattern_changed(self, pattern: str):
        """視覺化建構器的 pattern 改變"""
        # 防止遞迴:如果已經在同步中,不要再同步
        if hasattr(self, '_syncing_pattern') and self._syncing_pattern:
            return

        self._syncing_pattern = True
        try:
            # 同步到文字輸入
            self.entry_pattern_widget.set_pattern(pattern)
        finally:
            self._syncing_pattern = False

    def _on_text_pattern_changed(self, pattern: str):
        """文字輸入的 pattern 改變"""
        # 防止遞迴:如果已經在同步中,不要再同步
        if hasattr(self, '_syncing_pattern') and self._syncing_pattern:
            return

        self._syncing_pattern = True
        try:
            # 同步到視覺化建構器
            self.visual_pattern_builder.set_pattern(pattern)
        finally:
            self._syncing_pattern = False

    def _build_staking_section(self) -> None:
        group = QGroupBox("注碼序列")
        layout = QVBoxLayout(group)

        # ✅ 模式切換（金額/單位）
        mode_layout = QHBoxLayout()
        mode_label = QLabel("序列模式:")
        mode_label.setStyleSheet(f"font-weight: bold; color: {Colors.TEXT_CRITICAL};")
        self.mode_amount_radio = QPushButton("金額模式 (推薦)")  # 移除 emoji
        self.mode_unit_radio = QPushButton("單位模式 (進階)")

        self.mode_amount_radio.setCheckable(True)
        self.mode_unit_radio.setCheckable(True)
        self.mode_amount_radio.setChecked(True)

        for btn in [self.mode_amount_radio, self.mode_unit_radio]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    padding: {Spacing.PADDING_SM}px {Spacing.PADDING_LG}px;
                    border-radius: {Spacing.RADIUS_MD}px;
                    background-color: {Colors.BG_INPUT};
                    color: {Colors.TEXT_MUTED};
                    border: 2px solid {Colors.BORDER_DEFAULT};
                }}
                QPushButton:checked {{
                    background-color: {Colors.PRIMARY_500};
                    color: white;
                    border: 2px solid {Colors.PRIMARY_600};
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {Colors.BG_HOVER};
                }}
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

        # 使用新的 StakingDirectionWidget
        self.staking_direction_widget = StakingDirectionWidget()
        self.staking_direction_widget.sequence_changed.connect(self._update_recipe_preview_from_widget)
        layout.addWidget(self.staking_direction_widget)

        # 其他配置
        form = QFormLayout()
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

        form.addRow("層數前進:", self.advance_combo)
        form.addRow("", self.reset_on_win)
        form.addRow("", self.reset_on_loss)
        form.addRow("最大層數:", self.max_layers)
        form.addRow("單手上限:", self.per_hand_cap)
        form.addRow("同手策略:", self.stack_policy)
        layout.addLayout(form)

        # ✅ 即時配方預覽（使用設計系統顏色）
        preview_group = QGroupBox("即時下注配方預覽")  # 移除 emoji
        preview_group.setStyleSheet(f"""
            QGroupBox {{
                background-color: {Colors.BG_INPUT};
                border: 2px solid {Colors.INFO_500};
                border-radius: {Spacing.RADIUS_LG}px;
                margin-top: {Spacing.PADDING_MD}px;
                padding-top: {Spacing.PADDING_MD}px;
                font-weight: bold;
                color: {Colors.INFO_500};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {Spacing.PADDING_MD - 2}px;
                padding: 0 {Spacing.PADDING_SM - 3}px;
            }}
        """)
        preview_layout = QVBoxLayout(preview_group)

        self.recipe_preview_label = QLabel("輸入序列以預覽配方")
        self.recipe_preview_label.setWordWrap(True)
        self.recipe_preview_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_NORMAL};
                padding: {Spacing.PADDING_MD}px;
                background-color: {Colors.BG_INPUT};
                border-radius: {Spacing.RADIUS_MD}px;
                font-family: '{FontStyle.FAMILY_MONO}', 'Courier New', monospace;
                font-size: 10pt;
            }}
        """)
        preview_layout.addWidget(self.recipe_preview_label)

        layout.addWidget(preview_group)

        self.tab_staking_layout.addWidget(group)

        # 初始化 ChipProfileManager
        try:
            self.chip_profile_manager = ChipProfileManager()
            self.chip_profile = self.chip_profile_manager.load_profile()
        except Exception as e:
            print(f"載入 ChipProfile 失敗: {e}")
            self.chip_profile = None

    def _build_cross_table_section(self) -> None:
        group = QGroupBox("跨桌設定")
        layout = QVBoxLayout(group)

        # ✅ 共享範圍
        scope_layout = QFormLayout()
        self.cross_scope = QLineEdit()
        self.cross_scope.setPlaceholderText("例如: strategy_key (預設)")
        scope_hint = QLabel("💡 共享範圍決定哪些策略實例共用層數。預設 'strategy_key' 表示同一策略的所有實例共享。")
        scope_hint.setWordWrap(True)
        scope_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt;")
        scope_layout.addRow("共享範圍:", self.cross_scope)
        scope_layout.addRow(scope_hint)
        layout.addLayout(scope_layout)

        # 使用新的跨桌模式 Widget
        self.cross_mode_widget = CrossTableModeWidget()
        layout.addWidget(self.cross_mode_widget)

        self.tab_staking_layout.addWidget(group)

    def _build_risk_section(self) -> None:
        group = QGroupBox("風控階層")
        layout = QVBoxLayout(group)

        # ✅ 範本按鈕（使用主要按鈕樣式）
        template_btn = QPushButton("使用風控範本")  # 移除 emoji
        template_btn.setStyleSheet(StyleSheet.button_primary())
        template_btn.clicked.connect(self._apply_risk_template)
        layout.addWidget(template_btn)

        # 使用新的 RiskControlWidget (支援簡易/進階雙模式)
        self.risk_control = RiskControlWidget()
        self.risk_control.risk_changed.connect(self._run_validation)
        layout.addWidget(self.risk_control)

        self.tab_risk_layout.addWidget(group)

    def _add_risk_level(self) -> None:
        """新增風控層級並觸發驗證"""
        self.risk_table.add_row()
        self._run_validation()

    def _build_validation_section(self) -> None:
        """建立驗證面板"""
        self.validation_panel = ValidationPanelWidget()
        self.tab_risk_layout.addWidget(self.validation_panel)

        # 連接所有輸入改變時自動驗證
        self._connect_validation_triggers()

    # ------------------------------------------------------------------
    def reload_strategies(self) -> None:
        try:
            self.definitions = load_strategy_definitions(self.strategy_dir)
        except Exception as exc:
            QMessageBox.critical(self, "載入失敗", f"讀取策略檔失敗: {exc}")
            self.definitions = {}

        # 更新標籤篩選選項
        self._update_tag_filter()

        # 顯示策略列表
        self._filter_strategies()

        if self.strategy_list.count():
            self.strategy_list.setCurrentRow(0)
        else:
            self._clear_form()

    def _update_tag_filter(self):
        """更新標籤篩選選項"""
        # 收集所有標籤
        all_tags = set()
        for definition in self.definitions.values():
            data = asdict(definition)
            metadata = data.get("metadata", {})
            tags = metadata.get("tags", [])
            all_tags.update(tags)

        # 更新 ComboBox
        current_filter = self.tag_filter.currentData()
        self.tag_filter.clear()
        self.tag_filter.addItem("全部", "")

        for tag in sorted(all_tags):
            self.tag_filter.addItem(f"# {tag}", tag)

        # 恢復選擇
        idx = self.tag_filter.findData(current_filter)
        if idx >= 0:
            self.tag_filter.setCurrentIndex(idx)

    def _filter_strategies(self):
        """根據搜尋和標籤篩選策略"""
        search_text = self.search_box.text().lower()
        tag_filter = self.tag_filter.currentData()

        self.strategy_list.clear()

        for key in sorted(self.definitions.keys()):
            definition = self.definitions[key]
            data = asdict(definition)
            metadata = data.get("metadata", {})

            # 搜尋過濾
            if search_text:
                description = metadata.get("description", "").lower()
                tags = " ".join(metadata.get("tags", [])).lower()
                if search_text not in key.lower() and search_text not in description and search_text not in tags:
                    continue

            # 標籤過濾
            if tag_filter:
                strategy_tags = metadata.get("tags", [])
                if tag_filter not in strategy_tags:
                    continue

            # 建立顯示項目
            display_text = key
            if metadata.get("description"):
                display_text += f"\n  {metadata['description']}"
            if metadata.get("tags"):
                tags_str = ", ".join(metadata["tags"])
                display_text += f"\n  # {tags_str}"

            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, key)  # 儲存實際的 key
            self.strategy_list.addItem(item)

        # ✅ 更新結果計數
        displayed_count = self.strategy_list.count()
        total_count = len(self.definitions)
        if displayed_count == total_count:
            self.result_count_label.setText(f"顯示 {total_count} 個策略")
        else:
            self.result_count_label.setText(f"顯示 {displayed_count}/{total_count} 個策略")

    def _clear_filters(self) -> None:
        """清除所有篩選條件"""
        self.search_box.clear()
        self.tag_filter.setCurrentIndex(0)  # 選擇「全部」
        # _filter_strategies 會自動被 textChanged 和 currentIndexChanged 觸發

    def _on_strategy_selected(self) -> None:
        items = self.strategy_list.selectedItems()
        if not items:
            self._clear_form()
            self.validation_panel.show_placeholder()
            return
        # 從 UserRole 取得實際的 key
        key = items[0].data(Qt.UserRole)
        definition = self.definitions.get(key)
        if not definition:
            return
        self.current_key = key
        self.current_data = asdict(definition)
        self._apply_to_form(self.current_data)
        # 載入策略後立即驗證
        self._run_validation()

    # ------------------------------------------------------------------
    def _apply_to_form(self, data: Dict[str, Any]) -> None:
        # Metadata
        metadata = data.get("metadata", {})
        self.description_edit.setText(metadata.get("description", ""))
        tags = metadata.get("tags", [])
        self.tags_edit.setText(", ".join(tags) if tags else "")

        # Entry
        entry = data.get("entry", {})
        self.entry_pattern_widget.set_pattern(entry.get("pattern", ""))
        self.entry_window.setValue(float(entry.get("valid_window_sec", 0) or 0))
        self.entry_dedup_widget.set_value(entry.get("dedup", "overlap_dedup"))
        self.entry_first_trigger_widget.set_value(int(entry.get("first_trigger_layer", 1) or 1))

        staking = data.get("staking", {})
        sequence = staking.get("sequence", [])
        self.staking_direction_widget.set_sequence(sequence)
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
        self.cross_mode_widget.set_value(cross.get("mode", CrossTableMode.RESET.value))

        risk_levels = data.get("risk", {}).get("levels", [])
        self.risk_control.load_levels(risk_levels)

    def _collect_form(self) -> Dict[str, Any]:
        sequence = self.staking_direction_widget.get_sequence()
        per_hand_cap = float(self.per_hand_cap.value())
        per_hand_cap_value = None if per_hand_cap == 0.0 else per_hand_cap
        max_layers_value = None if self.max_layers.value() == 0 else self.max_layers.value()

        data = {
            "strategy_key": self.current_key or "",
            "entry": {
                "pattern": self.entry_pattern_widget.get_pattern(),
                "valid_window_sec": float(self.entry_window.value()),
                "dedup": self.entry_dedup_widget.get_value(),
                "first_trigger_layer": self.entry_first_trigger_widget.get_value(),
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
                "mode": self.cross_mode_widget.get_value(),
            },
            "risk": {"levels": self.risk_control.get_risk_levels()},
            "metadata": {
                "description": self.description_edit.text().strip(),
                "tags": [t.strip() for t in self.tags_edit.text().split(",") if t.strip()],
            },
        }
        return data

    # ------------------------------------------------------------------
    def create_strategy(self) -> None:
        """新增策略 - 先顯示範本選擇對話框"""
        # 顯示範本選擇對話框
        dialog = TemplateSelectionDialog(self)
        if dialog.exec() == TemplateSelectionDialog.Accepted:
            template = dialog.get_selected()
            if template:
                # 使用範本建立策略
                self._create_from_template(template)
                return

        # 使用者取消或沒有選擇範本,詢問是否手動建立
        reply = QMessageBox.question(
            self,
            "手動建立策略",
            "要手動建立空白策略嗎?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._create_blank_strategy()

    def _create_from_template(self, template) -> None:
        """從範本建立策略"""
        # 詢問策略鍵
        suggested_key = template.key
        key, ok = QInputDialog.getText(
            self,
            "新增策略",
            f"策略鍵 (僅英數與底線):\n範本建議: {suggested_key}",
            text=suggested_key
        )
        if not ok or not key:
            return
        key = key.strip()
        if key in self.definitions:
            QMessageBox.warning(self, "重複", "策略鍵已存在")
            return

        # 使用範本定義
        definition = template.definition
        definition.strategy_key = key  # 更新策略鍵

        # 轉換為字典格式儲存
        data = asdict(definition)
        self.definitions[key] = parse_strategy_definition(data)
        self.strategy_list.addItem(key)
        self.strategy_list.setCurrentRow(self.strategy_list.count() - 1)
        emit_toast(f"策略 '{key}' 已從範本 '{template.name}' 建立", "success")

    def _create_blank_strategy(self) -> None:
        """手動建立空白策略"""
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

    def run_simulator(self) -> None:
        """執行策略模擬器"""
        if not self.current_key:
            QMessageBox.warning(self, "提示", "請先選擇一個策略")
            return

        try:
            # 收集當前表單資料
            data = self._collect_form()
            definition = parse_strategy_definition(data)

            # 打開模擬器對話框
            dialog = StrategySimulatorDialog(definition, self)
            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"無法啟動模擬器: {str(e)}")

    # ------------------------------------------------------------------
    def _clear_form(self) -> None:
        self.current_key = None
        self.current_data = {}
        self.entry_pattern_widget.set_pattern("")
        self.entry_window.setValue(0.0)
        self.entry_dedup_widget.set_value("overlap_dedup")
        self.entry_first_trigger_widget.set_value(1)
        self.staking_direction_widget.set_sequence([100, 200, 400])
        self.advance_combo.setCurrentIndex(0)
        self.reset_on_win.setChecked(True)
        self.reset_on_loss.setChecked(False)
        self.max_layers.setValue(0)
        self.per_hand_cap.setValue(0.0)
        self.stack_policy.setCurrentIndex(0)
        self.cross_scope.setText("strategy_key")
        self.cross_mode_widget.set_value(CrossTableMode.RESET.value)
        self.risk_control.load_levels([])

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

    def _apply_risk_template(self) -> None:
        """套用風控範本"""
        dialog = RiskTemplateDialog(self)
        if dialog.exec() == RiskTemplateDialog.Accepted:
            template = dialog.get_selected()
            if template:
                # 載入範本層級到風控 widget
                from dataclasses import asdict
                levels = [asdict(level) for level in template.levels]
                self.risk_control.load_levels(levels)
                emit_toast(f"已套用風控範本: {template.name}", "success")
                self._run_validation()

    def _connect_validation_triggers(self) -> None:
        """連接所有會改變配置的控件以觸發驗證"""
        # Entry 相關
        self.entry_pattern_widget.pattern_changed.connect(self._run_validation)
        self.entry_window.valueChanged.connect(self._run_validation)
        self.entry_dedup_widget.value_changed.connect(self._run_validation)
        self.entry_first_trigger_widget.value_changed.connect(self._run_validation)

        # Staking 相關
        self.staking_direction_widget.sequence_changed.connect(self._run_validation)
        self.advance_combo.currentIndexChanged.connect(self._run_validation)
        self.reset_on_win.toggled.connect(self._run_validation)
        self.reset_on_loss.toggled.connect(self._run_validation)
        self.max_layers.valueChanged.connect(self._run_validation)
        self.per_hand_cap.valueChanged.connect(self._run_validation)
        self.stack_policy.currentIndexChanged.connect(self._run_validation)

        # Cross-table 相關
        self.cross_scope.textChanged.connect(self._run_validation)
        self.cross_mode_widget.value_changed.connect(self._run_validation)

        # Risk 相關 - 表格內容改變時也觸發
        # (Risk table 的改變需要手動調用 _run_validation)

    def _run_validation(self) -> None:
        """執行策略驗證"""
        if not self.current_key:
            self.validation_panel.show_placeholder()
            return

        try:
            # 收集當前表單資料
            data = self._collect_form()

            # 解析為 StrategyDefinition
            definition = parse_strategy_definition(data)

            # 執行驗證
            result = StrategyValidator.validate(definition)

            # 顯示結果
            self.validation_panel.display_result(result)

        except Exception as e:
            # 顯示錯誤
            self.validation_panel.show_placeholder()
            print(f"驗證失敗: {e}")

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
                self.recipe_preview_label.setText("輸入序列以預覽配方")
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
                    "未載入籌碼組合\n"
                    "請先在「籌碼設定」頁面設定並校準籌碼"
                )
                return

            calibrated_chips = self.chip_profile.get_calibrated_chips()
            if not calibrated_chips:
                self.recipe_preview_label.setText(
                    "沒有已校準的籌碼\n"
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
                            preview_lines.append(f"  !  {warning}")
                else:
                    preview_lines.append(f"第 {i} 層 ({amount} 元)")
                    preview_lines.append(f"  × {plan.reason}")

                preview_lines.append("")  # 空行分隔

            # 移除最後的空行
            if preview_lines and preview_lines[-1] == "":
                preview_lines.pop()

            self.recipe_preview_label.setText("\n".join(preview_lines))

        except ValueError:
            self.recipe_preview_label.setText("錯誤: 序列格式不正確\n請輸入逗號分隔的數字")
        except Exception as e:
            self.recipe_preview_label.setText(f"錯誤: 配方預覽失敗\n{str(e)}")

    def _update_recipe_preview_from_widget(self, sequence: list):
        """從 StakingDirectionWidget 更新配方預覽"""
        try:
            # 取得絕對值序列用於顯示
            amounts = [abs(x) for x in sequence]
            if not amounts:
                self.recipe_preview_label.setText("請設定注碼序列...")
                return

            # 載入 ChipProfile 並建立 Planner
            if not self.chip_profile:
                self.recipe_preview_label.setText(
                    "未載入籌碼組合\n"
                    "請先在「籌碼設定」頁面設定並校準籌碼"
                )
                return

            calibrated_chips = self.chip_profile.get_calibrated_chips()
            if not calibrated_chips:
                self.recipe_preview_label.setText(
                    "沒有已校準的籌碼\n"
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
                    preview_lines.append(f"第 {i} 層 ({amount} 元)")
                    preview_lines.append(f"  → {plan.recipe}")

                    if plan.warnings:
                        for warning in plan.warnings:
                            preview_lines.append(f"  !  {warning}")
                else:
                    preview_lines.append(f"第 {i} 層 ({amount} 元)")
                    preview_lines.append(f"  × {plan.reason}")

                preview_lines.append("")  # 空行分隔

            # 移除最後的空行
            if preview_lines and preview_lines[-1] == "":
                preview_lines.pop()

            self.recipe_preview_label.setText("\n".join(preview_lines))

        except Exception as e:
            self.recipe_preview_label.setText(f"錯誤: 配方預覽失敗\n{str(e)}")
