# ui/pages/page_settings.py
import os
import json
import zipfile
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton,
    QFrame, QGroupBox, QFileDialog, QMessageBox, QTextEdit,
    QSpinBox, QFormLayout
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
        title = QLabel("配置方案管理")
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

        self.save_preset_btn = QPushButton("保存方案...")
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

        self.load_preset_btn = QPushButton("載入方案...")
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
                status_lines.append(f"√ Positions: {point_count} points")
            except:
                status_lines.append("× Positions: 無法讀取")
        else:
            status_lines.append("× Positions: 未找到")

        # 檢查線路策略 (新系統)
        strategy_dir = "configs/line_strategies"
        if os.path.exists(strategy_dir):
            try:
                strategy_files = [f for f in os.listdir(strategy_dir) if f.endswith('.json')]
                if strategy_files:
                    status_lines.append(f"√ Strategy: {len(strategy_files)} 個策略")
                else:
                    status_lines.append("× Strategy: 沒有策略")
            except:
                status_lines.append("× Strategy: 無法讀取")
        else:
            status_lines.append("× Strategy: 未找到目錄")

        # 檢查模板
        template_count = 0
        if os.path.exists("templates"):
            template_count = len([f for f in os.listdir("templates") if f.endswith(('.png', '.jpg', '.jpeg'))])
        status_lines.append(f"▫ Templates: {template_count} files")

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
                # 包含基本配置
                files_to_include = [
                    "configs/positions.json"
                ]

                # 包含所有線路策略
                strategy_dir = "configs/line_strategies"
                if os.path.exists(strategy_dir):
                    for f in os.listdir(strategy_dir):
                        if f.endswith('.json'):
                            files_to_include.append(os.path.join(strategy_dir, f))

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
                if "positions.json" in zf.namelist():
                    zf.extract("positions.json", "configs/")
                    loaded_files.append("positions.json")

                # 解壓線路策略
                os.makedirs("configs/line_strategies", exist_ok=True)
                for file_info in zf.infolist():
                    if file_info.filename.startswith("line_strategies/") and file_info.filename.endswith('.json'):
                        target_path = os.path.join("configs", file_info.filename)
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zf.open(file_info) as source, open(target_path, 'wb') as target:
                            target.write(source.read())
                        loaded_files.append(file_info.filename)

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

        # 檢查線路策略
        strategy_dir = "configs/line_strategies"
        if os.path.exists(strategy_dir):
            strategy_files = [f for f in os.listdir(strategy_dir) if f.endswith('.json')]
            if strategy_files:
                APP_STATE.strategyChanged.emit({'complete': True, 'count': len(strategy_files)})

