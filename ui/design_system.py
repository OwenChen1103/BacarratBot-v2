# ui/design_system.py
"""
UI 設計系統
定義統一的字體、色彩、間距等設計規範
"""

from PySide6.QtGui import QFont


# ============================================================
# 字體層級系統
# ============================================================

class FontStyle:
    """字體樣式"""

    # 字體家族
    FAMILY_UI = "Microsoft YaHei UI"
    FAMILY_MONO = "Consolas"  # 等寬字體（用於數字）

    # 字體大小
    SIZE_H1 = 12  # 大標題
    SIZE_H2 = 11  # 中標題
    SIZE_H3 = 10  # 小標題
    SIZE_BODY = 9  # 正文
    SIZE_CAPTION = 8  # 說明文字

    @staticmethod
    def title() -> QFont:
        """標題字體（策略名稱、卡片標題）"""
        return QFont(FontStyle.FAMILY_UI, FontStyle.SIZE_H2, QFont.Bold)

    @staticmethod
    def heading() -> QFont:
        """副標題字體"""
        return QFont(FontStyle.FAMILY_UI, FontStyle.SIZE_H3, QFont.Bold)

    @staticmethod
    def body() -> QFont:
        """正文字體"""
        return QFont(FontStyle.FAMILY_UI, FontStyle.SIZE_BODY, QFont.Normal)

    @staticmethod
    def body_bold() -> QFont:
        """加粗正文"""
        return QFont(FontStyle.FAMILY_UI, FontStyle.SIZE_BODY, QFont.Bold)

    @staticmethod
    def caption() -> QFont:
        """說明文字"""
        return QFont(FontStyle.FAMILY_UI, FontStyle.SIZE_CAPTION, QFont.Normal)

    @staticmethod
    def mono_number() -> QFont:
        """等寬數字字體（金額、數量）"""
        return QFont(FontStyle.FAMILY_MONO, FontStyle.SIZE_BODY, QFont.Bold)


# ============================================================
# 色彩系統
# ============================================================

class Colors:
    """色彩定義"""

    # === 基礎色彩 ===
    # 灰階
    GRAY_50 = "#f9fafb"
    GRAY_100 = "#f3f4f6"
    GRAY_200 = "#e5e7eb"
    GRAY_300 = "#d1d5db"
    GRAY_400 = "#9ca3af"
    GRAY_500 = "#6b7280"
    GRAY_600 = "#4b5563"
    GRAY_700 = "#374151"
    GRAY_800 = "#1f2937"
    GRAY_900 = "#111827"

    # === 語義色彩 ===
    # 成功/盈利（綠色）
    SUCCESS_50 = "#d1fae5"
    SUCCESS_100 = "#a7f3d0"
    SUCCESS_300 = "#6ee7b7"
    SUCCESS_500 = "#10b981"
    SUCCESS_700 = "#047857"
    SUCCESS_900 = "#065f46"

    # 警告/等待（黃色/橙色）
    WARNING_50 = "#fef3c7"
    WARNING_100 = "#fde68a"
    WARNING_300 = "#fcd34d"
    WARNING_500 = "#f59e0b"
    WARNING_700 = "#b45309"
    WARNING_900 = "#713f12"

    # 錯誤/虧損（紅色）
    ERROR_50 = "#fee2e2"
    ERROR_100 = "#fecaca"
    ERROR_500 = "#ef4444"
    ERROR_700 = "#b91c1c"
    ERROR_900 = "#7f1d1d"

    # 資訊（藍色）
    INFO_50 = "#dbeafe"
    INFO_100 = "#bfdbfe"
    INFO_500 = "#3b82f6"
    INFO_700 = "#1d4ed8"
    INFO_900 = "#1e3a8a"

    # === 文字色彩（依據重要性）===
    TEXT_CRITICAL = GRAY_100   # 最重要（#f3f4f6）
    TEXT_IMPORTANT = GRAY_200  # 重要（#e5e7eb）
    TEXT_NORMAL = GRAY_300     # 一般（#d1d5db）
    TEXT_MUTED = GRAY_400      # 輔助（#9ca3af）
    TEXT_DISABLED = GRAY_500   # 禁用（#6b7280）

    # === 背景色彩 ===
    BG_PRIMARY = GRAY_700      # 卡片主背景（#374151）
    BG_SECONDARY = GRAY_800    # 次要背景（#1f2937）
    BG_HOVER = "#3f4956"       # 懸停背景

    # === 邊框色彩 ===
    BORDER_DEFAULT = GRAY_600  # 預設邊框（#4b5563）
    BORDER_HOVER = GRAY_500    # 懸停邊框（#6b7280）

    # === 狀態背景色（帶透明度）===
    @staticmethod
    def status_bg(status: str) -> str:
        """獲取狀態背景色"""
        return {
            'running': Colors.SUCCESS_900,   # 運行中（深綠）
            'ready': Colors.SUCCESS_700,     # 準備就緒（綠）
            'waiting': Colors.WARNING_900,   # 等待中（深黃）
            'idle': Colors.GRAY_700,         # 待機（灰）
            'error': Colors.ERROR_900,       # 錯誤（深紅）
        }.get(status, Colors.GRAY_700)

    @staticmethod
    def status_border(status: str) -> str:
        """獲取狀態邊框色"""
        return {
            'running': Colors.SUCCESS_500,
            'ready': Colors.SUCCESS_500,
            'waiting': Colors.WARNING_500,
            'idle': Colors.GRAY_500,
            'error': Colors.ERROR_500,
        }.get(status, Colors.GRAY_500)

    @staticmethod
    def status_text(status: str) -> str:
        """獲取狀態文字色"""
        return {
            'running': Colors.SUCCESS_50,
            'ready': Colors.SUCCESS_50,
            'waiting': Colors.WARNING_50,
            'idle': Colors.GRAY_400,
            'error': Colors.ERROR_50,
        }.get(status, Colors.GRAY_400)

    @staticmethod
    def pnl_color(value: float) -> str:
        """根據盈虧值返回顏色"""
        if value > 0:
            return Colors.SUCCESS_500
        elif value < 0:
            return Colors.ERROR_500
        else:
            return Colors.GRAY_500


