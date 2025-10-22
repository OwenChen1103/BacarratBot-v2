# ui/dialogs/setup_wizard.py
"""首次設定精靈 - 引導新使用者完成所有配置"""
from __future__ import annotations

from typing import Dict, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QFrame,
    QCheckBox,
)

from src.utils.config_validator import ConfigValidator, ValidationResult


class SetupWizard(QDialog):
    """首次設定精靈對話框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("首次設定精靈")
        self.setMinimumSize(700, 600)
        self.setModal(True)

        self.validator = ConfigValidator()
        self.results: Dict[str, ValidationResult] = {}

        self.setup_ui()
        self.check_status()

    def setup_ui(self):
        """建立 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # 標題
        title = QLabel("🎯 歡迎使用百家樂自動投注系統")
        title.setFont(QFont("Microsoft YaHei UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                color: #f9fafb;
                background-color: #1f2937;
                padding: 20px;
                border-radius: 10px;
            }
        """)
        layout.addWidget(title)

        # 說明文字
        desc = QLabel("首次使用需完成以下 4 個步驟,預計總時間: 15 分鐘")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #d1d5db; font-size: 12pt; padding: 10px;")
        layout.addWidget(desc)

        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 4)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #374151;
                border-radius: 8px;
                text-align: center;
                background-color: #1f2937;
                color: #f3f4f6;
                font-size: 11pt;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 6px;
            }
        """)
        self.progress_bar.setFormat("完成度: %p%")
        layout.addWidget(self.progress_bar)

        # 步驟列表
        self.steps_frame = QFrame()
        self.steps_frame.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 10px;
                padding: 16px;
            }
        """)
        self.steps_layout = QVBoxLayout(self.steps_frame)
        self.steps_layout.setSpacing(16)

        # 步驟 1-4 將動態創建
        self.step_widgets = {}
        self.create_steps()

        layout.addWidget(self.steps_frame, 1)

        # 不再顯示選項
        self.dont_show_again = QCheckBox("不再顯示此精靈 (可在設定中重新啟用)")
        self.dont_show_again.setStyleSheet("color: #9ca3af; font-size: 10pt;")
        layout.addWidget(self.dont_show_again)

        # 按鈕列
        buttons = QHBoxLayout()
        buttons.setSpacing(12)

        self.skip_btn = QPushButton("稍後設定")
        self.skip_btn.setStyleSheet("""
            QPushButton {
                padding: 12px 24px;
                background-color: #1f2937;
                color: #f3f4f6;
                border: none;
                border-radius: 6px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.skip_btn.clicked.connect(self.reject)

        self.close_btn = QPushButton("關閉精靈")
        self.close_btn.setStyleSheet("""
            QPushButton {
                padding: 12px 24px;
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setVisible(False)  # 初始隱藏

        buttons.addWidget(self.skip_btn)
        buttons.addStretch()
        buttons.addWidget(self.close_btn)

        layout.addLayout(buttons)

    def create_steps(self):
        """創建步驟項目"""
        steps = [
            {
                "id": "chip_profile",
                "title": "1️⃣ 籌碼設定與校準",
                "desc": "設定籌碼金額並校準螢幕位置",
                "time": "5 分鐘",
                "page": "chip_setup",
            },
            {
                "id": "positions",
                "title": "2️⃣ 位置與 ROI 校準",
                "desc": "設定可下注判斷區域",
                "time": "3 分鐘",
                "page": "roi_setup",
            },
            {
                "id": "strategy",
                "title": "3️⃣ 建立投注策略",
                "desc": "選擇範本或自訂策略",
                "time": "5 分鐘",
                "page": "strategy_setup",
            },
            {
                "id": "overlay",
                "title": "4️⃣ 檢測模板設定",
                "desc": "設定可下注狀態檢測",
                "time": "2 分鐘",
                "page": "overlay_setup",
            },
        ]

        for step in steps:
            widget = self.create_step_widget(step)
            self.step_widgets[step["id"]] = widget
            self.steps_layout.addWidget(widget)

    def create_step_widget(self, step: Dict[str, Any]) -> QFrame:
        """創建單個步驟 Widget"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 8px;
                padding: 12px;
            }
            QFrame:hover {
                border-color: #4b5563;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setSpacing(12)

        # 狀態圖標
        status_label = QLabel("❌")
        status_label.setObjectName("status")
        status_label.setStyleSheet("font-size: 24pt;")
        status_label.setFixedWidth(40)
        status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(status_label)

        # 資訊區域
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        title_label = QLabel(step["title"])
        title_label.setStyleSheet("color: #f3f4f6; font-size: 12pt; font-weight: bold;")
        info_layout.addWidget(title_label)

        desc_label = QLabel(f"{step['desc']} (預計: {step['time']})")
        desc_label.setStyleSheet("color: #9ca3af; font-size: 10pt;")
        info_layout.addWidget(desc_label)

        layout.addLayout(info_layout, 1)

        # 按鈕
        action_btn = QPushButton("前往設定 →")
        action_btn.setObjectName("action")
        action_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        action_btn.clicked.connect(lambda: self.goto_page(step["page"]))
        layout.addWidget(action_btn)

        # 儲存步驟資訊
        frame.setProperty("step_id", step["id"])
        frame.setProperty("page", step["page"])

        return frame

    def check_status(self):
        """檢查配置狀態"""
        self.results = self.validator.validate_all()

        completed_count = 0

        for step_id, widget in self.step_widgets.items():
            result = self.results.get(step_id)
            if result:
                status_label = widget.findChild(QLabel, "status")
                action_btn = widget.findChild(QPushButton, "action")

                if result.complete:
                    # 已完成
                    status_label.setText("✅")
                    action_btn.setText("已完成 ✓")
                    action_btn.setStyleSheet("""
                        QPushButton {
                            padding: 8px 16px;
                            background-color: #059669;
                            color: white;
                            border: none;
                            border-radius: 6px;
                            font-size: 10pt;
                        }
                    """)
                    action_btn.setEnabled(False)
                    completed_count += 1

                    # 更新 Frame 樣式
                    widget.setStyleSheet("""
                        QFrame {
                            background-color: #064e3b;
                            border: 2px solid #059669;
                            border-radius: 8px;
                            padding: 12px;
                        }
                    """)
                else:
                    # 未完成
                    status_label.setText("⚠️")

        # 更新進度條
        self.progress_bar.setValue(completed_count)

        # 如果全部完成
        if completed_count == 4:
            self.skip_btn.setVisible(False)
            self.close_btn.setVisible(True)
            self.progress_bar.setFormat("已完成: 100%")

    def goto_page(self, page_name: str):
        """前往指定頁面"""
        # 關閉精靈並通知主視窗跳轉
        self.setProperty("target_page", page_name)
        self.accept()

    def should_save_preference(self) -> bool:
        """是否儲存「不再顯示」偏好"""
        return self.dont_show_again.isChecked()

    def get_target_page(self) -> str:
        """取得目標頁面"""
        return self.property("target_page") or ""
