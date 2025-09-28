# ui/pages/page_settings.py
import os
import json
import zipfile
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton,
    QFrame, QGroupBox, QFileDialog, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ..app_state import APP_STATE, emit_toast

class PresetManager(QFrame):
    """方案管理器"""

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
                padding: 16px;
            }
        """)

        layout = QVBoxLayout(self)

        # 標題
        title = QLabel("📦 配置方案管理")
        title.setFont(QFont("Microsoft YaHei UI", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 說明
        desc = QLabel("保存或載入完整的系統配置 (positions + overlay + strategy)")
        desc.setStyleSheet("color: #9ca3af; padding: 8px;")
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        # 按鈕區
        btn_layout = QHBoxLayout()

        self.save_preset_btn = QPushButton("💾 保存方案...")
        self.save_preset_btn.clicked.connect(self.save_preset)
        self.save_preset_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)

        self.load_preset_btn = QPushButton("📂 載入方案...")
        self.load_preset_btn.clicked.connect(self.load_preset)
        self.load_preset_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)

        btn_layout.addWidget(self.save_preset_btn)
        btn_layout.addWidget(self.load_preset_btn)
        layout.addLayout(btn_layout)

        # 當前配置狀態
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(120)
        self.status_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
                color: #e5e5e5;
            }
        """)
        layout.addWidget(self.status_text)

        self.update_status()

    def update_status(self):
        """更新當前配置狀態"""
        status_lines = []

        # 檢查 positions.json
        if os.path.exists("configs/positions.json"):
            try:
                with open("configs/positions.json", "r", encoding="utf-8") as f:
                    pos_data = json.load(f)
                point_count = len(pos_data.get("points", {}))
                status_lines.append(f"✅ Positions: {point_count} points")
            except:
                status_lines.append("❌ Positions: 無法讀取")
        else:
            status_lines.append("❌ Positions: 未找到")

        # 檢查 strategy.json
        if os.path.exists("configs/strategy.json"):
            try:
                with open("configs/strategy.json", "r", encoding="utf-8") as f:
                    strategy_data = json.load(f)
                target = strategy_data.get("target", "?")
                unit = strategy_data.get("unit", 0)
                status_lines.append(f"✅ Strategy: {target}, {unit} unit")
            except:
                status_lines.append("❌ Strategy: 無法讀取")
        else:
            status_lines.append("❌ Strategy: 未找到")

        # 檢查模板
        template_count = 0
        if os.path.exists("templates"):
            template_count = len([f for f in os.listdir("templates") if f.endswith(('.png', '.jpg', '.jpeg'))])
        status_lines.append(f"📁 Templates: {template_count} files")

        self.status_text.setText("\n".join(status_lines))

    def save_preset(self):
        """保存配置方案"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"preset_{timestamp}.zip"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存配置方案",
            default_name,
            "配置方案 (*.zip);;All Files (*)"
        )

        if not file_path:
            return

        try:
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                files_to_include = [
                    "configs/positions.json",
                    "configs/strategy.json"
                ]

                included_files = []
                for file_path_to_zip in files_to_include:
                    if os.path.exists(file_path_to_zip):
                        zf.write(file_path_to_zip, os.path.basename(file_path_to_zip))
                        included_files.append(os.path.basename(file_path_to_zip))

                # 包含模板文件
                if os.path.exists("templates"):
                    for template_file in os.listdir("templates"):
                        if template_file.endswith(('.png', '.jpg', '.jpeg')):
                            template_path = os.path.join("templates", template_file)
                            zf.write(template_path, f"templates/{template_file}")
                            included_files.append(f"templates/{template_file}")

                # 創建manifest
                manifest = {
                    "created": datetime.now().isoformat(),
                    "files": included_files,
                    "version": "1.0"
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            emit_toast(f"Preset saved: {len(included_files)} files", "success")
            QMessageBox.information(self, "成功", f"配置方案已保存\n包含 {len(included_files)} 個文件")

        except Exception as e:
            emit_toast(f"Save failed: {str(e)}", "error")
            QMessageBox.critical(self, "錯誤", f"保存失敗: {str(e)}")

    def load_preset(self):
        """載入配置方案"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "載入配置方案",
            "",
            "配置方案 (*.zip);;All Files (*)"
        )

        if not file_path:
            return

        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # 讀取manifest
                manifest = None
                if "manifest.json" in zf.namelist():
                    manifest_data = zf.read("manifest.json").decode('utf-8')
                    manifest = json.loads(manifest_data)

                # 確保目錄存在
                os.makedirs("configs", exist_ok=True)
                os.makedirs("templates", exist_ok=True)

                loaded_files = []

                # 解壓配置文件
                for file_name in ["positions.json", "strategy.json"]:
                    if file_name in zf.namelist():
                        zf.extract(file_name, "configs/")
                        loaded_files.append(file_name)

                # 解壓模板文件
                for file_info in zf.infolist():
                    if file_info.filename.startswith("templates/"):
                        zf.extract(file_info, ".")
                        loaded_files.append(file_info.filename)

            # 更新狀態
            self.update_status()

            # 發送更新事件
            self.emit_config_update_events()

            emit_toast(f"Preset loaded: {len(loaded_files)} files", "success")
            QMessageBox.information(self, "成功", f"配置方案已載入\n包含 {len(loaded_files)} 個文件")

        except Exception as e:
            emit_toast(f"Load failed: {str(e)}", "error")
            QMessageBox.critical(self, "錯誤", f"載入失敗: {str(e)}")

    def emit_config_update_events(self):
        """發送配置更新事件"""
        # 通知各模組重新載入
        if os.path.exists("configs/positions.json"):
            try:
                with open("configs/positions.json", "r", encoding="utf-8") as f:
                    pos_data = json.load(f)
                APP_STATE.positionsChanged.emit({
                    'complete': len(pos_data.get("points", {})) >= 3,
                    'count': len(pos_data.get("points", {})),
                    'required': ["banker", "chip_1k", "confirm"]
                })
            except:
                pass

        if os.path.exists("configs/strategy.json"):
            APP_STATE.strategyChanged.emit({'complete': True})

class SettingsPage(QWidget):
    """系統設定頁面"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 標題
        header = QLabel("🔧 系統設定")
        header.setFont(QFont("Microsoft YaHei UI", 18, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #374151;
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 8px;
            }
        """)

        # 方案管理器
        self.preset_manager = PresetManager()

        # 其他設定占位符
        other_settings = QLabel("其他設定功能開發中...")
        other_settings.setAlignment(Qt.AlignCenter)
        other_settings.setStyleSheet("""
            QLabel {
                color: #9ca3af;
                background-color: #374151;
                padding: 20px;
                border-radius: 8px;
                border: 2px dashed #6b7280;
            }
        """)

        layout.addWidget(header)
        layout.addWidget(self.preset_manager)
        layout.addWidget(other_settings)
        layout.addStretch()