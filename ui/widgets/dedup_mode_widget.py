# ui/widgets/dedup_mode_widget.py
"""去重模式設定 Widget + 視覺化示範"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QRadioButton,
    QLabel,
    QFrame,
    QPushButton,
    QDialog,
    QWidget,
)


class DedupVisualizationCanvas(QWidget):
    """去重視覺化畫布"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "overlap"  # "overlap", "none", "strict"
        self.setMinimumHeight(200)
        self.animation_step = 0
        self.max_steps = 3

    def set_mode(self, mode: str):
        """設定模式: overlap, none, strict"""
        self.mode = mode
        self.animation_step = 0
        self.update()

    def play_animation(self):
        """播放動畫"""
        self.animation_step = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_step)
        self.timer.start(800)  # 每 800ms 一步

    def _next_step(self):
        """動畫下一步"""
        self.animation_step += 1
        self.update()
        if self.animation_step >= self.max_steps:
            self.timer.stop()

    def reset_animation(self):
        """重置動畫"""
        if hasattr(self, 'timer'):
            self.timer.stop()
        self.animation_step = 0
        self.update()

    def paintEvent(self, event):
        """繪製視覺化"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 設定背景
        painter.fillRect(self.rect(), QColor("#374151"))

        # 繪製三張牌: B B B
        card_width = 70
        card_height = 100
        spacing = 15
        start_x = 40
        y = 30

        cards = ['莊', '莊', '莊']
        for i, card in enumerate(cards):
            x = start_x + i * (card_width + spacing)

            # 繪製卡片背景
            painter.setBrush(QBrush(QColor("#fef3c7")))
            painter.setPen(QPen(QColor("#f59e0b"), 2))
            painter.drawRoundedRect(x, y, card_width, card_height, 6, 6)

            # 繪製文字
            painter.setPen(QPen(QColor("#92400e")))
            painter.setFont(QFont("Arial", 18, QFont.Bold))
            painter.drawText(x, y, card_width, card_height, Qt.AlignCenter, card)

            # 繪製序號
            painter.setFont(QFont("Arial", 10))
            painter.setPen(QPen(QColor("#6b7280")))
            painter.drawText(x, y + card_height + 15, card_width, 20, Qt.AlignCenter, f"第{i+1}局")

        # 繪製訊號指示
        signal_y = y + card_height + 45

        # 訊號 1: 1-2 (BB)
        if self.animation_step >= 1:
            self._draw_signal(painter, start_x, signal_y, card_width, spacing, 0, 1, "訊號1", QColor("#10b981"), True)

        # 訊號 2: 2-3 (BB)
        if self.animation_step >= 2:
            if self.mode == "none":
                # 不去重 - 兩個訊號都有效
                self._draw_signal(painter, start_x, signal_y + 35, card_width, spacing, 1, 2, "訊號2", QColor("#ef4444"), True)
            elif self.mode == "overlap":
                # 重疊去重 - 訊號2被去重
                self._draw_signal(painter, start_x, signal_y + 35, card_width, spacing, 1, 2, "訊號2", QColor("#6b7280"), False)
            else:  # strict
                # 嚴格去重 - 訊號2被去重
                self._draw_signal(painter, start_x, signal_y + 35, card_width, spacing, 1, 2, "訊號2", QColor("#6b7280"), False)

        # 繪製結果說明
        if self.animation_step >= 3:
            result_y = signal_y + 80
            painter.setFont(QFont("Arial", 11, QFont.Bold))

            if self.mode == "overlap":
                painter.setPen(QPen(QColor("#10b981")))
                text = "✅ 第 3 局下注 1 次 (訊號1有效,訊號2去重)"
            elif self.mode == "none":
                painter.setPen(QPen(QColor("#ef4444")))
                text = "⚠️ 第 3 局下注 2 次 (兩個訊號都有效!)"
            else:  # strict
                painter.setPen(QPen(QColor("#3b82f6")))
                text = "✅ 第 3 局下注 1 次 (僅訊號1有效)"

            painter.drawText(start_x, result_y, text)

    def _draw_signal(self, painter, start_x, y, card_width, spacing, from_idx, to_idx, label, color, is_active):
        """繪製訊號連線"""
        x1 = start_x + from_idx * (card_width + spacing) + card_width // 2
        x2 = start_x + to_idx * (card_width + spacing) + card_width // 2

        # 繪製連線
        pen_width = 4 if is_active else 2
        pen_style = Qt.SolidLine if is_active else Qt.DashLine
        pen = QPen(color, pen_width, pen_style)
        painter.setPen(pen)
        painter.drawLine(x1, y, x2, y)

        # 繪製箭頭 (指向第3局)
        if is_active:
            arrow_size = 8
            painter.setBrush(QBrush(color))
            # 簡化箭頭
            painter.drawEllipse(x2 - arrow_size//2, y - arrow_size//2, arrow_size, arrow_size)

        # 繪製標籤
        painter.setFont(QFont("Arial", 9, QFont.Bold if is_active else QFont.Normal))
        label_x = (x1 + x2) // 2 - 20
        painter.drawText(label_x, y - 8, label)


class DedupAnimationDialog(QDialog):
    """去重模式動畫示範對話框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("去重模式視覺化示範")
        self.setMinimumSize(500, 450)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 標題
        title = QLabel("📊 去重模式視覺化示範")
        title.setStyleSheet("""
            QLabel {
                font-size: 16pt;
                font-weight: bold;
                color: #f9fafb;
                background-color: #1f2937;
                padding: 12px;
                border-radius: 6px;
            }
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 模式選擇
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("選擇模式:"))

        self.mode_combo_buttons = QHBoxLayout()
        self.btn_overlap = QPushButton("重疊去重")
        self.btn_none = QPushButton("不去重")
        self.btn_strict = QPushButton("嚴格去重")

        self.btn_overlap.setCheckable(True)
        self.btn_none.setCheckable(True)
        self.btn_strict.setCheckable(True)
        self.btn_overlap.setChecked(True)

        for btn in [self.btn_overlap, self.btn_none, self.btn_strict]:
            btn.setStyleSheet("""
                QPushButton {
                    padding: 8px 16px;
                    border-radius: 4px;
                    background-color: #1f2937;
                    color: #d1d5db;
                    border: none;
                }
                QPushButton:checked {
                    background-color: #2563eb;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #4b5563;
                }
            """)
            self.mode_combo_buttons.addWidget(btn)

        self.btn_overlap.clicked.connect(lambda: self.select_mode("overlap"))
        self.btn_none.clicked.connect(lambda: self.select_mode("none"))
        self.btn_strict.clicked.connect(lambda: self.select_mode("strict"))

        mode_layout.addLayout(self.mode_combo_buttons)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # 動畫畫布
        canvas_frame = QFrame()
        canvas_frame.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 8px;
            }
        """)
        canvas_layout = QVBoxLayout(canvas_frame)
        self.canvas = DedupVisualizationCanvas()
        canvas_layout.addWidget(self.canvas)
        layout.addWidget(canvas_frame)

        # 說明文字
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        self.explanation.setStyleSheet("""
            QLabel {
                background-color: #1f2937;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 12px;
                font-size: 10pt;
            }
        """)
        layout.addWidget(self.explanation)

        # 播放按鈕
        controls = QHBoxLayout()
        self.btn_play = QPushButton("▶ 播放動畫")
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_play.clicked.connect(self.play_animation)

        self.btn_reset = QPushButton("🔄 重置")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #1f2937;
                color: #f3f4f6;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.btn_reset.clicked.connect(self.reset_animation)

        btn_close = QPushButton("關閉")
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #1f2937;
                color: #f3f4f6;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        btn_close.clicked.connect(self.accept)

        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_reset)
        controls.addStretch()
        controls.addWidget(btn_close)

        layout.addLayout(controls)

        # 初始化說明
        self.update_explanation()

    def select_mode(self, mode):
        """選擇模式"""
        # 更新按鈕狀態
        self.btn_overlap.setChecked(mode == "overlap")
        self.btn_none.setChecked(mode == "none")
        self.btn_strict.setChecked(mode == "strict")

        # 更新畫布
        self.canvas.set_mode(mode)
        self.update_explanation()

    def update_explanation(self):
        """更新說明文字"""
        mode = self.canvas.mode

        explanations = {
            "overlap": (
                "<b>🟢 重疊去重模式 (推薦)</b><br><br>"
                "序列: <b>莊 → 莊 → 莊</b> (三莊)<br>"
                "檢測: 發現 <span style='color: #10b981;'>訊號1 (1-2局)</span> 和 <span style='color: #6b7280;'>訊號2 (2-3局)</span><br>"
                "處理: <span style='color: #10b981;'>去重,僅觸發一次</span><br>"
                "結果: 第 3 局下注 <b>1 次</b><br><br>"
                "適合: 避免同一趨勢重複下注"
            ),
            "none": (
                "<b>🔴 不去重模式</b><br><br>"
                "序列: <b>莊 → 莊 → 莊</b> (三莊)<br>"
                "檢測: 發現 <span style='color: #10b981;'>訊號1 (1-2局)</span> 和 <span style='color: #ef4444;'>訊號2 (2-3局)</span><br>"
                "處理: <span style='color: #ef4444;'>不去重,全部觸發</span><br>"
                "結果: 第 3 局下注 <b>2 次</b> (風險加倍!)<br><br>"
                "適合: 訊號強度疊加策略 (高風險)"
            ),
            "strict": (
                "<b>🔵 嚴格去重模式</b><br><br>"
                "序列: <b>莊 → 莊 → 莊</b> (三莊)<br>"
                "檢測: 發現 <span style='color: #10b981;'>訊號1 (1-2局)</span> 和 <span style='color: #6b7280;'>訊號2 (2-3局)</span><br>"
                "處理: <span style='color: #3b82f6;'>嚴格去重,僅首次觸發</span><br>"
                "結果: 第 3 局下注 <b>1 次</b> (僅訊號1有效)<br><br>"
                "適合: 保守進場"
            ),
        }

        self.explanation.setText(explanations.get(mode, ""))

    def play_animation(self):
        """播放動畫"""
        self.canvas.play_animation()

    def reset_animation(self):
        """重置動畫"""
        self.canvas.reset_animation()


