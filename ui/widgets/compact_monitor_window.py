# ui/widgets/compact_monitor_window.py
"""
精簡監控視窗 - 永遠置頂的小型監控面板
適合單螢幕用戶，不遮擋遊戲畫面
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from ..design_system import FontStyle, Colors, Spacing, StyleSheet


class CompactMonitorWindow(QWidget):
    """精簡監控視窗"""

    # 信號
    emergency_stop_clicked = Signal()
    show_main_window_clicked = Signal()

    def __init__(self):
        super().__init__()
        print("[CompactMonitor] Initializing CompactMonitorWindow")

        # 用於拖動視窗
        self._drag_pos = None

        # 結果局自動清除定時器（必須在 setup_ui 之前初始化）
        self.result_clear_timer = QTimer(self)
        self.result_clear_timer.setSingleShot(True)
        self.result_clear_timer.timeout.connect(self._clear_result_display)

        self.setup_ui()
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |  # 永遠置頂
            Qt.FramelessWindowHint      # 無邊框
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        print("[CompactMonitor] CompactMonitorWindow initialized")

    def setup_ui(self):
        """設置 UI"""
        self.setWindowTitle("監控面板")
        self.resize(280, 420)

        # 主佈局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 容器框架（深色背景，無邊框）
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d23;
                border: none;
                border-radius: 0px;
            }}
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(16, 12, 16, 12)
        container_layout.setSpacing(12)

        # 0. 標題欄（含關閉按鈕）
        self.title_bar = self._create_title_bar()
        container_layout.addWidget(self.title_bar)

        # 1. 狀態欄（模式 + 檢測）
        self.status_section = self._create_status_section()
        container_layout.addWidget(self.status_section)

        # 2. 策略資訊
        self.strategy_section = self._create_strategy_section()
        container_layout.addWidget(self.strategy_section)

        # 3. 盈虧卡片（高亮顯示）
        self.pnl_section = self._create_pnl_section()
        container_layout.addWidget(self.pnl_section)

        # 4. 下注/結果卡片
        self.bet_section = self._create_bet_section()
        container_layout.addWidget(self.bet_section)

        # 5. 歷史記錄
        self.history_section = self._create_history_section()
        container_layout.addWidget(self.history_section)

        # 6. 警告區（初始隱藏）
        self.warning_section = self._create_warning_section()
        container_layout.addWidget(self.warning_section)
        self.warning_section.hide()

        # 添加彈性空間
        container_layout.addStretch()

        # 7. 底部按鈕
        self.control_section = self._create_control_section()
        container_layout.addWidget(self.control_section)

        main_layout.addWidget(container)

        # 初始化顯示
        self.update_status("idle", "○ 等待啟動", "")
        self.update_strategy("", "", "", "", 0, 0, 0.0, "")
        self.update_pnl(0, 0, 0, 0)
        self.update_bet_status("waiting", {})
        self.update_history([])

    def _create_divider(self) -> QFrame:
        """創建分隔線"""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BORDER_DEFAULT};
                max-height: 1px;
                margin: 4px 0px;
            }}
        """)
        return line

    def _create_title_bar(self) -> QFrame:
        """創建標題欄（含關閉按鈕）"""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 標題（可拖動區域）
        title_label = QLabel("監控面板")
        title_label.setFont(FontStyle.body_bold())
        title_label.setStyleSheet(f"color: {Colors.TEXT_IMPORTANT};")

        # 關閉按鈕
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont("Arial", 14, QFont.Bold))
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ERROR_500};
                color: white;
            }}
            QPushButton:pressed {{
                background-color: {Colors.ERROR_700};
            }}
        """)
        close_btn.clicked.connect(self.close)

        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(close_btn)

        return frame

    def _create_status_section(self) -> QFrame:
        """創建狀態欄（水平佈局：引擎狀態 | 可下注時間）"""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 運行狀態（左側）
        self.mode_label = QLabel("■ 待機中")
        self.mode_label.setFont(FontStyle.body_bold())
        self.mode_label.setStyleSheet(f"color: {Colors.TEXT_CRITICAL}; background: transparent; border: none;")

        # 可下注狀態（右側）
        self.detection_label = QLabel("○ 等待啟動")
        self.detection_label.setFont(FontStyle.body_bold())
        self.detection_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; background: transparent; border: none;")
        self.detection_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self.mode_label)
        layout.addStretch()  # 彈性空間，將兩個標籤推到兩側
        layout.addWidget(self.detection_label)

        return frame

    def _create_strategy_section(self) -> QFrame:
        """創建策略資訊區"""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 策略名稱（含層數）
        strategy_row = QHBoxLayout()
        strategy_row.setContentsMargins(0, 0, 0, 0)
        strategy_row.setSpacing(8)

        self.strategy_name_label = QLabel("策略: --")
        self.strategy_name_label.setFont(FontStyle.body_bold())
        self.strategy_name_label.setStyleSheet(f"color: {Colors.TEXT_IMPORTANT}; background: transparent; border: none;")

        self.strategy_layer_label = QLabel("")
        self.strategy_layer_label.setFont(FontStyle.body_bold())
        self.strategy_layer_label.setStyleSheet(f"color: {Colors.WARNING_500}; background: transparent; border: none;")
        self.strategy_layer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        strategy_row.addWidget(self.strategy_name_label)
        strategy_row.addStretch()
        strategy_row.addWidget(self.strategy_layer_label)

        # 策略狀態 + 下一注預覽
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)

        self.strategy_status_label = QLabel("● 運行中")
        self.strategy_status_label.setFont(FontStyle.caption())
        self.strategy_status_label.setStyleSheet(f"color: {Colors.SUCCESS_500}; background: transparent; border: none;")

        self.next_stake_label = QLabel("")
        self.next_stake_label.setFont(FontStyle.caption())
        self.next_stake_label.setStyleSheet(f"color: {Colors.INFO_500}; background: transparent; border: none;")
        self.next_stake_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        status_row.addWidget(self.strategy_status_label)
        status_row.addStretch()
        status_row.addWidget(self.next_stake_label)

        layout.addLayout(strategy_row)
        layout.addLayout(status_row)

        return frame

    def _create_pnl_section(self) -> QFrame:
        """創建盈虧卡片（現代化設計）"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #252930;
                border-radius: 6px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 標題
        title = QLabel("會話盈虧")
        title.setFont(FontStyle.caption())
        title.setStyleSheet("color: #8b92a0; background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)

        # 盈虧金額（超大字體）
        self.pnl_amount_label = QLabel("0 元")
        self.pnl_amount_label.setFont(QFont(FontStyle.FAMILY_MONO, 20, QFont.Bold))
        self.pnl_amount_label.setAlignment(Qt.AlignCenter)
        self.pnl_amount_label.setStyleSheet("color: #ffffff; background: transparent; border: none;")

        # 勝率
        self.win_rate_label = QLabel("0/0 | 0%")
        self.win_rate_label.setFont(FontStyle.caption())
        self.win_rate_label.setStyleSheet("color: #8b92a0; background: transparent; border: none;")
        self.win_rate_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(self.pnl_amount_label)
        layout.addWidget(self.win_rate_label)

        return frame

    def _create_bet_section(self) -> QFrame:
        """創建下注/結果卡片"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #252930;
                border-radius: 6px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 標題
        self.bet_title_label = QLabel("等待信號")
        self.bet_title_label.setFont(FontStyle.body_bold())
        self.bet_title_label.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        self.bet_title_label.setAlignment(Qt.AlignCenter)

        # 詳細資訊
        self.bet_detail_layout = QVBoxLayout()
        self.bet_detail_layout.setSpacing(2)

        self.bet_line1 = QLabel("")
        self.bet_line1.setFont(FontStyle.caption())
        self.bet_line1.setStyleSheet("color: #8b92a0; background: transparent; border: none;")
        self.bet_line1.setAlignment(Qt.AlignCenter)

        self.bet_line2 = QLabel("")
        self.bet_line2.setFont(FontStyle.caption())
        self.bet_line2.setStyleSheet("color: #8b92a0; background: transparent; border: none;")
        self.bet_line2.setAlignment(Qt.AlignCenter)

        self.bet_line3 = QLabel("")
        self.bet_line3.setFont(FontStyle.body())
        self.bet_line3.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        self.bet_line3.setAlignment(Qt.AlignCenter)

        self.bet_line4 = QLabel("")
        self.bet_line4.setFont(FontStyle.body_bold())
        self.bet_line4.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        self.bet_line4.setAlignment(Qt.AlignCenter)

        self.bet_detail_layout.addWidget(self.bet_line1)
        self.bet_detail_layout.addWidget(self.bet_line2)
        self.bet_detail_layout.addWidget(self.bet_line3)
        self.bet_detail_layout.addWidget(self.bet_line4)

        layout.addWidget(self.bet_title_label)
        layout.addLayout(self.bet_detail_layout)

        return frame

    def _create_history_section(self) -> QFrame:
        """創建歷史記錄區"""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 標題行（含方向指示）
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title = QLabel("最近 5 局")
        title.setFont(FontStyle.caption())
        title.setStyleSheet("color: #8b92a0; background: transparent; border: none;")

        direction_hint = QLabel("舊 → 新")
        direction_hint.setFont(FontStyle.caption())
        direction_hint.setStyleSheet("color: #6b7280; background: transparent; border: none;")
        direction_hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(direction_hint)

        # 歷史記錄
        self.history_label = QLabel("-- -- -- -- --")
        self.history_label.setFont(QFont(FontStyle.FAMILY_MONO, 12, QFont.Bold))
        self.history_label.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        self.history_label.setAlignment(Qt.AlignCenter)

        layout.addLayout(title_row)
        layout.addWidget(self.history_label)

        return frame

    def _create_warning_section(self) -> QFrame:
        """創建風險警告區"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.WARNING_900};
                border: 1px solid {Colors.WARNING_500};
                border-radius: {Spacing.RADIUS_MD}px;
                padding: {Spacing.PADDING_SM}px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        self.warning_label = QLabel("! 警告訊息")
        self.warning_label.setFont(FontStyle.body_bold())
        self.warning_label.setStyleSheet(f"color: {Colors.WARNING_50};")
        self.warning_label.setAlignment(Qt.AlignCenter)
        self.warning_label.setWordWrap(True)

        layout.addWidget(self.warning_label)

        return frame

    def _create_control_section(self) -> QFrame:
        """創建控制欄"""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 緊急停止按鈕
        self.stop_btn = QPushButton("緊急停止")
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ERROR_700};
                color: white;
                border: none;
                border-radius: {Spacing.RADIUS_MD}px;
                padding: {Spacing.PADDING_SM}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.ERROR_500};
            }}
        """)
        self.stop_btn.clicked.connect(self.emergency_stop_clicked.emit)

        # 顯示主視窗按鈕
        self.show_main_btn = QPushButton("主視窗")
        self.show_main_btn.setStyleSheet(StyleSheet.button_ghost())
        self.show_main_btn.clicked.connect(self.show_main_window_clicked.emit)

        layout.addWidget(self.stop_btn)
        layout.addWidget(self.show_main_btn)

        return frame

    # ==================== 更新方法 ====================

    def update_status(self, mode: str, mode_text: str, detection_text: str):
        """更新狀態欄"""
        self.mode_label.setText(mode_text)
        self.detection_label.setText(detection_text)

        # 根據模式改變引擎狀態顏色
        color_map = {
            "running": Colors.SUCCESS_500,
            "simulate": Colors.INFO_500,
            "idle": Colors.TEXT_MUTED,
            "stopped": Colors.GRAY_500
        }
        self.mode_label.setStyleSheet(f"color: {color_map.get(mode, Colors.TEXT_CRITICAL)}; background: transparent; border: none;")

        # 根據可下注狀態改變顏色
        if "可下注" in detection_text:
            # 可下注 → 綠色
            detection_color = Colors.SUCCESS_500
        elif "停止下注" in detection_text:
            # 停止下注 → 紅色
            detection_color = Colors.ERROR_500
        else:
            # 其他狀態 → 灰色
            detection_color = Colors.TEXT_MUTED

        self.detection_label.setStyleSheet(f"color: {detection_color}; background: transparent; border: none;")

    def update_strategy(self, strategy_name: str, table: str, round_id: str, status: str, current_layer: int = 0, max_layer: int = 0, next_stake: float = 0.0, direction: str = ""):
        """更新策略資訊

        Args:
            strategy_name: 策略名稱
            table: 桌號
            round_id: 局號
            status: 狀態
            current_layer: 當前層數
            max_layer: 最大層數
            next_stake: 下一注金額（負數=反向）
            direction: 下注方向 (banker/player/tie)
        """
        self.strategy_name_label.setText(f"策略: {strategy_name or '--'}")

        # 顯示層數（如果有）
        if current_layer > 0 and max_layer > 0:
            self.strategy_layer_label.setText(f"層數: {current_layer}/{max_layer}")
            self.strategy_layer_label.show()
        else:
            self.strategy_layer_label.setText("")
            self.strategy_layer_label.hide()

        # 顯示預計下手（方向 + 金額）
        if next_stake != 0:
            # 檢查是否為反向層
            is_reverse = (next_stake < 0)
            amount = abs(next_stake)

            # 方向映射和顏色
            direction_map = {
                "banker": ("B", Colors.ERROR_500),
                "player": ("P", Colors.INFO_500),
                "tie": ("T", Colors.SUCCESS_500)
            }
            direction_text, direction_color = direction_map.get(direction, ("?", Colors.TEXT_MUTED))

            # 如果是反向層，反轉方向
            if is_reverse:
                opposite_map = {"B": ("P", Colors.INFO_500), "P": ("B", Colors.ERROR_500), "T": ("T", Colors.SUCCESS_500)}
                direction_text, direction_color = opposite_map.get(direction_text, (direction_text, direction_color))

            # 反向標記
            reverse_indicator = "⮌" if is_reverse else ""

            self.next_stake_label.setText(f"預計下手: {direction_text} {amount:.0f}元{reverse_indicator}")
            self.next_stake_label.setStyleSheet(f"color: {direction_color}; background: transparent; border: none; font-weight: bold;")
            self.next_stake_label.show()
        else:
            self.next_stake_label.setText("")
            self.next_stake_label.hide()

        # 策略狀態
        if status == "running":
            self.strategy_status_label.setText("● 運行中")
            self.strategy_status_label.setStyleSheet(f"color: {Colors.SUCCESS_500}; background: transparent; border: none;")
        elif status == "frozen":
            self.strategy_status_label.setText("■ 已凍結")
            self.strategy_status_label.setStyleSheet(f"color: {Colors.ERROR_500}; background: transparent; border: none;")
        elif status == "waiting":
            self.strategy_status_label.setText("○ 等待中")
            self.strategy_status_label.setStyleSheet(f"color: {Colors.WARNING_500}; background: transparent; border: none;")
        else:
            self.strategy_status_label.setText("◼ 待機")
            self.strategy_status_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; background: transparent; border: none;")

    def update_pnl(self, pnl: float, wins: int, losses: int, total: int):
        """更新盈虧資訊"""
        # 盈虧金額
        sign = "+" if pnl > 0 else ""
        self.pnl_amount_label.setText(f"{sign}{pnl:.0f} 元")

        # 顏色
        if pnl > 0:
            self.pnl_amount_label.setStyleSheet(f"color: #10b981; background: transparent; border: none;")
        elif pnl < 0:
            self.pnl_amount_label.setStyleSheet(f"color: #ef4444; background: transparent; border: none;")
        else:
            self.pnl_amount_label.setStyleSheet(f"color: #ffffff; background: transparent; border: none;")

        # 勝率（簡化格式）
        win_rate = (wins / total * 100) if total > 0 else 0
        self.win_rate_label.setText(f"{wins}/{total} | {win_rate:.0f}%")

    def update_bet_status(self, status: str, data: dict):
        """
        更新下注/結果局狀態

        status:
            - "waiting": 等待進場信號
            - "ready": 準備下注
            - "pre_triggered": ✅ 策略已觸發，等待下注時機
            - "betting": 結果局進行中
            - "settled": 結果已出
        """
        # ✅ 如果是非 settled 狀態更新，停止自動清除定時器
        if status != "settled":
            self.result_clear_timer.stop()

        if status == "waiting":
            self.bet_title_label.setText("等待信號")
            self.bet_line1.setText("")
            self.bet_line2.setText("")
            self.bet_line3.setText("")
            self.bet_line4.setText("")

        elif status == "ready":
            self.bet_title_label.setText("下次下注")
            direction_map = {"banker": "莊家", "player": "閒家", "tie": "和局"}
            direction = direction_map.get(data.get("direction", ""), "--")
            amount = data.get("amount", 0)
            chips = data.get("chips_str", "--")

            self.bet_line1.setText(f"方向: {direction}")
            self.bet_line2.setText(f"金額: {amount} 元")
            self.bet_line3.setText(f"籌碼: {chips}")
            self.bet_line4.setText("")

        elif status == "pre_triggered":
            # ✅ 新增：預觸發狀態顯示
            self.bet_title_label.setText("🎯 策略已觸發")
            # ✅ 支持兩種格式：banker/player/tie 或 B/P/T
            direction_map = {
                "banker": "莊家", "player": "閒家", "tie": "和局",
                "B": "莊家", "P": "閒家", "T": "和局",
                "b": "莊家", "p": "閒家", "t": "和局"
            }
            direction_raw = data.get("direction", "")
            direction = direction_map.get(direction_raw, "--")
            amount = data.get("amount", 0)
            chips = data.get("chips_str", "--")

            self.bet_line1.setText(f"預計下手: {direction} {amount:.0f} 元")
            self.bet_line2.setText(f"籌碼: {chips}")
            self.bet_line3.setText("等待下注時機...")
            self.bet_line3.setStyleSheet(f"color: {Colors.INFO_500}; background: transparent; border: none;")
            self.bet_line4.setText("")

        elif status == "betting":
            self.bet_title_label.setText("結果局")
            # ✅ 支持兩種格式：banker/player/tie 或 B/P/T
            direction_map = {
                "banker": "莊家", "player": "閒家", "tie": "和局",
                "B": "莊家", "P": "閒家", "T": "和局",
                "b": "莊家", "p": "閒家", "t": "和局"
            }
            direction_raw = data.get("direction", "")
            direction = direction_map.get(direction_raw, "--")
            amount = data.get("amount", 0)
            chips = data.get("chips_str", "--")

            # ✅ 防禦性檢查：確保有有效數據
            if not direction_raw or amount == 0:
                self.bet_line1.setText(f"已下注: 數據載入中...")
                self.bet_line2.setText(f"籌碼: --")
            else:
                self.bet_line1.setText(f"已下注: {direction} {amount:.0f} 元")
                self.bet_line2.setText(f"籌碼: {chips}")

            self.bet_line3.setText("等待開獎...")
            self.bet_line4.setText("")

        elif status == "settled":
            self.bet_title_label.setText("結果局")
            # ✅ 支持兩種格式：banker/player/tie 或 B/P/T
            direction_map = {
                "banker": "莊家", "player": "閒家", "tie": "和局",
                "B": "莊家", "P": "閒家", "T": "和局",
                "b": "莊家", "p": "閒家", "t": "和局"
            }
            bet_direction_raw = data.get("direction", "")
            result_raw = data.get("result", "")
            bet_direction = direction_map.get(bet_direction_raw, "--")
            result_direction = direction_map.get(result_raw, "--")
            amount = data.get("amount", 0)
            pnl = data.get("pnl", 0)
            outcome = data.get("outcome", "")

            outcome_text = "勝" if outcome == "win" else "輸" if outcome == "loss" else "skip"

            # ✅ 防禦性檢查：確保有有效數據
            if not bet_direction_raw or amount == 0:
                self.bet_line1.setText(f"已下注: -- 元")
            else:
                self.bet_line1.setText(f"已下注: {bet_direction} {amount:.0f} 元")

            if not result_raw:
                self.bet_line2.setText(f"開獎: 數據載入中...")
            else:
                self.bet_line2.setText(f"開獎: {result_direction} ({outcome_text})")

            sign = "+" if pnl > 0 else ""
            pnl_text = f"盈虧: {sign}{pnl:.0f} 元"
            self.bet_line3.setText(pnl_text)

            # 盈虧顏色
            if pnl > 0:
                self.bet_line3.setStyleSheet(f"color: {Colors.SUCCESS_500}; background: transparent; border: none;")
            elif pnl < 0:
                self.bet_line3.setStyleSheet(f"color: {Colors.ERROR_500}; background: transparent; border: none;")
            else:
                self.bet_line3.setStyleSheet(f"color: {Colors.TEXT_NORMAL}; background: transparent; border: none;")

            self.bet_line4.setText("")

            # ✅ 啟動定時器：5秒後自動切回「等待信號」狀態
            self.result_clear_timer.stop()  # 先停止可能存在的舊定時器
            self.result_clear_timer.start(5000)  # 5秒 = 5000毫秒

    def update_history(self, history: list):
        """
        更新最近5局開獎結果

        history: list of dict
            [
                {"winner": "banker"},
                {"winner": "player"},
                {"winner": "tie"},
                ...
            ]
        """
        print(f"[CompactMonitor] update_history() called")
        print(f"[CompactMonitor] history type: {type(history)}")
        print(f"[CompactMonitor] history length: {len(history) if history else 0}")
        print(f"[CompactMonitor] history data: {history}")

        if not history:
            print(f"[CompactMonitor] No history data, setting default text")
            self.history_label.setText("-- -- -- -- --")
            return

        # 取最近5局
        recent = history[-5:] if len(history) >= 5 else history
        print(f"[CompactMonitor] recent length: {len(recent)}")
        print(f"[CompactMonitor] recent data: {recent}")

        # 格式: 莊 閒 莊 和 閒 (顯示最近5局開獎結果)
        result_strs = []
        for i, item in enumerate(recent):
            print(f"[CompactMonitor] Processing item {i}: {item}")
            winner = item.get("winner", "")
            print(f"[CompactMonitor]   winner: '{winner}'")

            # 開獎結果中文顯示（支持兩種格式）
            winner_map = {
                "banker": "莊", "player": "閒", "tie": "和",
                "B": "莊", "P": "閒", "T": "和"
            }
            result_str = winner_map.get(winner, "?")

            print(f"[CompactMonitor]   result_str: {result_str}")
            result_strs.append(result_str)

        # 補齊到5個
        while len(result_strs) < 5:
            result_strs.insert(0, "--")

        final_text = "  ".join(result_strs)
        print(f"[CompactMonitor] Setting history_label text to: {final_text}")
        self.history_label.setText(final_text)
        print(f"[CompactMonitor] After setText, label text is: {self.history_label.text()}")

    def show_warning(self, message: str):
        """顯示警告"""
        self.warning_label.setText(f"! {message}")
        self.warning_section.show()

    def hide_warning(self):
        """隱藏警告"""
        self.warning_section.hide()

    def _clear_result_display(self):
        """清除結果局顯示，切回「等待信號」狀態"""
        print("[CompactMonitor] Clearing result display, switching to 'waiting' status")
        self.update_bet_status("waiting", {})

    # ==================== 拖動視窗 ====================

    def mousePressEvent(self, event):
        """滑鼠按下"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """滑鼠移動（拖動視窗）"""
        if event.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        """滑鼠釋放"""
        self._drag_pos = None
