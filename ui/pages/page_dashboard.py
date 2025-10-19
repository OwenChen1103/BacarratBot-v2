# ui/pages/page_dashboard.py
import os
import json
import time
import re
from typing import Any, Dict, Optional, List, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTextEdit,
    QProgressBar, QComboBox, QCheckBox, QSpinBox,
    QMessageBox, QInputDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QScrollArea, QSizePolicy, QTabWidget
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor, QColor, QPalette

from ..workers.engine_worker import EngineWorker
from ..components.next_bet_card import NextBetCard

TABLE_ID_DISPLAY_MAP = {
    "WG7": "BG_131",
    "WG8": "BG_132",
    "WG9": "BG_133",
    "WG10": "BG_135",
    "WG11": "BG_136",
    "WG12": "BG_137",
    "WG13": "BG_138",
}

TABLE_TAG_RE = re.compile(r"\[table=([^\]]+)\]")
DISPLAY_TAG_RE = re.compile(r"\[display=([^\]]+)\]")

class NoWheelComboBox(QComboBox):
    """禁用滾輪的 ComboBox"""
    def wheelEvent(self, event):
        # 完全忽略滾輪事件，除非按住 Ctrl 鍵
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.keyboardModifiers() & Qt.ControlModifier:
            super().wheelEvent(event)
        else:
            event.ignore()

