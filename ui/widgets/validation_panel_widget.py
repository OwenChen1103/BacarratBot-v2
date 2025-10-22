# ui/widgets/validation_panel_widget.py
"""策略驗證結果面板 Widget"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QWidget,
)

from src.autobet.strategy_validator import ValidationResult, ValidationLevel


class ValidationPanelWidget(QGroupBox):
    """驗證結果面板"""

    def __init__(self, parent=None):
        super().__init__("🔍 策略驗證", parent)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            ValidationPanelWidget {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                font-weight: bold;
                color: #e5e7eb;
                font-size: 11pt;
            }
            ValidationPanelWidget::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: transparent;
            }
            ValidationPanelWidget QLabel {
                background-color: transparent;
                color: #e5e7eb;
            }
            ValidationPanelWidget QWidget {
                background-color: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 捲動區域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)  # 設置最小高度確保內容可見
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(8)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll)

        # 初始提示
        self.show_placeholder()

    def show_placeholder(self):
        """顯示佔位提示"""
        self.clear_content()

        placeholder = QLabel("💡 修改策略配置後會自動顯示驗證結果")
        placeholder.setStyleSheet("""
            color: #9ca3af;
            font-size: 10pt;
            font-weight: normal;
            padding: 20px;
        """)
        placeholder.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(placeholder)

    def clear_content(self):
        """清空內容"""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def display_result(self, result: ValidationResult):
        """顯示驗證結果"""
        self.clear_content()

        # 總覽
        summary_frame = self._create_summary_frame(result)
        self.content_layout.addWidget(summary_frame)

        # 訊息列表
        if result.messages:
            for msg in result.messages:
                msg_widget = self._create_message_widget(msg)
                self.content_layout.addWidget(msg_widget)

        # 風險評估
        if result.risk_assessment:
            risk_frame = self._create_risk_frame(result.risk_assessment)
            self.content_layout.addWidget(risk_frame)

        self.content_layout.addStretch()

    def _create_summary_frame(self, result: ValidationResult) -> QFrame:
        """建立總覽框"""
        frame = QFrame()

        if result.is_valid:
            # 使用更柔和的深色調，與主題協調
            bg_color = "#1e3a2f" if not result.has_warnings() else "#3a2e1e"
            border_color = "#10b981" if not result.has_warnings() else "#f59e0b"
            icon = "✅" if not result.has_warnings() else "⚠️"
            text = "配置有效" if not result.has_warnings() else "配置有效但有警告"
        else:
            bg_color = "#3a1e1e"
            border_color = "#ef4444"
            icon = "❌"
            text = "配置無效"

        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 6px;
                padding: 12px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(4)

        title = QLabel(f"{icon} {text}")
        title.setStyleSheet("""
            font-weight: bold;
            color: white;
            font-size: 12pt;
        """)

        error_count = len(result.get_messages_by_level(ValidationLevel.ERROR))
        warning_count = len(result.get_messages_by_level(ValidationLevel.WARNING))
        info_count = len(result.get_messages_by_level(ValidationLevel.INFO))

        counts = []
        if error_count > 0:
            counts.append(f"❌ {error_count} 個錯誤")
        if warning_count > 0:
            counts.append(f"⚠️ {warning_count} 個警告")
        if info_count > 0:
            counts.append(f"ℹ️ {info_count} 個建議")

        if counts:
            subtitle = QLabel(" | ".join(counts))
            subtitle.setStyleSheet("""
                color: #e5e7eb;
                font-size: 10pt;
                font-weight: normal;
            """)
            layout.addWidget(title)
            layout.addWidget(subtitle)
        else:
            layout.addWidget(title)

        return frame

    def _create_message_widget(self, msg) -> QFrame:
        """建立訊息卡片"""
        frame = QFrame()

        # 根據等級設定顏色
        if msg.level == ValidationLevel.ERROR:
            border_color = "#dc2626"
            icon = "❌"
            label_color = "#fca5a5"
        elif msg.level == ValidationLevel.WARNING:
            border_color = "#f59e0b"
            icon = "⚠️"
            label_color = "#fcd34d"
        elif msg.level == ValidationLevel.INFO:
            border_color = "#3b82f6"
            icon = "ℹ️"
            label_color = "#93c5fd"
        else:  # SUCCESS
            border_color = "#10b981"
            icon = "✓"
            label_color = "#6ee7b7"

        frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1f2937;
                border-left: 4px solid {border_color};
                border-radius: 4px;
                padding: 10px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # 類別標籤
        category_label = QLabel(f"{icon} {msg.category.upper()}")
        category_label.setStyleSheet(f"""
            color: {label_color};
            font-weight: bold;
            font-size: 9pt;
        """)
        layout.addWidget(category_label)

        # 訊息
        message_label = QLabel(msg.message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("""
            color: #f3f4f6;
            font-size: 10pt;
            font-weight: normal;
        """)
        layout.addWidget(message_label)

        # 建議
        if msg.suggestion:
            suggestion_label = QLabel(f"💡 建議: {msg.suggestion}")
            suggestion_label.setWordWrap(True)
            suggestion_label.setStyleSheet("""
                color: #9ca3af;
                font-size: 9pt;
                font-weight: normal;
                font-style: italic;
                padding-left: 10px;
            """)
            layout.addWidget(suggestion_label)

        return frame

    def _create_risk_frame(self, assessment: dict) -> QFrame:
        """建立風險評估框"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(8)

        # 標題
        title = QLabel("📊 風險評估")
        title.setStyleSheet("""
            font-weight: bold;
            color: #60a5fa;
            font-size: 11pt;
        """)
        layout.addWidget(title)

        # 評估資訊
        risk_level = assessment.get("risk_level", "未知")
        risk_color = {"低": "#10b981", "中": "#f59e0b", "高": "#ef4444"}.get(risk_level, "#6b7280")

        info_text = f"""
        <table style='color: #e5e7eb; font-size: 10pt;'>
        <tr><td><b>風險等級:</b></td><td><span style='color: {risk_color}; font-weight: bold;'>{risk_level}</span></td></tr>
        <tr><td><b>總風險:</b></td><td>{assessment.get('total_risk', 0):,.0f} 元</td></tr>
        <tr><td><b>單手最高:</b></td><td>{assessment.get('max_single_bet', 0):,.0f} 元</td></tr>
        <tr><td><b>平均注碼:</b></td><td>{assessment.get('avg_bet', 0):.0f} 元</td></tr>
        <tr><td><b>層數:</b></td><td>{assessment.get('layer_count', 0)} 層</td></tr>
        <tr><td><b>進層速度:</b></td><td>{assessment.get('progression_speed', '未知')}</td></tr>
        <tr><td><b>風控保護:</b></td><td>{'✓ 已設定' if assessment.get('has_risk_control') else '✗ 未設定'}</td></tr>
        <tr><td><b>去重保護:</b></td><td>{'✓ 已啟用' if assessment.get('dedup_safe') else '✗ 未啟用'}</td></tr>
        </table>
        """

        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: normal;")
        layout.addWidget(info_label)

        return frame
