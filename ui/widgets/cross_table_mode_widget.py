# ui/widgets/cross_table_mode_widget.py
"""跨桌模式選擇與視覺化說明 Widget"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QRadioButton,
    QLabel,
    QPushButton,
    QGroupBox,
    QDialog,
    QButtonGroup,
)

from src.autobet.lines.config import CrossTableMode


class CrossTableVisualizationCanvas(QWidget):
    """跨桌模式視覺化畫布"""

    def __init__(self, mode: CrossTableMode, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setMinimumHeight(200)
        self.setMinimumWidth(500)

    def set_mode(self, mode: CrossTableMode):
        self.mode = mode
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景
        painter.fillRect(self.rect(), QColor("#374151"))

        if self.mode == CrossTableMode.RESET:
            self._draw_reset_mode(painter)
        else:
            self._draw_accumulate_mode(painter)

    def _draw_reset_mode(self, painter):
        """繪製 RESET 模式說明"""
        # 標題
        painter.setPen(QColor("#60a5fa"))
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        painter.drawText(10, 20, "RESET 模式 - 每桌獨立層數")

        # 說明文字
        painter.setPen(QColor("#9ca3af"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(10, 40, "每張桌子維持各自的注碼層數,互不影響")

        # 繪製三張桌子
        y_start = 60
        table_width = 140
        spacing = 20

        for i, (table_name, sequence) in enumerate([
            ("桌 A", ["L1", "L2", "L1", "L1"]),
            ("桌 B", ["L1", "L1", "L1", "L2"]),
            ("桌 C", ["L1", "L2", "L3", "L2"]),
        ]):
            x = 10 + i * (table_width + spacing)

            # 桌子標題
            painter.setPen(QColor("#f3f4f6"))
            painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
            painter.drawText(x, y_start, table_name)

            # 繪製序列
            for j, layer in enumerate(sequence):
                box_x = x + j * 30
                box_y = y_start + 10

                # 層級框
                if layer == "L1":
                    color = QColor("#10b981")
                elif layer == "L2":
                    color = QColor("#f59e0b")
                else:
                    color = QColor("#ef4444")

                painter.setPen(QPen(color, 2))
                painter.setBrush(color.darker(300))
                painter.drawRect(box_x, box_y, 25, 25)

                # 層級文字
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.drawText(box_x, box_y, 25, 25, Qt.AlignCenter, layer)

            # 箭頭
            painter.setPen(QPen(QColor("#6b7280"), 2))
            for j in range(len(sequence) - 1):
                arrow_x = x + j * 30 + 25
                arrow_y = y_start + 22
                painter.drawLine(arrow_x, arrow_y, arrow_x + 5, arrow_y)

        # 結論
        painter.setPen(QColor("#6ee7b7"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(10, y_start + 70, "✓ 優點: 風險分散,每桌獨立控管")
        painter.drawText(10, y_start + 90, "✓ 適用: 保守型策略,多桌同時運行")

    def _draw_accumulate_mode(self, painter):
        """繪製 ACCUMULATE 模式說明"""
        # 標題
        painter.setPen(QColor("#f59e0b"))
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        painter.drawText(10, 20, "ACCUMULATE 模式 - 跨桌累進層數")

        # 說明文字
        painter.setPen(QColor("#9ca3af"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(10, 40, "所有桌子共享同一個注碼層數,持續累進")

        # 繪製共享層數進程
        y_start = 60

        # 全局層數指示器
        painter.setPen(QColor("#f3f4f6"))
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        painter.drawText(10, y_start, "全局層數進程:")

        # 繪製層數進程
        layers = ["L1", "L2", "L3", "L4", "L5"]
        for i, layer in enumerate(layers):
            box_x = 10 + i * 40
            box_y = y_start + 10

            # 層級框
            if i < 2:
                color = QColor("#10b981")  # 已完成
            elif i == 2:
                color = QColor("#f59e0b")  # 當前
            else:
                color = QColor("#374151")  # 未達到

            painter.setPen(QPen(color, 2))
            painter.setBrush(color.darker(200) if i < 3 else color)
            painter.drawRect(box_x, box_y, 35, 35)

            # 層級文字
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            painter.drawText(box_x, box_y, 35, 35, Qt.AlignCenter, layer)

            # 箭頭
            if i < len(layers) - 1:
                painter.setPen(QPen(QColor("#6b7280"), 2))
                painter.drawLine(box_x + 35, box_y + 17, box_x + 40, box_y + 17)

        # 當前指示
        painter.setPen(QColor("#fcd34d"))
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        painter.drawText(80, y_start + 55, "← 當前層級")

        # 事件序列
        painter.setPen(QColor("#f3f4f6"))
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        painter.drawText(10, y_start + 80, "事件序列:")

        events = [
            ("桌 A 輸", "L1 → L2", QColor("#ef4444")),
            ("桌 B 輸", "L2 → L3", QColor("#ef4444")),
            ("桌 A 贏", "停留 L3", QColor("#10b981")),
        ]

        for i, (event, result, color) in enumerate(events):
            y = y_start + 100 + i * 20
            painter.setPen(color)
            painter.drawText(10, y, f"{i+1}. {event} → {result}")

        # 結論
        painter.setPen(QColor("#fcd34d"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(10, y_start + 170, "⚠ 注意: 風險集中,層數快速累進")
        painter.drawText(250, y_start + 170, "✓ 適用: 激進型策略,快速回本")


class CrossTableModeDialog(QDialog):
    """跨桌模式詳細說明對話框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("跨桌模式說明")
        self.setMinimumSize(600, 500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # 標題
        title = QLabel("🔄 跨桌層數模式詳細說明")
        title.setStyleSheet("""
            font-size: 14pt;
            font-weight: bold;
            color: #f3f4f6;
            padding: 10px;
            background-color: #1f2937;
            border-radius: 6px;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 模式切換
        mode_group = QHBoxLayout()
        self.reset_radio = QRadioButton("RESET - 每桌獨立")
        self.accumulate_radio = QRadioButton("ACCUMULATE - 跨桌累進")

        self.mode_button_group = QButtonGroup()
        self.mode_button_group.addButton(self.reset_radio)
        self.mode_button_group.addButton(self.accumulate_radio)

        for btn in [self.reset_radio, self.accumulate_radio]:
            btn.setStyleSheet("""
                QRadioButton {
                    font-size: 11pt;
                    font-weight: bold;
                    color: #f3f4f6;
                    padding: 8px;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                }
            """)

        self.reset_radio.setChecked(True)
        mode_group.addWidget(self.reset_radio)
        mode_group.addWidget(self.accumulate_radio)
        mode_group.addStretch()
        layout.addLayout(mode_group)

        # 視覺化畫布
        self.canvas = CrossTableVisualizationCanvas(CrossTableMode.RESET)
        layout.addWidget(self.canvas)

        # 詳細說明
        detail_text = QLabel()
        detail_text.setWordWrap(True)
        detail_text.setStyleSheet("""
            color: #e5e7eb;
            font-size: 10pt;
            padding: 15px;
            background-color: #1f2937;
            border-radius: 6px;
            line-height: 1.6;
        """)
        self.detail_label = detail_text
        self._update_detail_text(CrossTableMode.RESET)
        layout.addWidget(detail_text)

        # 關閉按鈕
        close_btn = QPushButton("關閉")
        close_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 30px;
                background-color: #2563eb;
                color: white;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        # 連接信號
        self.reset_radio.toggled.connect(self._on_mode_changed)

    def _on_mode_changed(self):
        mode = CrossTableMode.RESET if self.reset_radio.isChecked() else CrossTableMode.ACCUMULATE
        self.canvas.set_mode(mode)
        self._update_detail_text(mode)

    def _update_detail_text(self, mode: CrossTableMode):
        if mode == CrossTableMode.RESET:
            text = """
<b>RESET 模式 - 每桌獨立層數</b><br><br>
<b>運作原理:</b><br>
• 每張桌子維護各自的注碼層數<br>
• 桌 A 的輸贏只影響桌 A 的層數<br>
• 桌 B 的輸贏只影響桌 B 的層數<br><br>
<b>適用場景:</b><br>
• 同時監控多張桌子<br>
• 希望分散風險,避免單一失控<br>
• 保守型馬丁策略<br><br>
<b>範例:</b><br>
桌 A: L1(輸) → L2(輸) → L3(贏) → L1<br>
桌 B: L1(贏) → L1(贏) → L1(輸) → L2<br>
兩者互不影響
            """
        else:
            text = """
<b>ACCUMULATE 模式 - 跨桌累進層數</b><br><br>
<b>運作原理:</b><br>
• 所有桌子共享同一個全局層數<br>
• 任何一張桌子輸,全局層數都會累進<br>
• 任何一張桌子贏,全局層數重置(依設定)<br><br>
<b>適用場景:</b><br>
• 激進型馬丁策略<br>
• 希望快速回本<br>
• 相信短期內必定有桌會贏<br><br>
<b>範例:</b><br>
全局: L1 → 桌A輸 → L2 → 桌B輸 → L3 → 桌C贏 → L1<br><br>
<b style='color: #fcd34d;'>⚠ 警告:</b> 風險極高,層數累進極快,需謹慎使用!
            """

        self.detail_label.setText(text)


class CrossTableModeWidget(QGroupBox):
    """跨桌模式選擇 Widget (整合到策略頁面)"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__("跨桌層數模式", parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 單選按鈕組
        self.reset_radio = QRadioButton("🔄 RESET - 每桌獨立層數")
        self.accumulate_radio = QRadioButton("📈 ACCUMULATE - 跨桌累進層數")

        self.mode_button_group = QButtonGroup()
        self.mode_button_group.addButton(self.reset_radio)
        self.mode_button_group.addButton(self.accumulate_radio)

        for btn in [self.reset_radio, self.accumulate_radio]:
            btn.setStyleSheet("""
                QRadioButton {
                    font-size: 10pt;
                    color: #f3f4f6;
                    padding: 6px;
                }
                QRadioButton::indicator {
                    width: 16px;
                    height: 16px;
                }
            """)

        self.reset_radio.setChecked(True)
        layout.addWidget(self.reset_radio)
        layout.addWidget(self.accumulate_radio)

        # 簡短說明
        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("""
            color: #9ca3af;
            font-size: 9pt;
            padding: 8px;
            background-color: #1f2937;
            border-radius: 4px;
        """)
        self._update_hint()
        layout.addWidget(self.hint_label)

        # 詳細說明按鈕
        detail_btn = QPushButton("📖 查看詳細說明與視覺化")
        detail_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 12px;
                background-color: #1f2937;
                color: #60a5fa;
                border-radius: 6px;
                font-weight: bold;
                border: 1px solid #4b5563;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        detail_btn.clicked.connect(self._show_detail_dialog)
        layout.addWidget(detail_btn)

        # 連接信號
        self.reset_radio.toggled.connect(self._on_mode_changed)

    def _on_mode_changed(self):
        self._update_hint()
        self.value_changed.emit()

    def _update_hint(self):
        if self.reset_radio.isChecked():
            text = "✓ 每張桌子獨立管理層數,風險分散 (推薦)"
        else:
            text = "⚠ 所有桌子共享層數,累進快速,風險較高"

        self.hint_label.setText(text)

    def _show_detail_dialog(self):
        dialog = CrossTableModeDialog(self)
        # 設定對話框初始模式
        if self.accumulate_radio.isChecked():
            dialog.accumulate_radio.setChecked(True)
        dialog.exec()

    def get_value(self) -> str:
        """取得當前選擇的模式"""
        return CrossTableMode.RESET.value if self.reset_radio.isChecked() else CrossTableMode.ACCUMULATE.value

    def set_value(self, value: str):
        """設定模式"""
        if value == CrossTableMode.ACCUMULATE.value:
            self.accumulate_radio.setChecked(True)
        else:
            self.reset_radio.setChecked(True)