class StatusCard(QFrame):
    """狀態卡片"""
    def __init__(self, title: str, icon: str = "📊"):
        super().__init__()
        self.title = title
        self.icon = icon
        self.is_detection_card = (title == "檢測狀態")
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        self.setFixedHeight(180)

        # 標題
        header_layout = QHBoxLayout()
        self.icon_label = QLabel(self.icon)
        self.icon_label.setFont(QFont("Segoe UI Emoji", 11))

        self.title_label = QLabel(self.title)
        self.title_label.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))

        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        # 內容區域（用一個 Frame 包裝，這樣可以單獨設置邊框）
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: 1px solid #4b5563;
                border-radius: 6px;
                padding: 8px;
            }
        """)

        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.content_label = QLabel("待機中...")
        # 檢測卡片使用左對齊以便顯示詳細信息，其他卡片居中
        if self.is_detection_card:
            self.content_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        else:
            self.content_label.setAlignment(Qt.AlignCenter)

        # 使用支援 emoji 的字體，檢測卡片使用較小字體
        if self.is_detection_card:
            content_font = QFont("Microsoft YaHei UI", 8, QFont.Normal)
        else:
            content_font = QFont("Microsoft YaHei UI", 10, QFont.Bold)
        content_font.setStyleStrategy(QFont.PreferAntialias)
        self.content_label.setFont(content_font)

        # 允許換行顯示
        self.content_label.setWordWrap(True)

        content_layout.addWidget(self.content_label)

        layout.addLayout(header_layout)
        layout.addWidget(self.content_frame)

    def update_content(self, content: str, color: str = "#ffffff", show_border: bool = False):
        """更新內容"""
        self.content_label.setText(content)
        # 確保內層標籤沒有邊框，只有文字顏色
        self.content_label.setStyleSheet(f"""
            color: {color};
            border: none;
            background: transparent;
        """)

        # 檢測狀態卡片的綠色邊框效果（只應用到內容區域）
        if self.is_detection_card and show_border:
            self.content_frame.setStyleSheet("""
                QFrame {
                    background-color: transparent;
                    border: 2px solid #10b981;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)
        else:
            self.content_frame.setStyleSheet("""
                QFrame {
                    background-color: transparent;
                    border: 1px solid #4b5563;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)

class ResultCard(QFrame):
    """顯示單桌最新開獎結果的卡片"""

    table_selected = Signal(str)

    def __init__(self):
        super().__init__()
        # 固定桌號列表 BG_125 - BG_138
        self._all_tables: List[str] = [f"BG_{i}" for i in range(125, 139)]
        self._tables_with_data: set = set()  # 已收到結果的桌號
        self._current_table = ""
        self._updating_combo = False
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        self.setFixedHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.setContentsMargins(6, 6, 6, 6)

        header_layout = QHBoxLayout()
        icon = QLabel("🎲")
        icon.setFont(QFont("Segoe UI Emoji", 10))
        header_layout.addWidget(icon)

        title = QLabel("開獎結果")
        title.setFont(QFont("Microsoft YaHei UI", 8, QFont.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        selector_layout = QHBoxLayout()
        selector_label = QLabel("桌號：")
        selector_label.setStyleSheet("color: #e5e7eb;")
        selector_layout.addWidget(selector_label)

        self.combo = NoWheelComboBox()
        self.combo.setEnabled(True)  # 改為啟用，因為我們有固定列表
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        selector_layout.addWidget(self.combo, 1)
        layout.addLayout(selector_layout)

        # 初始化固定桌號列表
        self._init_fixed_tables()

        self.status_label = QLabel("狀態：--")
        self.status_label.setStyleSheet("color: #f9fafb; font-size: 9pt; font-weight: bold; background: transparent;")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setMinimumHeight(30)
        self.status_label.setMinimumWidth(80)

        self.result_label = QLabel("尚未收到開獎結果")
        self.result_label.setWordWrap(True)
        self.result_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.result_label.setStyleSheet(
            "color: #f9fafb; font-size: 9pt; font-weight: bold; background: transparent;"
        )
        self.result_label.setMinimumHeight(30)
        status_result_row = QHBoxLayout()
        status_result_row.setSpacing(12)
        status_result_row.addWidget(self.status_label)
        status_result_row.addWidget(self.result_label, 1)
        layout.addLayout(status_result_row)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.detail_label.setStyleSheet("color: #d1d5db; font-size: 8pt;")
        self.detail_label.setMinimumHeight(40)
        layout.addWidget(self.detail_label)
        layout.addSpacing(4)

    def _init_fixed_tables(self):
        """初始化固定桌號列表"""
        self._updating_combo = True
        self.combo.clear()
        for table_id in self._all_tables:
            # 直接顯示桌號，不加後綴
            self.combo.addItem(table_id, table_id)
        self._updating_combo = False

    def set_stream_status(self, status: Optional[str]):
        mapping = {
            "connected": ("狀態：已連線", "#10b981"),
            "connecting": ("狀態：連線中…", "#f59e0b"),
            "error": ("狀態：連線錯誤", "#ef4444"),
            "disconnected": ("狀態：已斷線，等待重試", "#f59e0b"),
            "stopped": ("狀態：已停止", "#9ca3af"),
        }
        text, color = mapping.get(status or "", ("狀態：--", "#9ca3af"))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def set_tables(self, tables: List[str]):
        """更新已收到結果的桌號列表"""
        tables = list(tables)

        # 檢查是否有新桌號
        new_tables = set(tables) - self._tables_with_data
        if not new_tables:
            # 沒有新桌號，不需要更新
            return

        # 更新已收到數據的桌號集合
        self._tables_with_data.update(tables)

        # 如果選單還沒有初始化項目，或者當前沒有選中的桌號，才需要更新選中項
        if self.combo.count() == 0:
            # 第一次初始化，選擇第一個有數據的桌號
            if self._tables_with_data:
                first_table = min(self._tables_with_data, key=lambda x: int(x.split('_')[1]))
                index = self._all_tables.index(first_table)
                self._updating_combo = True
                self.combo.setCurrentIndex(index)
                self._current_table = first_table
                self._updating_combo = False
                self._emit_selection()

    def set_result(self, info: Optional[Dict[str, Any]]):
        if not info:
            self.result_label.setText("尚未收到開獎結果")
            self.result_label.setStyleSheet("color: #e5e7eb; font-size: 9pt; font-weight: bold;")
            self.detail_label.setText("")
            return

        winner = (info.get("winner") or "").upper()
        winner_map = {
            "B": ("莊", "#ef4444"),
            "P": ("閒", "#3b82f6"),
            "T": ("和", "#10b981"),
        }
        winner_text, color = winner_map.get(winner, (winner or "?", "#eab308"))
        self.result_label.setText(f"最新結果：{winner_text}")
        self.result_label.setStyleSheet(f"color: {color}; font-size: 9pt; font-weight: bold;")

        round_id = info.get("round_id") or "--"
        ts = info.get("received_at")
        ts_text = self._format_timestamp(ts)
        table_id = info.get("table_id")
        display_id = TABLE_ID_DISPLAY_MAP.get(table_id, table_id) if table_id else "--"

        detail_lines = []
        if display_id and display_id != "--":
            if table_id and display_id != table_id:
                detail_lines.append(f"桌號：{display_id} ({table_id})")
            else:
                detail_lines.append(f"桌號：{display_id}")
        detail_lines.append(f"局號：{round_id}")
        detail_lines.append(f"時間：{ts_text}")
        self.detail_label.setText("\n".join(detail_lines))

    def current_table(self) -> Optional[str]:
        return self._current_table or None

    def select_table(self, table_id: str) -> None:
        if not table_id or table_id not in self._tables:
            return
        target_index = self._tables.index(table_id)
        if target_index != self.combo.currentIndex():
            self.combo.setCurrentIndex(target_index)

    def _on_combo_changed(self, index: int) -> None:
        if self._updating_combo:
            return
        if index < 0:
            self._current_table = ""
        else:
            data = self.combo.itemData(index)
            if isinstance(data, str) and data:
                self._current_table = data
            elif 0 <= index < len(self._tables):
                self._current_table = self._tables[index]
            else:
                self._current_table = ""
        self._emit_selection()

    def _emit_selection(self) -> None:
        table = self.current_table()
        self.table_selected.emit(table or "")

    @staticmethod
    def _format_timestamp(ts: Optional[Any]) -> str:
        if ts is None:
            return "--"
        try:
            ts_value = float(ts)
        except (TypeError, ValueError):
            return str(ts)

        if ts_value > 1e12:
            ts_value /= 1000.0
        try:
            return time.strftime("%H:%M:%S", time.localtime(ts_value))
        except Exception:
            return str(int(ts_value))


class LineSummaryCard(QFrame):
    """顯示 Line 策略總覽的卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.metric_labels: Dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QHBoxLayout()
        title = QLabel("策略總覽")
        title.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        icon = QLabel("🧠")
        icon.setFont(QFont("Segoe UI Emoji", 14))
        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(16)
        metric_defs = [
            ("total", "總資金"),
            ("free", "可用資金"),
            ("exposure", "當前曝險"),
            ("active", "活躍策略"),
            ("frozen", "凍結策略"),
        ]
        for key, caption in metric_defs:
            widget = QWidget()
            widget_layout = QVBoxLayout(widget)
            widget_layout.setContentsMargins(0, 0, 0, 0)
            widget_layout.setSpacing(2)

            cap_label = QLabel(caption)
            cap_label.setStyleSheet("color: #9ca3af; font-size: 9pt;")
            value_label = QLabel("--")
            value_font = QFont("Microsoft YaHei UI", 12, QFont.Bold)
            value_label.setFont(value_font)
            value_label.setStyleSheet("color: #f9fafb;")

            widget_layout.addWidget(cap_label)
            widget_layout.addWidget(value_label)
            metrics_layout.addWidget(widget)
            self.metric_labels[key] = value_label

        metrics_layout.addStretch()
        layout.addLayout(metrics_layout)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["桌號", "策略", "階段", "層數", "注額", "PnL", "凍結"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #111827;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #1f2937;
                color: #d1d5db;
                padding: 4px;
                border: 1px solid #374151;
            }
            QTableWidget::item {
                padding: 4px;
            }
        """)
        layout.addWidget(self.table)

        self.placeholder = QLabel("尚未啟用策略或等待資料…")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("color: #9ca3af;")
        layout.addWidget(self.placeholder)

        self._set_placeholder(True)

    def _set_placeholder(self, enabled: bool) -> None:
        self.placeholder.setVisible(enabled)
        self.table.setVisible(not enabled)

    def update_summary(self, summary: Optional[Dict[str, Any]]) -> None:
        lines = []
        capital = {}
        if isinstance(summary, dict):
            lines = summary.get("lines") or []
            capital = summary.get("capital") or {}

        total = capital.get("bankroll_total")
        free = capital.get("bankroll_free")
        exposure = capital.get("exposure_total")
        self.metric_labels["total"].setText(self._fmt_money(total))
        self.metric_labels["free"].setText(self._fmt_money(free))
        self.metric_labels["exposure"].setText(self._fmt_money(exposure))

        active = sum(1 for ln in lines if ln.get("phase") not in {"idle", "exited"})
        frozen = sum(1 for ln in lines if ln.get("frozen"))
        self.metric_labels["active"].setText(str(active))
        self.metric_labels["frozen"].setText(str(frozen))

        if not lines:
            self.table.setRowCount(0)
            self._set_placeholder(True)
            return

        self._set_placeholder(False)
        lines_sorted = sorted(
            lines,
            key=lambda item: abs(float(item.get("stake") or 0.0)),
            reverse=True,
        )
        max_rows = min(len(lines_sorted), 8)
        self.table.setRowCount(max_rows)
        phase_map = {
            "idle": "待命",
            "armed": "待進場",
            "entered": "已下單",
            "waiting_result": "等待結果",
            "frozen": "凍結",
            "exited": "結束",
        }
        for row in range(max_rows):
            item = lines_sorted[row]
            data = [
                item.get("table", "--"),
                item.get("strategy", "--"),
                phase_map.get(item.get("phase"), item.get("phase", "--")),
                str(item.get("current_layer", "--")),
                self._fmt_money(item.get("stake")),
                self._fmt_money(item.get("pnl"), signed=True),
                "是" if item.get("frozen") else "否",
            ]
            for col, value in enumerate(data):
                cell = QTableWidgetItem(str(value))
                if col in (4, 5):
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    cell.setTextAlignment(Qt.AlignCenter)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, cell)

    @staticmethod
    def _fmt_money(value: Optional[Any], signed: bool = False) -> str:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return "--"
        fmt = "{:+,.0f}" if signed else "{:,.0f}"
        return fmt.format(num)


class LogViewer(QFrame):
    """日誌檢視器"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)

        # 標題與篩選
        header_layout = QHBoxLayout()

        title = QLabel("📋 即時日誌")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))

        self.level_filter = QComboBox()
        self.level_filter.addItems(["全部", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_filter.setCurrentText("全部")

        self.module_filter = QComboBox()
        self.module_filter.addItems(["全部", "Engine", "Events", "Config", "Actuator", "Line"])

        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_logs)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(QLabel("等級:"))
        header_layout.addWidget(self.level_filter)
        header_layout.addWidget(QLabel("模組:"))
        header_layout.addWidget(self.module_filter)
        header_layout.addWidget(clear_btn)

        # 日誌文字區域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #0f0f0f;
                color: #e5e5e5;
                border: 1px solid #333333;
                border-radius: 4px;
            }
        """)

        layout.addLayout(header_layout)
        layout.addWidget(self.log_text)

    def add_log(self, level: str, module: str, message: str):
        """添加日誌"""
        # 篩選檢查
        if self.level_filter.currentText() != "全部" and level != self.level_filter.currentText():
            return
        if self.module_filter.currentText() != "全部" and module != self.module_filter.currentText():
            return

        # 顏色對應
        colors = {
            "DEBUG": "#9ca3af",
            "INFO": "#60a5fa",
            "WARNING": "#f59e0b",
            "ERROR": "#ef4444"
        }
        color = colors.get(level, "#ffffff")

        # 格式化訊息
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f'<span style="color: #6b7280;">{timestamp}</span> <span style="color: {color}; font-weight: bold;">[{level}]</span> <span style="color: #a3a3a3;">{module}:</span> <span style="color: #e5e5e5;">{message}</span>'

        # 添加到文字區域
        self.log_text.append(formatted_msg)

        # 自動滾動到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

        # 限制日誌長度 (保持最後 1000 行)
        document = self.log_text.document()
        if document.blockCount() > 1000:
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.Start)
            for _ in range(100):  # 刪除前 100 行
                cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

    def clear_logs(self):
        """清除日誌"""
        self.log_text.clear()

class ClickSequenceCard(QFrame):
    """點擊順序設定卡片"""
    sequence_changed = Signal(list)

    def __init__(self):
        super().__init__()
        self.enabled_positions = []
        self.sequence_combos = []
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)

        # 標題
        title = QLabel("🎯 點擊順序設定")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        layout.addWidget(title)

        # 說明
        info = QLabel("根據已設定的位置（✓）設定點擊順序：")
        info.setStyleSheet("color: #9ca3af; font-size: 9pt;")
        layout.addWidget(info)

        # 刷新按鈕
        refresh_btn = QPushButton("🔄 刷新位置")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_positions)
        layout.addWidget(refresh_btn)

        # 滾動區域包裝器
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setMaximumHeight(300)  # 限制最大高度
        scroll_area.setMinimumHeight(120)  # 設置最小高度
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #4b5563;
                border-radius: 6px;
                background-color: #1f2937;
                padding: 4px;
            }
            QScrollBar:vertical {
                background-color: #4b5563;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #6b7280;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #9ca3af;
            }
        """)

        # 序列容器 widget
        self.sequence_widget = QWidget()
        self.sequence_container = QVBoxLayout(self.sequence_widget)
        self.sequence_container.setContentsMargins(8, 8, 8, 8)
        self.sequence_container.setSpacing(8)

        scroll_area.setWidget(self.sequence_widget)
        layout.addWidget(scroll_area)

        # 保存按鈕
        save_btn = QPushButton("💾 保存順序")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        save_btn.clicked.connect(self.save_sequence)
        layout.addWidget(save_btn)

        # 初始顯示
        self.update_no_data_message()

    def update_no_data_message(self):
        """顯示無資料訊息"""
        # 清空容器
        self.clear_sequence_container()

        no_data = QLabel("📝 請先在「位置校準」頁面設定位置")
        no_data.setStyleSheet("""
            QLabel {
                color: #6b7280;
                font-style: italic;
                padding: 20px;
                text-align: center;
            }
        """)
        no_data.setAlignment(Qt.AlignCenter)
        self.sequence_container.addWidget(no_data)

    def update_enabled_positions(self, positions_data: dict):
        """更新可用的位置（使用 ✓/✗ 狀態判斷）"""
        if not positions_data:
            self.update_no_data_message()
            return

        points = positions_data.get("points", {})
        # 只包含有座標的 position（✓ 狀態）
        available_points = {k: v for k, v in points.items()
                           if "x" in v and "y" in v}

        if not available_points:
            self.update_no_data_message()
            return

        self.enabled_positions = list(available_points.keys())
        self.build_sequence_interface()

    def clear_sequence_container(self):
        """清空序列容器"""
        while self.sequence_container.count():
            child = self.sequence_container.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def build_sequence_interface(self):
        """建立序列設定界面"""
        self.clear_sequence_container()
        self.sequence_combos = []

        # 載入現有順序
        current_sequence = self.load_current_sequence()

        action_descriptions = {
            "banker": "點擊莊家",
            "player": "點擊閒家",
            "tie": "點擊和局",
            "chip_1k": "選擇 1K 籌碼",
            "chip_5k": "選擇 5K 籌碼",
            "chip_10k": "選擇 10K 籌碼",
            "chip_100": "選擇 100 籌碼",
            "confirm": "確認下注",
            "cancel": "取消下注"
        }

        for i, position in enumerate(self.enabled_positions):
            # 步驟標籤
            step_layout = QHBoxLayout()

            step_label = QLabel(f"步驟 {i+1}:")
            step_label.setFixedWidth(80)
            step_label.setStyleSheet("font-weight: bold; color: #f3f4f6; font-size: 10pt;")

            # 下拉選單（禁用滾輪）
            combo = NoWheelComboBox()
            combo.setFocusPolicy(Qt.StrongFocus)  # 只有點擊時才能獲得焦點
            combo.addItem("-- 請選擇動作 --", "")

            for pos in self.enabled_positions:
                desc = action_descriptions.get(pos, f"點擊 {pos}")
                combo.addItem(desc, pos)

            # 設定當前值
            if i < len(current_sequence) and current_sequence[i] in self.enabled_positions:
                index = combo.findData(current_sequence[i])
                if index >= 0:
                    combo.setCurrentIndex(index)

            combo.setStyleSheet("""
                QComboBox {
                    background-color: #1f2937;
                    color: #f3f4f6;
                    border: 1px solid #4b5563;
                    border-radius: 4px;
                    padding: 6px 12px;
                    min-height: 28px;
                    font-size: 10pt;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background-color: #1f2937;
                    color: #f3f4f6;
                    selection-background-color: #3b82f6;
                    border: 1px solid #4b5563;
                }
            """)

            self.sequence_combos.append(combo)

            step_layout.addWidget(step_label)
            step_layout.addWidget(combo)

            self.sequence_container.addLayout(step_layout)

    def load_current_sequence(self) -> list:
        """載入當前保存的順序"""
        try:
            import json
            if os.path.exists("configs/positions.json"):
                with open("configs/positions.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("click_sequence", [])
        except:
            pass
        return []

    def save_sequence(self):
        """保存點擊順序"""
        sequence = []
        for combo in self.sequence_combos:
            selected = combo.currentData()
            if selected:  # 不是空選項
                sequence.append(selected)

        # 檢查是否有重複
        if len(sequence) != len(set(sequence)):
            QMessageBox.warning(self, "順序錯誤", "不能有重複的動作，請檢查設定！")
            return

        # 保存到配置檔
        try:
            import json
            if os.path.exists("configs/positions.json"):
                with open("configs/positions.json", "r", encoding="utf-8") as f:
                    data = json.load(f)

                data["click_sequence"] = sequence

                with open("configs/positions.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # 發送信號
                self.sequence_changed.emit(sequence)

                # 顯示成功訊息
                QMessageBox.information(self, "保存成功",
                    f"點擊順序已保存：\n{' → '.join(sequence)}")

        except Exception as e:
            QMessageBox.critical(self, "保存失敗", f"無法保存設定：{e}")

    def refresh_positions(self):
        """刷新位置資料"""
        try:
            import json
            if os.path.exists("configs/positions.json"):
                with open("configs/positions.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.update_enabled_positions(data)

                # 顯示刷新成功訊息
                from ..app_state import emit_toast
                emit_toast("位置資料已刷新", "success")
            else:
                from ..app_state import emit_toast
                emit_toast("找不到位置配置檔", "warning")
        except Exception as e:
            from ..app_state import emit_toast
            emit_toast(f"刷新失敗: {e}", "error")

class StatsCard(QFrame):
    """統計卡片"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)

        title = QLabel("📊 會話統計")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        layout.addWidget(title)

        # 統計表格
        self.stats_table = QTableWidget(4, 2)
        self.stats_table.setHorizontalHeaderLabels(["項目", "數值"])
        self.stats_table.verticalHeader().setVisible(False)

        # 設定表格樣式
        self.stats_table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                gridline-color: #404040;
                border: 1px solid #555555;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #404040;
            }
        """)

        # 初始化數據
        stats_items = [
            ("局數", "0"),
            ("淨利", "0"),
            ("最後結果", "-"),
            ("運行時間", "00:00:00")
        ]

        for i, (item, value) in enumerate(stats_items):
            self.stats_table.setItem(i, 0, QTableWidgetItem(item))
            self.stats_table.setItem(i, 1, QTableWidgetItem(value))

        # 調整列寬
        header = self.stats_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)

        layout.addWidget(self.stats_table)

    def update_stats(self, stats: dict):
        """更新統計資料"""
        rounds = stats.get("rounds", 0)
        net = stats.get("net", 0)
        last_winner = stats.get("last_winner", "-")

        # 轉換結果顯示
        winner_display = {
            "B": "莊贏", "P": "閒贏", "T": "和局", None: "-"
        }.get(last_winner, str(last_winner))

        self.stats_table.item(0, 1).setText(str(rounds))
        self.stats_table.item(1, 1).setText(f"{net:+d}")
        self.stats_table.item(2, 1).setText(winner_display)

        # 設定淨利顏色
        if net > 0:
            self.stats_table.item(1, 1).setForeground(QColor("#10b981"))
        elif net < 0:
            self.stats_table.item(1, 1).setForeground(QColor("#ef4444"))
        else:
            self.stats_table.item(1, 1).setForeground(QColor("#6b7280"))

class DashboardPage(QWidget):
    """實戰主控台頁面"""
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self.engine_worker = None
        self.start_time = None

        # 直接檢測相關屬性
        self.detector = None
        self.detection_timer = QTimer()
        self.detection_active = False
        self.last_decision = None  # 記錄上次決策，防重複觸發
        self.is_triggering = False  # 防止重複觸發標志
        self._last_counter_log = None  # 節流計數日誌使用
        self.latest_results: Dict[str, Dict[str, Any]] = {}
        self.line_summary: Dict[str, Any] = {}
        self.selected_result_table: Optional[str] = None

        self.setup_ui()
        self.setup_engine()
        self.setup_direct_detection()

    def create_strategy_status_indicator(self):
        """創建策略運行狀態指示器"""
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(8)

        # 標題
        title = QLabel("🎯 策略系統狀態")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        layout.addWidget(title)

        # 狀態指示器
        self.strategy_status_label = QLabel()
        self.strategy_status_label.setAlignment(Qt.AlignCenter)
        self.strategy_status_label.setWordWrap(True)
        self.strategy_status_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.strategy_status_label.setMinimumHeight(60)
        layout.addWidget(self.strategy_status_label)

        # 詳細信息
        self.strategy_detail_label = QLabel()
        self.strategy_detail_label.setAlignment(Qt.AlignLeft)
        self.strategy_detail_label.setWordWrap(True)
        self.strategy_detail_label.setStyleSheet("color: #9ca3af; font-size: 9pt;")
        layout.addWidget(self.strategy_detail_label)

        # 初始狀態
        self.update_strategy_status_display(None)

        return frame

    def update_strategy_status_display(self, summary):
        """更新策略狀態顯示"""
        if not summary:
            self.strategy_status_label.setText("⚪ 策略系統未啟動")
            self.strategy_status_label.setStyleSheet("""
                QLabel {
                    background-color: #374151;
                    border: 2px solid #6b7280;
                    border-radius: 6px;
                    padding: 12px;
                    color: #9ca3af;
                    font-weight: bold;
                }
            """)
            self.strategy_detail_label.setText("等待啟動引擎...")
            return

        lines = summary.get("lines", [])
        capital = summary.get("capital", {})

        # 計算活躍策略數量和策略定義數量
        active_count = sum(1 for ln in lines if ln.get("phase") not in {"idle", "exited"})
        frozen_count = sum(1 for ln in lines if ln.get("frozen"))
        total_pnl = sum(ln.get("pnl", 0.0) for ln in lines)

        # 統計不同策略和桌台數量
        unique_strategies = set(ln.get("strategy") for ln in lines if ln.get("strategy"))
        unique_tables = set(ln.get("table") for ln in lines if ln.get("table"))
        num_strategies = len(unique_strategies)
        num_tables = len(unique_tables)

        # 判斷狀態
        if active_count > 0:
            status_text = f"🟢 運行中 ({active_count} 個活躍)"
            status_color = "#10b981"
            border_color = "#10b981"
        elif len(lines) > 0:
            if num_strategies == 1:
                status_text = f"🟡 待機中 (1 個策略監控 {num_tables} 個桌台)"
            else:
                status_text = f"🟡 待機中 ({num_strategies} 個策略監控 {num_tables} 個桌台)"
            status_color = "#f59e0b"
            border_color = "#f59e0b"
        else:
            status_text = "⚪ 無策略運行"
            status_color = "#6b7280"
            border_color = "#6b7280"

        self.strategy_status_label.setText(status_text)
        self.strategy_status_label.setStyleSheet(f"""
            QLabel {{
                background-color: #374151;
                border: 2px solid {border_color};
                border-radius: 6px;
                padding: 12px;
                color: {status_color};
                font-weight: bold;
            }}
        """)

        # 詳細信息
        details = []
        if frozen_count > 0:
            details.append(f"⚠️ {frozen_count} 個策略已凍結")
        details.append(f"總 PnL: {total_pnl:+.2f}")
        details.append(f"可用資金: {capital.get('bankroll_free', 0):.0f}/{capital.get('bankroll_total', 0):.0f}")

        self.strategy_detail_label.setText(" | ".join(details))

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 頂部控制區域
        self.setup_control_panel(layout)

        # 主要內容區域 (分割器)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # 左側：日誌區域
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self.log_viewer = LogViewer()
        left_layout.addWidget(self.log_viewer)

        splitter.addWidget(left_frame)

        # 右側：狀態與統計（標籤頁形式）
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(12)

        # 創建組件
        self.strategy_status_card = self.create_strategy_status_indicator()
        self.next_bet_card = NextBetCard()
        # self.click_sequence_card = ClickSequenceCard()  # 已過時：SmartChipPlanner 自動生成計畫

        # 標籤頁（策略狀態 | 即將下注）
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #374151;
                background-color: #111827;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #1f2937;
                color: #d1d5db;
                padding: 10px 20px;
                margin: 0 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 10pt;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #374151;
            }
        """)

        # Tab 1: 策略狀態
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(8, 8, 8, 8)
        tab1_layout.addWidget(self.strategy_status_card)
        tab1_layout.addStretch()

        # Tab 2: 即將下注
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setContentsMargins(8, 8, 8, 8)
        tab2_layout.addWidget(self.next_bet_card)
        tab2_layout.addStretch()

        tabs.addTab(tab1, "🎯 策略狀態")
        tabs.addTab(tab2, "📌 即將下注")

        right_layout.addWidget(tabs, 1)  # 給予彈性空間

        splitter.addWidget(right_frame)

        # 設定分割比例 (日誌:狀態 = 1:1，讓右側有更多空間顯示下注資訊)
        splitter.setSizes([600, 600])

    def setup_control_panel(self, parent_layout):
        """設定控制面板"""
        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.StyledPanel)
        control_frame.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 6px;
            }
        """)

        control_layout = QVBoxLayout(control_frame)
        control_layout.setContentsMargins(6, 6, 6, 6)
        control_layout.setSpacing(8)

        # 狀態卡片行
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.state_card = StatusCard("引擎狀態", "🤖")
        self.mode_card = StatusCard("運行模式", "🧪")
        self.detection_card = StatusCard("檢測狀態", "🎯")
        self.result_card = ResultCard()
        status_row.addWidget(self.state_card, 1)
        status_row.addWidget(self.mode_card, 1)
        status_row.addWidget(self.detection_card, 1)
        status_row.addWidget(self.result_card, 1)
        status_row.addStretch()
        control_layout.addLayout(status_row)

        # 控制按鈕
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        # 模擬實戰按鈕
        self.simulate_btn = QPushButton("🎯 模擬實戰")
        self.simulate_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:disabled {
                background-color: #6b7280;
            }
        """)
        self.simulate_btn.clicked.connect(self.start_simulation)

        # 開始實戰按鈕
        self.start_btn = QPushButton("⚡ 開始實戰")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
            QPushButton:disabled {
                background-color: #6b7280;
            }
        """)
        self.start_btn.clicked.connect(self.start_real_battle)

        # 停止按鈕
        self.stop_btn = QPushButton("🛑 停止")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: white;
                border: 1px solid #6b7280;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
            QPushButton:disabled {
                background-color: #1f2937;
                color: #6b7280;
            }
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_engine)

        # 測試按鈕
        self.test_btn = QPushButton("測試順序")
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
        """)
        self.test_btn.clicked.connect(self.test_sequence)

        button_layout.addWidget(self.simulate_btn)
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.test_btn)
        button_layout.addStretch()

        control_layout.addLayout(button_layout)

        parent_layout.addWidget(control_frame)

    def setup_engine(self):
        """設定引擎工作執行緒"""
        self.engine_worker = EngineWorker()

        # 連接訊號
        self.engine_worker.state_changed.connect(self.on_state_changed)
        self.engine_worker.session_stats.connect(self.on_stats_updated)
        self.engine_worker.log_message.connect(self.on_log_message)
        self.engine_worker.engine_status.connect(self.on_engine_status)
        self.engine_worker.next_bet_info.connect(self.on_next_bet_info)

        # 連接結果卡片信號
        self.result_card.table_selected.connect(self.on_result_table_selected)

        # 啟動工作執行緒
        self.engine_worker.start()

        # 初始化引擎（等啟動時再設定模式）
        success = self.engine_worker.initialize_engine()
        if success:
            self.log_viewer.add_log("INFO", "Dashboard", "引擎工作執行緒已準備就緒")
        else:
            self.log_viewer.add_log("ERROR", "Dashboard", "引擎初始化失敗")

        # 設定初始狀態
        self.mode_card.update_content("⏸ 待機中", "#6b7280")
        initial_detection_info = (
            "NCC: -- | 綠色: --\n"
            "計數: --/--"
        )
        self.detection_card.update_content(f"⚪ 等待啟動\n{initial_detection_info}", "#6b7280", False)

        # 載入 positions 數據
        self.load_positions_data()

    def start_simulation(self):
        """啟動模擬實戰模式"""
        if not self.engine_worker:
            return

        # 檢查是否已選擇桌號
        selected_table = self.result_card.current_table()
        if not selected_table:
            QMessageBox.warning(self, "無法啟動", "請先選擇一個桌號！")
            return

        # 檢查配置完整性
        if not self._check_config_ready():
            return

        # 禁用桌號選擇器
        self.result_card.combo.setEnabled(False)

        # 設定選定的桌號到引擎
        self.engine_worker.set_selected_table(selected_table)

        # 啟動模擬模式
        success = self.engine_worker.start_engine(mode="simulation")

        if success:
            self.simulate_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.mode_card.update_content("🎯 模擬實戰中", "#0284c7")
            self.detection_card.update_content("檢測中", "#f59e0b", False)
            self.start_time = self.get_current_time()

            # 更新NextBetCard狀態為運行中
            self.next_bet_card.set_engine_running(True)

            # 啟動運行時間計時器
            self.runtime_timer = QTimer()
            self.runtime_timer.timeout.connect(self.update_runtime)
            self.runtime_timer.start(1000)

            # 啟動直接檢測
            self.start_direct_detection()

            self.log_viewer.add_log("INFO", "Dashboard", "🎯 模擬實戰模式已啟動 - 將移動滑鼠但不實際點擊")

    def start_real_battle(self):
        """啟動真實實戰模式"""
        if not self.engine_worker:
            return

        # 檢查是否已選擇桌號
        selected_table = self.result_card.current_table()
        if not selected_table:
            QMessageBox.warning(self, "無法啟動", "請先選擇一個桌號！")
            return

        # 檢查配置完整性
        if not self._check_config_ready():
            return

        # 確認對話框
        reply = QMessageBox.question(
            self, "確認實戰模式",
            "⚠️ 您即將啟動實戰模式！\n\n" +
            "系統將會：\n" +
            "• 檢測遊戲畫面的「請下注」狀態\n" +
            "• 根據策略自動移動滑鼠並點擊\n" +
            "• 執行真實的下注操作\n\n" +
            "確定要繼續嗎？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 禁用桌號選擇器
        self.result_card.combo.setEnabled(False)

        # 設定選定的桌號到引擎
        self.engine_worker.set_selected_table(selected_table)

        # 啟動實戰模式
        success = self.engine_worker.start_engine(mode="real")

        if success:
            self.simulate_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.mode_card.update_content("⚡ 實戰進行中", "#dc2626")
            self.detection_card.update_content("檢測中", "#f59e0b", False)
            self.start_time = self.get_current_time()

            # 更新NextBetCard狀態為運行中
            self.next_bet_card.set_engine_running(True)

            # 啟動運行時間計時器
            self.runtime_timer = QTimer()
            self.runtime_timer.timeout.connect(self.update_runtime)
            self.runtime_timer.start(1000)

            # 啟動直接檢測
            self.start_direct_detection()

            self.log_viewer.add_log("WARNING", "Dashboard", "⚡ 實戰模式已啟動 - 將執行真實點擊操作")

    def _check_config_ready(self):
        """檢查配置是否就緒"""
        import os

        # 檢查 positions.json
        if not os.path.exists("configs/positions.json"):
            QMessageBox.warning(self, "配置缺失", "未找到 positions.json\n請先完成位置校準！")
            return False

        # 檢查 strategy.json
        if not os.path.exists("configs/strategy.json"):
            QMessageBox.warning(self, "配置缺失", "未找到 strategy.json\n請先完成策略設定！")
            return False

        # 檢查模板路徑（在 positions.json 的 overlay_params 中）
        try:
            with open("configs/positions.json", "r", encoding="utf-8") as f:
                pos_data = json.load(f)
            template_paths = pos_data.get("overlay_params", {}).get("template_paths", {})
            qing_path = template_paths.get("qing")

            if not qing_path or not os.path.exists(qing_path):
                QMessageBox.warning(self, "配置缺失", "未設定檢測模板或模板文件不存在\n請先在「可下注判斷」頁面設定模板！")
                return False
        except:
            QMessageBox.warning(self, "配置缺失", "無法讀取模板配置\n請先完成 Overlay 設定！")
            return False

        return True

    def stop_engine(self):
        """停止引擎"""
        # 停止直接檢測
        self.stop_direct_detection()

        if self.engine_worker:
            self.engine_worker.stop_engine()

        # 更新NextBetCard狀態為等待啟動
        self.next_bet_card.set_engine_running(False)

        # 重新啟用桌號選擇器
        self.result_card.combo.setEnabled(True)

        # 重置按鈕狀態
        self.simulate_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # 重置模式顯示
        self.mode_card.update_content("⏸ 已停止", "#6b7280")
        stopped_detection_info = (
            "NCC: -- | 綠色: --\n"
            "計數: --/--"
        )
        self.detection_card.update_content(f"⚫ 已停止\n{stopped_detection_info}", "#6b7280", False)

        if hasattr(self, 'runtime_timer'):
            self.runtime_timer.stop()

        self.log_viewer.add_log("INFO", "Dashboard", "🛑 引擎已停止")

    def on_state_changed(self, state):
        """引擎狀態改變"""
        state_display = {
            "idle": "● 待機",
            "running": "⚡ 運行中",
            "betting_open": "● 下注期",
            "placing_bets": "⚡ 下注中",
            "in_round": "● 局中",
            "eval_result": "📊 結算中",
            "error": "✗ 錯誤",
            "paused": "⏸ 暫停"
        }.get(state, f"? {state}")

        color = {
            "idle": "#10b981",
            "running": "#3b82f6",
            "betting_open": "#f59e0b",
            "placing_bets": "#3b82f6",
            "in_round": "#ef4444",
            "eval_result": "#8b5cf6",
            "error": "#ef4444",
            "paused": "#6b7280"
        }.get(state, "#ffffff")

        self.state_card.update_content(state_display, color)

    def on_stats_updated(self, stats):
        """統計資料更新"""
        # StatsCard已移除,統計信息現在整合到策略狀態顯示中
        pass

    def _extract_log_context(self, message: str) -> Tuple[Optional[str], str]:
        if not message:
            return None, message
        table_id = None
        cleaned = message
        table_match = TABLE_TAG_RE.search(message)
        if table_match:
            table_id = table_match.group(1)
            cleaned = cleaned.replace(table_match.group(0), "", 1)
        display_match = DISPLAY_TAG_RE.search(cleaned)
        if display_match:
            cleaned = cleaned.replace(display_match.group(0), "", 1)
        return table_id, cleaned.lstrip()

    def _should_display_log(self, table_id: Optional[str]) -> bool:
        if not self.selected_result_table:
            return True
        return table_id == self.selected_result_table

    def _process_incoming_log(self, level: str, module: str, message: str) -> None:
        table_id, cleaned = self._extract_log_context(message)
        if not self._should_display_log(table_id):
            return
        self.log_viewer.add_log(level, module, cleaned)

    def _append_table_log(self, level: str, module: str, table_id: Optional[str], text: str) -> None:
        if table_id:
            display = TABLE_ID_DISPLAY_MAP.get(table_id, table_id)
            prefix = f"[table={table_id}]"
            if display and display != table_id:
                prefix += f"[display={display}]"
            message = f"{prefix} {text}"
        else:
            message = text
        self._process_incoming_log(level, module, message)

    def on_log_message(self, level, module, message):
        """接收日誌訊息"""
        self._process_incoming_log(level, module, message)

    def on_next_bet_info(self, bet_info: dict):
        """接收即將下注的詳細資訊並更新 NextBetCard"""
        try:
            # 從 bet_info 提取所有必要資訊
            table_id = bet_info.get('table_id', '')
            strategy = bet_info.get('strategy', '')
            layer = bet_info.get('layer', 'N/A')
            direction = bet_info.get('direction', '')
            amount = bet_info.get('amount', 0)
            recipe = bet_info.get('recipe', '')

            # 轉換方向顯示 (如果是縮寫形式)
            direction_map = {
                "banker": "B",
                "player": "P",
                "tie": "T"
            }
            direction_display = direction_map.get(direction.lower(), direction)

            # 更新 NextBetCard
            self.next_bet_card.update_next_bet(
                table=table_id,
                strategy=strategy,
                current_layer=layer.split('/')[0] if '/' in str(layer) else layer,
                direction=direction_display,
                amount=amount,
                recipe=recipe
            )

        except Exception as e:
            self.log_viewer.add_log("ERROR", "Dashboard", f"更新下注卡片失敗: {e}")

    def on_engine_status(self, status):
        """引擎狀態更新"""
        latest = status.get("latest_results")
        if not isinstance(latest, dict):
            latest = {}
        self.latest_results = latest

        tables = sorted(latest.keys())
        self.result_card.set_stream_status(status.get("t9_stream_status"))
        self.result_card.set_tables(tables)

        current_table = self.result_card.current_table()
        info = None
        if current_table and current_table in latest:
            info = latest[current_table]
            self.selected_result_table = current_table
        elif tables:
            first_table = tables[0]
            info = latest.get(first_table)
            self.result_card.select_table(first_table)
            self.selected_result_table = first_table
        else:
            self.selected_result_table = None

        self.result_card.set_result(info)
        summary = status.get("line_summary")
        if not isinstance(summary, dict):
            summary = {}
        self.line_summary = summary

        # 更新策略狀態指示器
        self.update_strategy_status_display(summary)

    def on_result_table_selected(self, table_id: str):
        """使用者切換桌號"""
        previous = self.selected_result_table
        self.selected_result_table = table_id or None

        info = self.latest_results.get(table_id) if table_id else None
        self.result_card.set_result(info)

        if previous != self.selected_result_table:
            if self.selected_result_table:
                display = TABLE_ID_DISPLAY_MAP.get(self.selected_result_table, self.selected_result_table)
                display_text = display if display == self.selected_result_table else f"{display}（{self.selected_result_table}）"
                self._append_table_log("INFO", "Result", self.selected_result_table, f"切換到 {display_text}")
            else:
                self._process_incoming_log("INFO", "Result", "已清除桌號篩選")

    def load_positions_data(self):
        """載入 positions 配置數據"""
        # 不再需要載入點擊順序數據，SmartChipPlanner 自動生成計畫
        pass

    def update_runtime(self):
        """更新運行時間"""
        # StatsCard已移除,運行時間現在不再顯示
        # 如果需要顯示運行時間,可以整合到策略狀態顯示中
        pass

    def get_current_time(self):
        """獲取當前時間戳"""
        import time
        return int(time.time())

    def test_sequence(self):
        """測試完整配置 - 使用新的ChipProfile + SmartChipPlanner"""
        if not self.engine_worker:
            self.log_viewer.add_log("ERROR", "Dashboard", "引擎未初始化")
            return

        # 檢查是否正在觸發過程中
        if self.is_triggering:
            self.log_viewer.add_log("WARNING", "Dashboard", "⚠️ 系統正在執行點擊序列，請稍後再試")
            return

        # 檢查是否在檢測模式中
        if self.detection_active:
            self.log_viewer.add_log("WARNING", "Dashboard", "⚠️ 請先停止檢測模式再進行測試")
            return

        # 1. 配置驗證
        from src.utils.config_validator import ConfigValidator
        validator = ConfigValidator()
        results = validator.validate_all()

        if not results['overall'].complete:
            # 顯示缺失項目並引導
            missing_modules = []
            for module, result in results.items():
                if module != 'overall' and not result.complete:
                    missing_modules.append(f"• {module}: {result.message}")

            QMessageBox.warning(
                self, "配置不完整",
                "請先完成以下配置:\n\n" + "\n".join(missing_modules) +
                "\n\n點擊確定後，配置狀態卡片會引導您完成設定。"
            )
            self.log_viewer.add_log("WARNING", "Test", "配置不完整，無法執行測試")
            return

        # 2. 載入ChipProfile
        try:
            from src.autobet.chip_profile_manager import ChipProfileManager
            from src.autobet.chip_planner import SmartChipPlanner

            manager = ChipProfileManager()
            chip_profile = manager.load_profile("default")

            # 獲取已校準的籌碼列表
            calibrated_chips = chip_profile.get_calibrated_chips()
            if not calibrated_chips:
                raise ValueError("沒有已校準的籌碼，請先校準籌碼位置")

            # 3. 生成測試計劃
            planner = SmartChipPlanner(calibrated_chips)
            test_amount = 1100  # 測試金額: 1100元

            plan = planner.plan_bet(test_amount, max_clicks=8)

            # 4. 顯示測試計劃
            chips_str = " + ".join([f"{c.value}元" for c in plan.chips])
            total_clicks = len(plan.chips) + 2  # 籌碼點擊 + 下注 + 確認

            self.log_viewer.add_log(
                "INFO", "Test",
                f"🧪 測試計劃: {test_amount}元 = {chips_str}"
            )
            self.log_viewer.add_log(
                "INFO", "Test",
                f"📊 總點擊次數: {total_clicks} (籌碼{len(plan.chips)}次 + 下注1次 + 確認1次)"
            )

            # 5. 設置測試標志
            self.is_triggering = True

            # 6. 執行測試
            self.log_viewer.add_log("INFO", "Test", "▶️ 開始執行測試序列...")
            self.engine_worker.force_test_sequence()

        except Exception as e:
            self.log_viewer.add_log("ERROR", "Test", f"測試失敗: {e}")
            QMessageBox.critical(self, "測試失敗", f"執行測試時發生錯誤:\n{e}")
        finally:
            # 3秒後重置標志
            QTimer.singleShot(3000, self._reset_triggering_flag)

    def setup_direct_detection(self):
        """設定直接檢測（類似 Overlay Page）"""
        self.detection_timer.timeout.connect(self.process_detection_frame)
        self.detection_timer.setInterval(120)  # 120ms，與 Overlay Page 一致

        # 初始化檢測器
        self.create_direct_detector()

    def create_direct_detector(self):
        """創建直接檢測器"""
        try:
            from src.autobet.detectors import ProductionOverlayDetector

            # 載入位置配置
            positions_file = "configs/positions.json"
            if not os.path.exists(positions_file):
                return False

            with open(positions_file, 'r', encoding='utf-8') as f:
                positions = json.load(f)

            # 檢測器配置
            config = {
                "open_threshold": 0.55,  # 降低NCC閾值，提高敏感度
                "close_threshold": 0.45,
                "k_open": 3,  # 調整為3幀，平衡穩定性和響應速度
                "k_close": 2,
                "green_hue_range": [90, 150],
                "green_sat_min": 0.45,
                "green_val_min": 0.55,
                "max_open_wait_ms": 8000,
                "cancel_on_close": True
            }

            self.detector = ProductionOverlayDetector(config)

            # 設定 ROI
            overlay_roi = positions.get("roi", {}).get("overlay")
            timer_roi = positions.get("roi", {}).get("timer")

            if overlay_roi and timer_roi:
                self.detector.set_rois(overlay_roi, timer_roi)

            # 載入模板
            template_path = positions.get("overlay_params", {}).get("template_paths", {}).get("qing")
            if template_path and os.path.exists(template_path):
                self.detector.load_qing_template(template_path)

            return True

        except Exception as e:
            self.log_viewer.add_log("ERROR", "Detection", f"檢測器初始化失敗: {e}")
            return False

    def process_detection_frame(self):
        """處理檢測幀（直接檢測）"""
        if not self.detector:
            return

        try:
            # 截取畫面並檢測
            import pyautogui
            from PIL import Image
            import numpy as np

            screenshot = pyautogui.screenshot()
            frame = np.array(screenshot)
            frame = frame[:, :, ::-1]  # RGB -> BGR

            # 執行檢測
            result = self.detector.process_frame(frame)

            # 提取關鍵檢測數據
            decision = result.get('decision', 'UNKNOWN')
            ncc_qing = result.get('ncc_qing', 0.0)
            hue = result.get('hue', 0.0)
            sat = result.get('sat', 0.0)
            in_green_gate = result.get('in_green_gate', False)
            open_counter = result.get('open_counter', '0/2')
            close_counter = result.get('close_counter', '0/2')
            reason = result.get('reason', '未知原因')

            # 格式化檢測詳情（精簡版）
            details = (
                f"NCC: {ncc_qing:.3f} | 綠色: {'✓' if in_green_gate else '✗'}\n"
                f"計數: {open_counter}/{close_counter}"
            )

            # 根據檢測結果更新狀態
            if decision == 'OPEN':
                self.detection_card.update_content(f"🟢 可下注\n{details}", "#10b981", True)
                # 防重複觸發：只在狀態從非OPEN變為OPEN時觸發，且當前未在觸發過程中
                if (hasattr(self, 'engine_worker') and self.engine_worker and self.detection_active and
                    self.last_decision != 'OPEN' and not self.is_triggering):
                    self.trigger_click_sequence()
            elif decision == 'CLOSED':
                self.detection_card.update_content(f"🔴 停止下注\n{details}", "#ef4444", False)
            else:
                self.detection_card.update_content(f"🟡 檢測中\n{details}", "#f59e0b", False)

            # 記錄當前決策
            self.last_decision = decision

            # 添加詳細調試日誌（當綠色護欄通過但未檢測到OPEN時）
            if in_green_gate and decision != 'OPEN':
                counter_state = (open_counter, close_counter)
                if counter_state != self._last_counter_log:
                    debug_msg = (
                        f"綠色護欄✓但未OPEN: NCC={ncc_qing:.3f} "
                        f"(需要≥{self.detector.open_th:.2f}), 計數={open_counter}"
                    )
                    self.log_viewer.add_log("DEBUG", "Detection", debug_msg)
                    self._last_counter_log = counter_state
            else:
                self._last_counter_log = None

        except Exception as e:
            self.log_viewer.add_log("ERROR", "Detection", f"檢測錯誤: {e}")
            self.detection_card.update_content(f"❌ 檢測錯誤\n{str(e)}", "#ef4444", False)

    def trigger_click_sequence(self):
        """觸發點擊序列（當檢測到可下注時）"""
        if self.is_triggering:
            return  # 如果已經在觸發過程中，直接返回

        self.is_triggering = True  # 設置觸發標志
        self.log_viewer.add_log("INFO", "Engine", "🎯 檢測到可下注")

        # 使用QTimer.singleShot延遲1秒後執行
        QTimer.singleShot(1000, self._execute_delayed_click_sequence)

    def _execute_delayed_click_sequence(self):
        """延遲執行點擊序列"""
        if self.engine_worker:
            self.engine_worker.trigger_click_sequence_async()
        else:
            self.log_viewer.add_log("ERROR", "Engine", "觸發點擊序列錯誤: 引擎未初始化")

        # 重置觸發標志（15秒後重置，確保序列執行完成）
        QTimer.singleShot(15000, self._reset_triggering_flag)

    def _reset_triggering_flag(self):
        """重置觸發標志"""
        self.is_triggering = False
        self.log_viewer.add_log("DEBUG", "Engine", "觸發標志已重置")

    def start_direct_detection(self):
        """開始直接檢測"""
        if self.detector:
            self.detection_active = True
            self.detection_timer.start()
            self.log_viewer.add_log("INFO", "Detection", "🎯 開始直接檢測")

    def stop_direct_detection(self):
        """停止直接檢測"""
        self.detection_active = False
        self.detection_timer.stop()
        self.is_triggering = False  # 重置觸發標志
        self.last_decision = None  # 重置決策記錄
        self.log_viewer.add_log("INFO", "Detection", "⏸️ 停止直接檢測")

    def closeEvent(self, event):
        """頁面關閉事件"""
        # 停止直接檢測
        self.stop_direct_detection()

        if self.engine_worker:
            self.engine_worker.stop_engine()
            self.engine_worker.quit()
            self.engine_worker.wait(3000)  # 等待最多 3 秒
        event.accept()