# ============================================================
# 間距系統
# ============================================================

class Spacing:
    """間距定義"""

    # 內邊距
    PADDING_XS = 4
    PADDING_SM = 8
    PADDING_MD = 12
    PADDING_LG = 16
    PADDING_XL = 20

    # 外邊距
    MARGIN_XS = 4
    MARGIN_SM = 8
    MARGIN_MD = 12
    MARGIN_LG = 16

    # 行間距
    LINE_SPACING_TIGHT = 4
    LINE_SPACING_NORMAL = 8
    LINE_SPACING_RELAXED = 12

    # 圓角
    RADIUS_SM = 4
    RADIUS_MD = 6
    RADIUS_LG = 8
    RADIUS_XL = 12


# ============================================================
# 圖示系統
# ============================================================

class Icons:
    """統一的圖示定義"""

    # === 狀態圖示 ===
    IDLE = "⏸️"
    WAITING = "⏳"
    READY = "🎯"
    RUNNING = "▶️"
    PAUSED = "⏸"
    STOPPED = "⏹️"

    # === 資料類型 ===
    STRATEGY = "📊"
    RISK = "🛡️"
    MONEY = "💰"
    STATS = "📈"
    ROADMAP = "🎲"
    CALENDAR = "📅"

    # === 方向 ===
    BANKER = "🔴"
    PLAYER = "⚪"
    TIE = "🟢"

    # === 結果 ===
    WIN = "✅"
    LOSS = "❌"
    ALERT = "⚠️"
    CHECK = "✔"
    CROSS = "✖"

    # === 趨勢 ===
    UP = "⬆"
    DOWN = "⬇"
    NEUTRAL = "➡"


# ============================================================
# 樣式表輔助函數
# ============================================================

class StyleSheet:
    """樣式表生成器"""

    @staticmethod
    def card(bg_color: str = Colors.BG_PRIMARY,
             border_color: str = Colors.BORDER_DEFAULT,
             padding: int = Spacing.PADDING_MD,
             radius: int = Spacing.RADIUS_LG) -> str:
        """生成卡片樣式"""
        return f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: {radius}px;
                padding: {padding}px;
            }}
        """

    @staticmethod
    def label(color: str = Colors.TEXT_NORMAL,
              padding: int = Spacing.PADDING_XS) -> str:
        """生成標籤樣式"""
        return f"""
            QLabel {{
                color: {color};
                padding: {padding}px;
            }}
        """

    @staticmethod
    def number_badge(value: float) -> str:
        """生成數字徽章樣式（根據正負值）"""
        bg_color = Colors.SUCCESS_900 if value > 0 else (
            Colors.ERROR_900 if value < 0 else Colors.GRAY_800
        )
        text_color = Colors.SUCCESS_100 if value > 0 else (
            Colors.ERROR_100 if value < 0 else Colors.GRAY_300
        )
        border_color = Colors.SUCCESS_500 if value > 0 else (
            Colors.ERROR_500 if value < 0 else Colors.GRAY_500
        )

        return f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                padding: 2px 8px;
                border-radius: {Spacing.RADIUS_SM}px;
                font-family: {FontStyle.FAMILY_MONO};
                font-weight: bold;
            }}
        """

    @staticmethod
    def progress_bar() -> str:
        """生成進度條樣式"""
        return """
            QProgressBar {
                border: 1px solid #4b5563;
                border-radius: 4px;
                background-color: #1f2937;
                height: 18px;
                text-align: center;
                color: #f3f4f6;
                font-size: 8pt;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f59e0b, stop:1 #ef4444
                );
                border-radius: 3px;
            }
        """

    @staticmethod
    def divider() -> str:
        """生成分隔線樣式"""
        return f"""
            QFrame {{
                background-color: {Colors.BORDER_DEFAULT};
                max-height: 1px;
                margin: 6px 0px;
            }}
        """
