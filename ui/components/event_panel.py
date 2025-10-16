# ui/components/event_panel.py
"""
事件區組件

顯示內容（§K）：
- 調度取捨理由（EV/先到/固定優先）
- 命中的風控層
- 錯誤與一鍵修復
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class EventItem(QFrame):
    """單個事件項"""

    fix_clicked = Signal(str)  # 發送事件 ID

    def __init__(
        self,
        event_type: str,
        message: str,
        timestamp: float,
        event_id: str = "",
        metadata: Optional[dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.event_type = event_type
        self.event_id = event_id
        self.metadata = metadata or {}

        self._build_ui(message, timestamp)

    def _build_ui(self, message: str, timestamp: float) -> None:
        """構建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 事件類型圖標與顏色
        icon_map = {
            "info": ("ℹ️", "#3b82f6"),
            "success": ("✅", "#10b981"),
            "warning": ("⚠️", "#f59e0b"),
            "error": ("❌", "#ef4444"),
            "conflict": ("⚔️", "#8b5cf6"),
            "risk": ("🛡️", "#dc2626"),
        }
        icon, color = icon_map.get(self.event_type, ("●", "#6b7280"))

        # 設置背景顏色
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1f2937;
                border-left: 4px solid {color};
                border-radius: 6px;
            }}
        """)

        # 圖標
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Microsoft YaHei UI", 14))
        icon_label.setFixedWidth(30)
        layout.addWidget(icon_label)

        # 訊息內容
        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)

        message_label = QLabel(message)
        message_label.setFont(QFont("Microsoft YaHei UI", 9))
        message_label.setStyleSheet("color: #f3f4f6;")
        message_label.setWordWrap(True)
        content_layout.addWidget(message_label)

        # 時間戳
        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        time_label = QLabel(time_str)
        time_label.setFont(QFont("Microsoft YaHei UI", 8))
        time_label.setStyleSheet("color: #6b7280;")
        content_layout.addWidget(time_label)

        # 額外元數據（如果有）
        if self.metadata:
            meta_parts = [f"{k}={v}" for k, v in self.metadata.items()]
            meta_text = " | ".join(meta_parts[:3])  # 最多顯示 3 個
            meta_label = QLabel(meta_text)
            meta_label.setFont(QFont("Microsoft YaHei UI", 7))
            meta_label.setStyleSheet("color: #9ca3af;")
            content_layout.addWidget(meta_label)

        layout.addLayout(content_layout, 1)

        # 修復按鈕（僅錯誤事件顯示）
        if self.event_type == "error":
            fix_btn = QPushButton("修復")
            fix_btn.setFont(QFont("Microsoft YaHei UI", 8))
            fix_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3b82f6;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #2563eb;
                }
            """)
            fix_btn.clicked.connect(lambda: self.fix_clicked.emit(self.event_id))
            layout.addWidget(fix_btn)


