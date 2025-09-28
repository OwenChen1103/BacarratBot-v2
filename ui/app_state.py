# ui/app_state.py
"""
全域事件匯流排 - 處理跨頁面狀態同步
不存儲實際數據，只做事件通知
"""
from PySide6.QtCore import QObject, Signal

class AppState(QObject):
    """應用程式狀態事件匯流排"""

    # 模板狀態變更 {'complete': bool, 'missing': list, 'total': int}
    templatesChanged = Signal(dict)

    # 位置狀態變更 {'complete': bool, 'count': int, 'required': list}
    positionsChanged = Signal(dict)

    # Overlay 狀態變更 {'has_roi': bool, 'threshold': float, 'ready': bool}
    overlayChanged = Signal(dict)

    # 策略狀態變更 {'complete': bool, 'target': str, 'unit': int}
    strategyChanged = Signal(dict)

    # 引擎狀態變更 {'state': str, 'enabled': bool, 'rounds': int, 'net': float}
    engineChanged = Signal(dict)

    # Toast 訊息 {'type': 'success'|'error'|'warning', 'message': str, 'duration': int}
    toastRequested = Signal(dict)

    # Banner 訊息 {'type': 'error'|'warning', 'message': str, 'actions': list}
    bannerRequested = Signal(dict)

# 全域實例
APP_STATE = AppState()

def emit_toast(message: str, toast_type: str = "success", duration: int = 2200):
    """發送 Toast 訊息"""
    APP_STATE.toastRequested.emit({
        'type': toast_type,
        'message': message,
        'duration': duration
    })

def emit_banner(message: str, banner_type: str = "error", actions: list = None):
    """發送 Banner 訊息"""
    APP_STATE.bannerRequested.emit({
        'type': banner_type,
        'message': message,
        'actions': actions or []
    })