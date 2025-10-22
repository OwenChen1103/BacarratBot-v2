# ui/widgets/staking_direction_widget.py
"""注碼設定 Widget - 分離方向與金額"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QEvent, QObject
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QRadioButton,
    QLabel,
    QLineEdit,
    QFrame,
    QPushButton,
    QSpinBox,
    QWidget,
)


class WheelEventFilter(QObject):
    """事件過濾器：禁止滾輪改變 SpinBox 的值"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if isinstance(obj, QSpinBox):
                event.ignore()
                return True
        return super().eventFilter(obj, event)


class StakingDirectionWidget(QGroupBox):
    """注碼設定 Widget - 包含方向選擇和金額序列"""

    sequence_changed = Signal(list)  # 當序列改變時發送信號 (含正負號)

    def __init__(self, parent=None):
        super().__init__("💰 注碼設定", parent)
        self.layers = []  # 儲存層級金額
        self.wheel_filter = WheelEventFilter(self)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            StakingDirectionWidget {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                font-weight: bold;
                color: #e5e7eb;
                font-size: 11pt;
            }
            StakingDirectionWidget::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: transparent;
            }
            StakingDirectionWidget QLabel {
                background-color: transparent;
                color: #e5e7eb;
            }
            StakingDirectionWidget QWidget {
                background-color: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 投注方向選擇
        direction_label = QLabel("投注方向:")
        direction_label.setStyleSheet("font-weight: bold; color: #f3f4f6; font-size: 10pt;")
        layout.addWidget(direction_label)

        self.radio_follow = QRadioButton("跟隨 Pattern (條件說押閒就押閒)")
        self.radio_follow.setChecked(True)
        self.radio_follow.setStyleSheet("""
            QRadioButton {
                color: #f3f4f6;
                font-size: 10pt;
                padding: 6px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.radio_follow.toggled.connect(self._on_direction_changed)

        self.radio_reverse = QRadioButton("反向押注 (條件說押閒就押莊)")
        self.radio_reverse.setStyleSheet("""
            QRadioButton {
                color: #f3f4f6;
                font-size: 10pt;
                padding: 6px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.radio_reverse.toggled.connect(self._on_direction_changed)

        layout.addWidget(self.radio_follow)
        layout.addWidget(self.radio_reverse)

        layout.addSpacing(10)

        # 注碼層級設定
        layers_label = QLabel("注碼序列 (金額):")
        layers_label.setStyleSheet("font-weight: bold; color: #f3f4f6; font-size: 10pt;")
        layout.addWidget(layers_label)

        # 層級列表容器
        self.layers_container = QWidget()
        self.layers_layout = QVBoxLayout(self.layers_container)
        self.layers_layout.setContentsMargins(0, 0, 0, 0)
        self.layers_layout.setSpacing(6)
        layout.addWidget(self.layers_container)

        # 新增層級按鈕
        self.btn_add_layer = QPushButton("+ 新增層級")
        self.btn_add_layer.setStyleSheet("""
            QPushButton {
                background-color: #1f2937;
                color: #f3f4f6;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.btn_add_layer.clicked.connect(lambda: self.add_layer(0))
        layout.addWidget(self.btn_add_layer)

        layout.addSpacing(10)

        # 預覽 (先建立 preview_text,再加入預設層級)
        preview_label = QLabel("📊 預覽:")
        preview_label.setStyleSheet("font-weight: bold; color: #60a5fa; font-size: 10pt;")
        layout.addWidget(preview_label)

        self.preview_text = QLabel()
        self.preview_text.setWordWrap(True)
        self.preview_text.setStyleSheet("""
            QLabel {
                color: #d1d5db;
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 10px;
                font-size: 10pt;
            }
        """)
        layout.addWidget(self.preview_text)

        # 預設加入三層 (在 preview_text 建立後)
        self.add_layer(100)
        self.add_layer(200)
        self.add_layer(400)

    def add_layer(self, amount: int):
        """新增一層"""
        layer_widget = QWidget()
        layer_layout = QHBoxLayout(layer_widget)
        layer_layout.setContentsMargins(0, 0, 0, 0)
        layer_layout.setSpacing(8)

        # 層級編號
        layer_num = len(self.layers) + 1
        label = QLabel(f"第 {layer_num} 層:")
        label.setMinimumWidth(60)
        label.setStyleSheet("color: #e5e7eb; font-size: 10pt;")

        # 金額輸入
        spin = QSpinBox()
        spin.setRange(0, 999999)
        spin.setValue(amount)
        spin.setSuffix(" 元")
        spin.setFocusPolicy(Qt.StrongFocus)
        spin.installEventFilter(self.wheel_filter)
        spin.setStyleSheet("""
            QSpinBox {
                background-color: #1f2937;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        spin.valueChanged.connect(self.update_preview)

        # 刪除按鈕
        btn_delete = QPushButton("✕")
        btn_delete.setMaximumWidth(30)
        btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        btn_delete.clicked.connect(lambda: self.remove_layer(layer_widget, spin))

        layer_layout.addWidget(label)
        layer_layout.addWidget(spin, 1)
        layer_layout.addWidget(btn_delete)

        self.layers_layout.addWidget(layer_widget)

        self.layers.append({
            'widget': layer_widget,
            'spin': spin
        })

        self.update_preview()

    def remove_layer(self, widget: QWidget, spin: QSpinBox):
        """移除一層"""
        if len(self.layers) <= 1:
            return  # 至少保留一層

        # 移除 UI
        widget.deleteLater()

        # 移除資料
        self.layers = [layer for layer in self.layers if layer['spin'] != spin]

        # 重新編號
        for i, layer in enumerate(self.layers):
            layout = layer['widget'].layout()
            label = layout.itemAt(0).widget()
            label.setText(f"第 {i+1} 層:")

        self.update_preview()

    def _on_direction_changed(self):
        """當方向改變時更新預覽"""
        self.update_preview()

    def update_preview(self):
        """更新預覽"""
        is_reverse = self.radio_reverse.isChecked()
        direction_text = "反向" if is_reverse else "跟隨"

        preview_lines = [f"<b>投注方向:</b> {direction_text}<br>"]

        for i, layer in enumerate(self.layers):
            amount = layer['spin'].value()
            # 假設 pattern 是 "bet P" (押閒)
            target = "莊家" if is_reverse else "閒家"
            preview_lines.append(f"  第 {i+1} 層: <b>{amount}</b> 元 (<span style='color: #60a5fa;'>{target}</span>)")

        self.preview_text.setText("<br>".join(preview_lines))

        # 發送信號
        sequence = self.get_sequence()
        self.sequence_changed.emit(sequence)

    def get_sequence(self) -> list:
        """取得注碼序列 (含正負號)"""
        is_reverse = self.radio_reverse.isChecked()
        sequence = []

        for layer in self.layers:
            amount = layer['spin'].value()
            if is_reverse:
                sequence.append(-amount)  # 反向用負數
            else:
                sequence.append(amount)

        return sequence

    def set_sequence(self, sequence: list):
        """設定注碼序列 (解析正負號)"""
        if not sequence:
            return

        # 清空現有層級
        for layer in self.layers:
            layer['widget'].deleteLater()
        self.layers.clear()

        # 判斷方向
        if sequence and sequence[0] < 0:
            self.radio_reverse.setChecked(True)
            sequence = [-x for x in sequence]  # 轉為正數顯示
        else:
            self.radio_follow.setChecked(True)
            sequence = [abs(x) for x in sequence]

        # 建立層級
        for amount in sequence:
            self.add_layer(amount)

    def get_sequence_text(self) -> str:
        """取得序列文字 (用於舊版相容)"""
        sequence = [abs(x) for x in self.get_sequence()]
        return ", ".join(str(x) for x in sequence)