class DedupModeWidget(QGroupBox):
    """去重模式設定 Widget"""

    value_changed = Signal(str)  # 當值改變時發送信號

    def __init__(self, parent=None):
        super().__init__("🔁 訊號去重設定", parent)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            DedupModeWidget {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                font-weight: bold;
                color: #e5e7eb;
                font-size: 11pt;
            }
            DedupModeWidget::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: transparent;
            }
            DedupModeWidget QLabel {
                background-color: transparent;
                color: #e5e7eb;
            }
            DedupModeWidget QWidget {
                background-color: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 情境說明
        scenario = QLabel("情境: 條件是「<b>BB</b>」(兩莊),實際開出: <b>莊→莊→莊</b>")
        scenario.setStyleSheet("color: #e5e7eb; font-size: 10pt; font-weight: bold;")
        layout.addWidget(scenario)

        explanation = QLabel(
            "這會產生兩個「BB」訊號:<br>"
            "  • 第 1-2 局 (莊莊)<br>"
            "  • 第 2-3 局 (莊莊) ← 重疊!"
        )
        explanation.setStyleSheet("color: #9ca3af; font-size: 10pt; font-weight: normal; padding-left: 10px;")
        layout.addWidget(explanation)

        layout.addSpacing(10)

        # 選項 1: 重疊去重 (推薦)
        self.radio_overlap = QRadioButton("重疊去重 (推薦)")
        self.radio_overlap.setChecked(True)
        self.radio_overlap.setStyleSheet("""
            QRadioButton {
                color: #f3f4f6;
                font-size: 11pt;
                padding: 6px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.radio_overlap.toggled.connect(self._on_radio_changed)

        overlap_desc = QLabel(
            "└─ 第 3 局只下注一次<br>"
            "└─ 適合: 避免同一趨勢重複下注"
        )
        overlap_desc.setStyleSheet("color: #9ca3af; font-size: 10pt; padding-left: 30px; font-weight: normal;")

        layout.addWidget(self.radio_overlap)
        layout.addWidget(overlap_desc)

        layout.addSpacing(8)

        # 選項 2: 不去重
        self.radio_none = QRadioButton("不去重")
        self.radio_none.setStyleSheet("""
            QRadioButton {
                color: #f3f4f6;
                font-size: 11pt;
                padding: 6px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.radio_none.toggled.connect(self._on_radio_changed)

        none_desc = QLabel(
            "└─ 第 3 局下注兩次 (風險高)<br>"
            "└─ 適合: 訊號強度疊加策略"
        )
        none_desc.setStyleSheet("color: #9ca3af; font-size: 10pt; padding-left: 30px; font-weight: normal;")

        layout.addWidget(self.radio_none)
        layout.addWidget(none_desc)

        layout.addSpacing(8)

        # 選項 3: 嚴格去重
        self.radio_strict = QRadioButton("嚴格去重")
        self.radio_strict.setStyleSheet("""
            QRadioButton {
                color: #f3f4f6;
                font-size: 11pt;
                padding: 6px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.radio_strict.toggled.connect(self._on_radio_changed)

        strict_desc = QLabel(
            "└─ 訊號必須完全不重疊<br>"
            "└─ 適合: 保守進場"
        )
        strict_desc.setStyleSheet("color: #9ca3af; font-size: 10pt; padding-left: 30px; font-weight: normal;")

        layout.addWidget(self.radio_strict)
        layout.addWidget(strict_desc)

        layout.addSpacing(12)

        # 動畫示範按鈕
        self.btn_demo = QPushButton("▶ 播放視覺化示範")
        self.btn_demo.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_demo.clicked.connect(self.show_animation_demo)
        layout.addWidget(self.btn_demo)

    def _on_radio_changed(self):
        """當單選按鈕改變時發送信號"""
        self.value_changed.emit(self.get_value())

    def show_animation_demo(self):
        """顯示動畫示範對話框"""
        dialog = DedupAnimationDialog(self)
        # 設定為當前選擇的模式
        current_mode = self.get_value()
        mode_map = {
            "overlap_dedup": "overlap",
            "none": "none",
            "strict_dedup": "strict"
        }
        dialog.canvas.set_mode(mode_map.get(current_mode, "overlap"))
        dialog.update_explanation()
        dialog.exec_()

    def get_value(self) -> str:
        """轉換為技術值"""
        if self.radio_overlap.isChecked():
            return "overlap_dedup"
        elif self.radio_strict.isChecked():
            return "strict_dedup"
        else:
            return "none"

    def set_value(self, value: str):
        """從技術值設定"""
        if value == "overlap_dedup":
            self.radio_overlap.setChecked(True)
        elif value == "strict_dedup":
            self.radio_strict.setChecked(True)
        else:
            self.radio_none.setChecked(True)