class EventPanel(QWidget):
    """事件面板"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.max_events = 100  # 最多顯示 100 個事件
        self._build_ui()

        # 定時刷新
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.start(1000)  # 1秒刷新一次

    def _build_ui(self) -> None:
        """構建 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 標題與控制
        header_layout = QHBoxLayout()

        header = QLabel("📋 事件記錄")
        header.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        header.setStyleSheet("color: #f9fafb;")
        header_layout.addWidget(header)

        header_layout.addStretch()

        # 清空按鈕
        clear_btn = QPushButton("清空")
        clear_btn.setFont(QFont("Microsoft YaHei UI", 9))
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #f3f4f6;
                padding: 6px 12px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        clear_btn.clicked.connect(self.clear_events)
        header_layout.addWidget(clear_btn)

        main_layout.addLayout(header_layout)

        # 篩選標籤
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        filter_label = QLabel("篩選:")
        filter_label.setFont(QFont("Microsoft YaHei UI", 9))
        filter_label.setStyleSheet("color: #9ca3af;")
        filter_layout.addWidget(filter_label)

        # 篩選按鈕
        self.filter_all_btn = QPushButton("全部")
        self.filter_error_btn = QPushButton("錯誤")
        self.filter_warning_btn = QPushButton("警告")
        self.filter_conflict_btn = QPushButton("衝突")
        self.filter_risk_btn = QPushButton("風控")

        for btn in [self.filter_all_btn, self.filter_error_btn, self.filter_warning_btn,
                    self.filter_conflict_btn, self.filter_risk_btn]:
            btn.setFont(QFont("Microsoft YaHei UI", 8))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #374151;
                    color: #9ca3af;
                    padding: 4px 10px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #4b5563;
                    color: #f3f4f6;
                }
                QPushButton:checked {
                    background-color: #3b82f6;
                    color: white;
                }
            """)
            btn.setCheckable(True)
            filter_layout.addWidget(btn)

        self.filter_all_btn.setChecked(True)
        filter_layout.addStretch()
        main_layout.addLayout(filter_layout)

        # 事件列表區
        self.event_list = QListWidget()
        self.event_list.setStyleSheet("""
            QListWidget {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            QListWidget::item {
                border: none;
                padding: 4px;
            }
        """)
        self.event_list.setSpacing(8)
        main_layout.addWidget(self.event_list)

    def add_event(
        self,
        event_type: str,
        message: str,
        event_id: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        """
        添加事件

        Args:
            event_type: "info", "success", "warning", "error", "conflict", "risk"
            message: 事件訊息
            event_id: 事件 ID（用於修復）
            metadata: 額外元數據
        """
        import time

        # 創建事件項
        event_item = EventItem(
            event_type=event_type,
            message=message,
            timestamp=time.time(),
            event_id=event_id,
            metadata=metadata,
        )

        # 添加到列表頂部
        list_item = QListWidgetItem(self.event_list)
        list_item.setSizeHint(event_item.sizeHint())
        self.event_list.insertItem(0, list_item)
        self.event_list.setItemWidget(list_item, event_item)

        # 限制最大數量
        while self.event_list.count() > self.max_events:
            self.event_list.takeItem(self.event_list.count() - 1)

        # 連接修復信號
        event_item.fix_clicked.connect(self._on_fix_requested)

    def add_conflict_event(self, rejected_strategy: str, reason: str, metadata: Optional[dict] = None) -> None:
        """添加衝突事件"""
        message = f"策略 {rejected_strategy} 被拒絕: {reason}"
        self.add_event("conflict", message, metadata=metadata)

    def add_risk_event(self, scope: str, action: str, metadata: Optional[dict] = None) -> None:
        """添加風控觸發事件"""
        message = f"風控觸發 [{scope}] 動作: {action}"
        self.add_event("risk", message, metadata=metadata)

    def add_error_event(self, error_message: str, error_id: str = "", metadata: Optional[dict] = None) -> None:
        """添加錯誤事件"""
        self.add_event("error", error_message, event_id=error_id, metadata=metadata)

    def clear_events(self) -> None:
        """清空所有事件"""
        self.event_list.clear()

    def _on_fix_requested(self, event_id: str) -> None:
        """處理修復請求"""
        # TODO: 實現修復邏輯
        print(f"Fix requested for event: {event_id}")
        self.add_event("info", f"嘗試修復事件 {event_id}...")

    def _auto_refresh(self) -> None:
        """自動刷新（由外部提供數據源時覆蓋此方法）"""
        pass

    def set_orchestrator(self, orchestrator) -> None:
        """
        設置 Orchestrator 數據源

        Args:
            orchestrator: LineOrchestrator 實例
        """
        self.orchestrator = orchestrator
        self.last_event_count = 0

        # 覆蓋自動刷新方法
        def refresh_from_orchestrator():
            if not hasattr(self, 'orchestrator'):
                return

            # 獲取最新事件
            events = self.orchestrator.drain_events()

            for event in events:
                # 解析事件類型
                level = event.level.lower()
                message = event.message
                metadata = event.metadata

                # 判斷事件類型
                if "reject" in message.lower() or "conflict" in message.lower():
                    event_type = "conflict"
                elif "risk" in message.lower() or "freeze" in message.lower():
                    event_type = "risk"
                elif level == "error":
                    event_type = "error"
                elif level == "warning":
                    event_type = "warning"
                elif "enter" in message.lower() or "success" in message.lower():
                    event_type = "success"
                else:
                    event_type = "info"

                self.add_event(event_type, message, metadata=metadata)

        self._auto_refresh = refresh_from_orchestrator