class ClickDelaySettings(QGroupBox):
    """點擊延遲設定"""

    def __init__(self):
        super().__init__("點擊延遲設定")
        self.config_path = "configs/ui_config.json"
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        self.setStyleSheet("""
            QGroupBox {
                background-color: #374151;
                border: 2px solid #4b5563;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 18px;
                font-weight: bold;
                color: #e5e7eb;
                font-size: 11pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
            }
            QLabel {
                color: #d1d5db;
            }
            QSpinBox {
                background-color: #1f2937;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 6px;
                color: #e5e7eb;
                min-width: 80px;
            }
            QSpinBox:focus {
                border-color: #3b82f6;
            }
        """)

        layout = QVBoxLayout(self)

        # 說明
        desc = QLabel("調整滑鼠移動速度和點擊間隔，避免遊戲畫面反應不及（僅影響真實模式）")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #9ca3af; padding: 8px; font-weight: normal; font-size: 9pt;")
        layout.addWidget(desc)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        # 滑鼠移動延遲
        move_layout = QHBoxLayout()
        self.move_min_spin = QSpinBox()
        self.move_min_spin.setRange(50, 2000)
        self.move_min_spin.setSuffix(" ms")
        self.move_max_spin = QSpinBox()
        self.move_max_spin.setRange(50, 2000)
        self.move_max_spin.setSuffix(" ms")
        move_layout.addWidget(QLabel("最小:"))
        move_layout.addWidget(self.move_min_spin)
        move_layout.addWidget(QLabel("最大:"))
        move_layout.addWidget(self.move_max_spin)
        move_layout.addStretch()
        form_layout.addRow("滑鼠移動時間:", move_layout)

        # 點擊後延遲
        click_layout = QHBoxLayout()
        self.click_min_spin = QSpinBox()
        self.click_min_spin.setRange(50, 2000)
        self.click_min_spin.setSuffix(" ms")
        self.click_max_spin = QSpinBox()
        self.click_max_spin.setRange(50, 2000)
        self.click_max_spin.setSuffix(" ms")
        click_layout.addWidget(QLabel("最小:"))
        click_layout.addWidget(self.click_min_spin)
        click_layout.addWidget(QLabel("最大:"))
        click_layout.addWidget(self.click_max_spin)
        click_layout.addStretch()
        form_layout.addRow("點擊後等待:", click_layout)

        # 籌碼之間延遲
        chip_layout = QHBoxLayout()
        self.chip_min_spin = QSpinBox()
        self.chip_min_spin.setRange(100, 3000)
        self.chip_min_spin.setSuffix(" ms")
        self.chip_max_spin = QSpinBox()
        self.chip_max_spin.setRange(100, 3000)
        self.chip_max_spin.setSuffix(" ms")
        chip_layout.addWidget(QLabel("最小:"))
        chip_layout.addWidget(self.chip_min_spin)
        chip_layout.addWidget(QLabel("最大:"))
        chip_layout.addWidget(self.chip_max_spin)
        chip_layout.addStretch()
        form_layout.addRow("籌碼間延遲:", chip_layout)

        # 下注按鈕後延遲
        bet_layout = QHBoxLayout()
        self.bet_min_spin = QSpinBox()
        self.bet_min_spin.setRange(200, 3000)
        self.bet_min_spin.setSuffix(" ms")
        self.bet_max_spin = QSpinBox()
        self.bet_max_spin.setRange(200, 3000)
        self.bet_max_spin.setSuffix(" ms")
        bet_layout.addWidget(QLabel("最小:"))
        bet_layout.addWidget(self.bet_min_spin)
        bet_layout.addWidget(QLabel("最大:"))
        bet_layout.addWidget(self.bet_max_spin)
        bet_layout.addStretch()
        form_layout.addRow("下注按鈕後:", bet_layout)

        # 確認按鈕後延遲
        confirm_layout = QHBoxLayout()
        self.confirm_min_spin = QSpinBox()
        self.confirm_min_spin.setRange(100, 2000)
        self.confirm_min_spin.setSuffix(" ms")
        self.confirm_max_spin = QSpinBox()
        self.confirm_max_spin.setRange(100, 2000)
        self.confirm_max_spin.setSuffix(" ms")
        confirm_layout.addWidget(QLabel("最小:"))
        confirm_layout.addWidget(self.confirm_min_spin)
        confirm_layout.addWidget(QLabel("最大:"))
        confirm_layout.addWidget(self.confirm_max_spin)
        confirm_layout.addStretch()
        form_layout.addRow("確認按鈕後:", confirm_layout)

        layout.addLayout(form_layout)

        # 按鈕
        btn_layout = QHBoxLayout()

        self.save_btn = QPushButton("保存設定")
        self.save_btn.clicked.connect(self.save_config)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)

        self.reset_btn = QPushButton("重置預設值")
        self.reset_btn.clicked.connect(self.reset_defaults)
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #6b7280;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)

        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def load_config(self):
        """載入配置"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    click_cfg = config.get("click", {})

                    move_delay = click_cfg.get("move_delay_ms", [300, 600])
                    self.move_min_spin.setValue(move_delay[0])
                    self.move_max_spin.setValue(move_delay[1])

                    click_delay = click_cfg.get("click_delay_ms", [200, 400])
                    self.click_min_spin.setValue(click_delay[0])
                    self.click_max_spin.setValue(click_delay[1])

                    chip_delay = click_cfg.get("between_chip_delay_ms", [400, 700])
                    self.chip_min_spin.setValue(chip_delay[0])
                    self.chip_max_spin.setValue(chip_delay[1])

                    bet_delay = click_cfg.get("after_bet_button_delay_ms", [500, 800])
                    self.bet_min_spin.setValue(bet_delay[0])
                    self.bet_max_spin.setValue(bet_delay[1])

                    confirm_delay = click_cfg.get("after_confirm_delay_ms", [300, 500])
                    self.confirm_min_spin.setValue(confirm_delay[0])
                    self.confirm_max_spin.setValue(confirm_delay[1])
            else:
                self.reset_defaults()
        except Exception as e:
            emit_toast(f"載入配置失敗: {str(e)}", "error")

    def save_config(self):
        """保存配置"""
        try:
            # 驗證最小值 <= 最大值
            if self.move_min_spin.value() > self.move_max_spin.value():
                QMessageBox.warning(self, "驗證錯誤", "滑鼠移動時間的最小值不能大於最大值")
                return
            if self.click_min_spin.value() > self.click_max_spin.value():
                QMessageBox.warning(self, "驗證錯誤", "點擊後等待的最小值不能大於最大值")
                return
            if self.chip_min_spin.value() > self.chip_max_spin.value():
                QMessageBox.warning(self, "驗證錯誤", "籌碼間延遲的最小值不能大於最大值")
                return
            if self.bet_min_spin.value() > self.bet_max_spin.value():
                QMessageBox.warning(self, "驗證錯誤", "下注按鈕後延遲的最小值不能大於最大值")
                return
            if self.confirm_min_spin.value() > self.confirm_max_spin.value():
                QMessageBox.warning(self, "驗證錯誤", "確認按鈕後延遲的最小值不能大於最大值")
                return

            os.makedirs("configs", exist_ok=True)

            config = {
                "click": {
                    "move_delay_ms": [self.move_min_spin.value(), self.move_max_spin.value()],
                    "click_delay_ms": [self.click_min_spin.value(), self.click_max_spin.value()],
                    "jitter_px": 3,
                    "between_chip_delay_ms": [self.chip_min_spin.value(), self.chip_max_spin.value()],
                    "after_bet_button_delay_ms": [self.bet_min_spin.value(), self.bet_max_spin.value()],
                    "after_confirm_delay_ms": [self.confirm_min_spin.value(), self.confirm_max_spin.value()]
                },
                "description": {
                    "move_delay_ms": "滑鼠移動時間範圍（毫秒）[最小, 最大]",
                    "click_delay_ms": "點擊後等待時間範圍（毫秒）[最小, 最大]",
                    "jitter_px": "點擊位置隨機偏移量（像素）",
                    "between_chip_delay_ms": "籌碼之間的延遲範圍（毫秒）[最小, 最大]",
                    "after_bet_button_delay_ms": "點擊下注按鈕後的延遲範圍（毫秒）[最小, 最大]",
                    "after_confirm_delay_ms": "點擊確認按鈕後的延遲範圍（毫秒）[最小, 最大]"
                }
            }

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            emit_toast("點擊延遲設定已保存（重啟引擎後生效）", "success")
            QMessageBox.information(self, "成功", "點擊延遲設定已保存\n請重新啟動引擎以套用新設定")
        except Exception as e:
            emit_toast(f"保存失敗: {str(e)}", "error")
            QMessageBox.critical(self, "錯誤", f"保存失敗: {str(e)}")

    def reset_defaults(self):
        """重置為預設值"""
        self.move_min_spin.setValue(300)
        self.move_max_spin.setValue(600)
        self.click_min_spin.setValue(200)
        self.click_max_spin.setValue(400)
        self.chip_min_spin.setValue(400)
        self.chip_max_spin.setValue(700)
        self.bet_min_spin.setValue(500)
        self.bet_max_spin.setValue(800)
        self.confirm_min_spin.setValue(300)
        self.confirm_max_spin.setValue(500)

class SettingsPage(QWidget):
    """系統設定頁面"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 標題
        header = QLabel("系統設定")
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

        # 點擊延遲設定
        self.delay_settings = ClickDelaySettings()

        layout.addWidget(header)
        layout.addWidget(self.preset_manager)
        layout.addWidget(self.delay_settings)
        layout.addStretch()