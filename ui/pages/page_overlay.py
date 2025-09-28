# ui/pages/page_overlay.py
import json
import os
import time
import logging
import cv2
import numpy as np
from enum import Enum
from typing import Dict, List, Tuple, Optional
from collections import deque

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QTextEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QFileDialog, QMessageBox, QFrame, QScrollArea,
    QSplitter, QProgressBar, QRadioButton, QSizePolicy,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QStyleOptionGraphicsItem, QGraphicsItem, QGraphicsRectItem
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QRect, QPoint, QSize, QPointF, QRectF
from PySide6.QtGui import (
    QFont, QPixmap, QPainter, QPen, QColor, QBrush,
    QGuiApplication, QImage, QCursor, QKeySequence, QShortcut,
    QPainterPath, QWheelEvent
)

from ..app_state import APP_STATE, emit_toast

logger = logging.getLogger(__name__)

POSITIONS_FILE = "configs/positions.json"
OVERLAY_LOG_FILE = "data/logs/overlay_debug.log"
TEMPLATES_DIR = "templates/overlay/"

class OverlayPhase(str, Enum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    DEALING = "dealing"
    RESULT = "result"
    UNKNOWN = "unknown"


class ROIItem(QGraphicsRectItem, QWidget):
    sig_rect_changed = Signal()

    HANDLE_SIZE = 6.0

    def __init__(self, bounds_rect: QRectF, roi_type: str):
        QGraphicsRectItem.__init__(self, QRectF(100, 100, 400, 80))
        QWidget.__init__(self)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._dragging = None
        self._start_rect = QRectF(self.rect())
        self._start_pos = QPointF()
        self._bounds = bounds_rect  # 影像邊界（scene 座標）
        self.roi_type = roi_type  # "overlay" / "timer"
        self.active = True
        # 標籤 chip
        self.label_bg_color = QColor("#0ea5e9") if roi_type == "overlay" else QColor("#d97706")
        self.label_text = "Overlay" if roi_type == "overlay" else "Timer"

    def set_bounds(self, r: QRectF):
        self._bounds = QRectF(r)
        self._clamp()

    def paint(self, p: QPainter, o: QStyleOptionGraphicsItem, w: QWidget | None = None):
        r = self.rect()
        # 周圍遮罩
        if self.scene():
            p.save()
            g = QPainterPath()
            g.addRect(self.scene().sceneRect())
            g2 = QPainterPath()
            g2.addRect(r)
            p.fillPath(g - g2, QColor(0, 0, 0, 120))
            p.restore()

        # 框（不同樣式）
        p.setRenderHint(QPainter.Antialiasing)
        if self.roi_type == "overlay":
            pen = QPen(QColor("#22c55e"), 2)  # Green for overlay
            pen.setStyle(Qt.SolidLine)
            p.setPen(pen)
            p.setBrush(QColor(34,197,94,30))
        else:
            pen = QPen(QColor("#3b82f6"), 2)  # Blue for timer
            pen.setStyle(Qt.DashLine if not self.active else Qt.SolidLine)
            p.setPen(pen)
            p.setBrush(QColor(59,130,246,25))
        p.drawRect(r)

        # 標籤 chip
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(self.label_bg_color)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(self.label_text) + 10
        th = fm.height() + 4
        chip_rect = QRectF(r.left()+4, r.top()+4, tw, th)
        p.drawRoundedRect(chip_rect, 6, 6)
        p.setPen(QColor("white"))
        p.drawText(chip_rect.adjusted(5, 0, -5, 0), Qt.AlignVCenter | Qt.AlignLeft, self.label_text)
        p.restore()

        # handles（依 ROI 類型/是否 active 顯示不同形狀）
        if self.active:
            if self.roi_type == "overlay":
                p.setBrush(QBrush(QColor("#22c55e")))  # Green
                p.setPen(QPen(QColor("#16a34a")))
                for pt in self._handle_points(r):
                    s = self.HANDLE_SIZE
                    p.drawRect(QRectF(pt.x()-s/2, pt.y()-s/2, s, s))
            else:
                p.setBrush(QBrush(QColor("#3b82f6")))  # Blue
                p.setPen(QPen(QColor("#2563eb")))
                for pt in self._handle_points(r):
                    s = self.HANDLE_SIZE
                    p.drawEllipse(QRectF(pt.x()-s/2, pt.y()-s/2, s, s))

    def _handle_points(self, r: QRectF):
        return [
            r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight(),
            QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()),
            QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y())
        ]

    def _hit_handle(self, pos: QPointF) -> str | None:
        names = ["lt","rt","lb","rb","t","b","l","r"]
        for name, pt in zip(names, self._handle_points(self.rect())):
            if QRectF(pt.x()-8, pt.y()-8, 16, 16).contains(pos):
                return name
        if self.rect().contains(pos):
            return "move"
        return None

    def hoverMoveEvent(self, e):
        hit = self._hit_handle(e.pos())
        cursor = Qt.ArrowCursor
        if hit in ("lt","rb"):
            cursor = Qt.SizeFDiagCursor
        elif hit in ("rt","lb"):
            cursor = Qt.SizeBDiagCursor
        elif hit in ("l","r"):
            cursor = Qt.SizeHorCursor
        elif hit in ("t","b"):
            cursor = Qt.SizeVerCursor
        elif hit == "move":
            cursor = Qt.OpenHandCursor
        self.setCursor(cursor)

    def mousePressEvent(self, e):
        if not self.active:
            e.ignore()
            return
        self._dragging = self._hit_handle(e.pos()) or "move"
        self._start_rect = QRectF(self.rect())
        self._start_pos = QPointF(e.pos())
        if self._dragging == "move":
            self.setCursor(Qt.ClosedHandCursor)
        e.accept()

    def mouseMoveEvent(self, e):
        if not self._dragging:
            return
        r = QRectF(self._start_rect)
        delta = e.pos() - self._start_pos
        if self._dragging == "move":
            r.moveTopLeft(r.topLeft() + delta)
        else:
            if "l" in self._dragging:
                r.setLeft(r.left() + delta.x())
            if "r" in self._dragging:
                r.setRight(r.right() + delta.x())
            if "t" in self._dragging:
                r.setTop(r.top() + delta.y())
            if "b" in self._dragging:
                r.setBottom(r.bottom() + delta.y())
        self.setRect(r.normalized())
        self._clamp()
        self.sig_rect_changed.emit()
        e.accept()

    def mouseReleaseEvent(self, e):
        self._dragging = None
        self.setCursor(Qt.ArrowCursor)
        self._clamp()
        self.sig_rect_changed.emit()
        e.accept()

    def _clamp(self):
        r = QRectF(self.rect())
        b = self._bounds
        if b.isNull():
            return
        if r.left() < b.left():
            r.moveLeft(b.left())
        if r.top() < b.top():
            r.moveTop(b.top())
        if r.right() > b.right():
            r.moveRight(b.right())
        if r.bottom() > b.bottom():
            r.moveBottom(b.bottom())
        # 保證不為負尺寸
        r.setWidth(max(20.0, min(r.width(), b.width())))
        r.setHeight(max(20.0, min(r.height(), b.height())))
        self.setRect(r)


class PreviewView(QGraphicsView):
    roi_changed = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setStyleSheet("QGraphicsView { background: #1f2937; border: 2px solid #374151; border-radius: 8px; }")

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix_item: QGraphicsPixmapItem | None = None
        self.current_phase = "UNKNOWN"

        # 兩個 ROI
        self.current_roi_name = "overlay"
        self.roi_items = {
            "overlay": ROIItem(QRectF(), "overlay"),
            "timer": ROIItem(QRectF(), "timer")
        }
        for name, item in self.roi_items.items():
            self._scene.addItem(item)
            item.sig_rect_changed.connect(lambda n=name: self._emit_roi(n))

        # 放大鏡設定
        self._mouse_pos = QPointF()

    def set_current_roi(self, name: str):
        self.current_roi_name = name
        # 鎖定/解鎖與透明度
        for roi_name, item in self.roi_items.items():
            item.active = (roi_name == name)
            item.setOpacity(1.0 if item.active else 0.45)
            item.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable if item.active else QGraphicsItem.GraphicsItemFlag(0))
            item.setCursor(Qt.OpenHandCursor if item.active else Qt.ForbiddenCursor)
            item.update()

    def set_current_phase(self, phase: str):
        self.current_phase = phase
        self.viewport().update()

    def set_pixmap(self, pix: QPixmap):
        if self._pix_item is None:
            self._pix_item = self._scene.addPixmap(pix)
            self._pix_item.setZValue(-10)
        else:
            self._pix_item.setPixmap(pix)
        # 更新邊界供 clamp 使用
        bounds = QRectF(0, 0, pix.width(), pix.height())
        self._scene.setSceneRect(bounds)
        for item in self.roi_items.values():
            item.set_bounds(bounds)
        # 確保兩個 ROI 在影像邊界內，若無效或超界給置中預設
        def default_rect(kind: str) -> QRectF:
            bw, bh = bounds.width(), bounds.height()
            w = max(80.0, bw * 0.3)
            h = max(60.0, (bh * 0.12) if kind == "overlay" else (bh * 0.16))
            return QRectF(bounds.left() + (bw - w) / 2, bounds.top() + (bh - h) / 2, w, h)

        for kind, item in self.roi_items.items():
            r = QRectF(item.rect())
            out = (
                r.width() <= 0 or r.height() <= 0 or
                r.right() < bounds.left() or r.bottom() < bounds.top() or
                r.left() > bounds.right() or r.top() > bounds.bottom()
            )
            if out:
                item.setRect(default_rect(kind))
            item.set_bounds(bounds)
        self.fitInView(self._pix_item, Qt.KeepAspectRatio)
        self.viewport().update()

    def _emit_roi(self, name: str):
        r = self.roi_items[name].rect().toRect()
        self.roi_changed.emit(name, {"x": r.x(), "y": r.y(), "w": r.width(), "h": r.height()})

    def wheelEvent(self, e: QWheelEvent):
        if e.modifiers() & Qt.ControlModifier:
            # 保留給外層其他快捷；此處仍然縮放
            pass
        delta = 1.001 ** e.angleDelta().y()
        self.scale(delta, delta)

    def mouseMoveEvent(self, e):
        self._mouse_pos = self.mapToScene(e.pos())
        super().mouseMoveEvent(e)
        self.viewport().update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.setCursor(Qt.ClosedHandCursor)
            self._panning = True
            self._pan_start = e.pos()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e):
        if getattr(self, "_panning", False):
            d = e.pos() - self._pan_start
            self._pan_start = e.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            e.accept()
            return
        self._mouse_pos = self.mapToScene(e.pos())
        super().mouseMoveEvent(e)
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect: QRectF):
        # 相位邊框
        phase_colors = {
            "OPEN": "#10b981",
            "CLOSING": "#f59e0b",
            "CLOSED": "#dc2626",
            "DEALING": "#8b5cf6",
            "RESULT": "#06b6d4",
            "UNKNOWN": "#6b7280"
        }
        if self._pix_item is not None:
            pen = QPen(QColor(phase_colors.get(self.current_phase, "#6b7280")), 3)
            painter.setPen(pen)
            painter.drawRect(self._scene.sceneRect())

        # 右下角放大鏡（取較小區域並降低倍率）
        if self._pix_item is not None and not self._scene.sceneRect().isNull():
            src_size = 72  # 原 100 -> 72
            x = int(max(0, min(self._mouse_pos.x() - src_size/2, self._scene.width()-src_size)))
            y = int(max(0, min(self._mouse_pos.y() - src_size/2, self._scene.height()-src_size)))
            src = QRectF(x, y, src_size, src_size)
            thumb = self._pix_item.pixmap().copy(int(src.x()), int(src.y()), int(src.width()), int(src.height()))
            mag = thumb.scaled(src_size*2, src_size*2)  # 原 x3 -> x2
            view_rect = self.viewport().rect()
            pos = QPoint(view_rect.right()-int(src_size*2)-12, view_rect.bottom()-int(src_size*2)-12)
            painter.resetTransform()  # 確保在視口座標畫
            painter.drawPixmap(pos, mag)
            painter.setPen(QPen(QColor("#374151"), 2))
            painter.drawRect(QRect(pos, mag.size()))

class OverlayPage(QWidget):
    """可下注判斷頁面（完整互動版）"""

    def __init__(self):
        super().__init__()
        self.detector = None
        self.detection_timer = QTimer()
        self.detection_active = False
        self.current_frame = None
        self.log_buffer = deque(maxlen=30)
        self.frame_count = 0
        self.last_frame_time = time.time()

        # FPS 計算
        self.fps_buffer = deque(maxlen=30)
        self.fps_last_time = time.time()

        # ROI 設定
        self.overlay_roi = {"x": 100, "y": 100, "w": 400, "h": 80}
        self.timer_roi = {"x": 500, "y": 200, "w": 100, "h": 100}

        # 來源模式與圖片來源記錄
        self.source_mode = "screen"  # "screen" or "image"
        self.last_image_path = None

        # 模板路徑
        self.template_paths = {
            "qing": None,
            "jie": None,
            "fa": None
        }

        # 參數（用於持久化）
        self.overlay_params = {
            "consecutive_required": 3,
            "ncc_threshold": 0.6,
            "flicker_threshold": 0.06,
            "timer_white_range": [0.03, 0.20],
            "template_paths": self.template_paths.copy()
        }

        self.setup_ui()
        self.setup_shortcuts()
        self.load_positions()
        self.init_detection_timer()

    def setup_ui(self):
        """設定 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(2, 0, 2, 2)

        # 標題
        title = QLabel("🎯 可下注判斷")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        title.setStyleSheet("color: #f3f4f6; padding: 4px 8px; margin: 0px;")
        title.setFixedHeight(26)  # 固定高度避免過大
        layout.addWidget(title)

        # 主分割器
        main_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(main_splitter, 1)  # stretch factor = 1，佔用剩餘空間

        # 左側：預覽與 ROI 編輯
        left_panel = self.create_preview_panel()
        main_splitter.addWidget(left_panel)

        # 右側：控制與狀態
        right_panel = self.create_control_panel()
        main_splitter.addWidget(right_panel)

        main_splitter.setSizes([900, 400])  # 增加右側面板寬度

    def create_preview_panel(self):
        """創建預覽面板"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 0px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setSpacing(2)
        # 進一步收緊內間距，讓 ROI 編輯區更貼近上下邊
        layout.setContentsMargins(2, 0, 2, 2)

        # ROI 選擇器
        roi_group = QWidget()
        # 背景改為與左側大區塊相同的深藍色（移除底線）
        roi_group.setStyleSheet(
            "background-color: #111827; border: none;"
        )
        roi_layout = QHBoxLayout(roi_group)
        roi_layout.setContentsMargins(0, 0, 0, 0)
        roi_layout.setSpacing(8)
        # 適度增加高度，避免過薄
        roi_group.setFixedHeight(50)

        roi_label = QLabel("編輯 ROI:")
        roi_label.setStyleSheet("color: #f3f4f6; font-weight: bold; padding: 0px; margin: 0px; font-size: 12px; text-decoration: none;")
        roi_layout.addWidget(roi_label)

        self.overlay_radio = QRadioButton("Overlay")
        self.overlay_radio.setChecked(True)
        self.overlay_radio.setStyleSheet("QRadioButton { color: #60a5fa; font-weight: bold; padding: 0px; margin: 0px; font-size: 12px; text-decoration: none; }")
        self.overlay_radio.toggled.connect(lambda: self.set_current_roi("overlay"))
        roi_layout.addWidget(self.overlay_radio)

        self.timer_radio = QRadioButton("Timer")
        self.timer_radio.setStyleSheet("QRadioButton { color: #f59e0b; font-weight: bold; padding: 0px; margin: 0px; font-size: 12px; text-decoration: none; }")
        self.timer_radio.toggled.connect(lambda: self.set_current_roi("timer"))
        roi_layout.addWidget(self.timer_radio)

        # 小圖例
        legend = QLabel("實線青框＝Overlay  |  虛線橘框＝Timer")
        legend.setStyleSheet("color: #9ca3af; font-size: 11px;")
        roi_layout.addWidget(legend)

        roi_layout.addStretch()
        layout.addWidget(roi_group)

        # 互動式預覽
        self.preview = PreviewView()
        # 放寬高度：讓左側可隨視窗垂直擴張
        self.preview.setMinimumSize(640, 400)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.roi_changed.connect(self.on_roi_changed)
        layout.addWidget(self.preview)

        # 控制按鈕
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 2, 0, 0)
        capture_btn = QPushButton("📸 截取螢幕")
        capture_btn.clicked.connect(self.capture_screen)
        capture_btn.setStyleSheet("""
            QPushButton {
                background: #1e40af;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background: #1d4ed8; }
        """)
        btn_layout.addWidget(capture_btn)

        # FPS 顯示與控制
        fps_label = QLabel("FPS:")
        fps_label.setStyleSheet("color: #f3f4f6;")
        self.fps_display = QLabel("--")
        self.fps_display.setStyleSheet("""
            QLabel {
                background: #1f2937;
                color: #10b981;
                padding: 4px 8px;
                border-radius: 4px;
                font-family: monospace;
                min-width: 40px;
            }
        """)
        self.fps_display.setAlignment(Qt.AlignCenter)

        timer_label = QLabel("間隔(ms):")
        timer_label.setStyleSheet("color: #f3f4f6;")
        self.timer_interval_spin = QSpinBox()
        self.timer_interval_spin.setRange(60, 300)
        self.timer_interval_spin.setValue(120)
        self.timer_interval_spin.setStyleSheet("QSpinBox { background: #374151; color: white; }")
        self.timer_interval_spin.valueChanged.connect(self.update_timer_interval)

        btn_layout.addStretch()
        btn_layout.addWidget(fps_label)
        btn_layout.addWidget(self.fps_display)
        btn_layout.addWidget(timer_label)
        btn_layout.addWidget(self.timer_interval_spin)
        layout.addLayout(btn_layout)

        return panel

    def create_control_panel(self):
        """創建控制面板"""
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        panel.setMinimumWidth(380)  # 增加最小寬度
        panel.setMaximumWidth(450)  # 設定最大寬度

        content = QWidget()
        layout = QVBoxLayout(content)

        # 檢測控制
        self.setup_detection_controls(layout)

        # 模板管理
        self.setup_template_controls(layout)

        # 參數調整
        self.setup_parameter_controls(layout)

        # 即時狀態
        self.setup_status_display(layout)

        # 日誌顯示
        self.setup_log_display(layout)

        layout.addStretch()
        panel.setWidget(content)
        return panel

    def setup_detection_controls(self, layout):
        """設定檢測控制組"""
        group = QGroupBox("🎮 檢測控制")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
        """)
        group_layout = QVBoxLayout(group)

        # 來源切換列
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("來源："))

        self.src_screen = QRadioButton("螢幕")
        self.src_image = QRadioButton("圖片")
        self.src_screen.setChecked(True)
        self.src_screen.toggled.connect(lambda: self.set_source_mode("screen"))
        self.src_image.toggled.connect(lambda: self.set_source_mode("image"))

        src_row.addWidget(self.src_screen)
        src_row.addWidget(self.src_image)

        self.load_image_btn = QPushButton("載入圖片")
        self.load_image_btn.clicked.connect(self.load_image_as_source)
        self.load_image_btn.setEnabled(False)
        src_row.addWidget(self.load_image_btn)

        self.step_btn = QPushButton("處理這一幀")
        self.step_btn.clicked.connect(self.process_one_frame)
        self.step_btn.setEnabled(False)
        src_row.addWidget(self.step_btn)

        src_row.addStretch()
        group_layout.addLayout(src_row)

        # 開始/停止按鈕
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("🚀 開始檢測")
        self.start_btn.clicked.connect(self.toggle_detection)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: #10b981;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background: #059669; }
        """)
        btn_layout.addWidget(self.start_btn)
        group_layout.addLayout(btn_layout)

        # 其他控制按鈕
        other_btn_layout = QHBoxLayout()

        save_btn = QPushButton("💾 保存 ROI")
        save_btn.clicked.connect(self.save_rois)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #7c3aed;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background: #6d28d9; }
        """)

        health_btn = QPushButton("🏥 健康檢查")
        health_btn.clicked.connect(self.health_check)
        health_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background: #b91c1c; }
        """)

        other_btn_layout.addWidget(save_btn)
        other_btn_layout.addWidget(health_btn)
        group_layout.addLayout(other_btn_layout)

        layout.addWidget(group)

    def setup_template_controls(self, layout):
        """設定模板控制組"""
        group = QGroupBox("📄 字模板管理")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
        """)
        group_layout = QVBoxLayout(group)

        # 模板載入按鈕
        template_btn_layout = QHBoxLayout()

        load_qing_btn = QPushButton("載入「請」")
        load_qing_btn.clicked.connect(lambda: self.load_template("qing"))

        load_jie_btn = QPushButton("載入「結」")
        load_jie_btn.clicked.connect(lambda: self.load_template("jie"))

        load_fa_btn = QPushButton("載入「發」")
        load_fa_btn.clicked.connect(lambda: self.load_template("fa"))

        for btn in [load_qing_btn, load_jie_btn, load_fa_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background: #f59e0b;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                }
                QPushButton:hover { background: #d97706; }
            """)

        template_btn_layout.addWidget(load_qing_btn)
        template_btn_layout.addWidget(load_jie_btn)
        template_btn_layout.addWidget(load_fa_btn)
        group_layout.addLayout(template_btn_layout)

        # 模板狀態
        self.template_status = QLabel("未載入模板")
        self.template_status.setStyleSheet("""
            QLabel {
                background: #7f1d1d;
                color: #fca5a5;
                padding: 4px;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        group_layout.addWidget(self.template_status)

        layout.addWidget(group)

    def setup_parameter_controls(self, layout):
        """設定參數控制組"""
        group = QGroupBox("⚙️ 檢測參數")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
        """)
        group_layout = QGridLayout(group)

        # 平滑參數
        row = 0
        group_layout.addWidget(QLabel("平滑幀數:"), row, 0)
        self.consecutive_spin = QSpinBox()
        self.consecutive_spin.setRange(1, 10)
        self.consecutive_spin.setValue(3)
        self.consecutive_spin.setStyleSheet("QSpinBox { background: #374151; color: white; }")
        group_layout.addWidget(self.consecutive_spin, row, 1)

        # NCC 門檻
        row += 1
        group_layout.addWidget(QLabel("NCC 門檻:"), row, 0)
        self.ncc_threshold_spin = QDoubleSpinBox()
        self.ncc_threshold_spin.setRange(0.1, 1.0)
        self.ncc_threshold_spin.setSingleStep(0.05)
        self.ncc_threshold_spin.setValue(0.7)
        self.ncc_threshold_spin.setStyleSheet("QDoubleSpinBox { background: #374151; color: white; }")
        group_layout.addWidget(self.ncc_threshold_spin, row, 1)

        # Flicker 門檻
        row += 1
        group_layout.addWidget(QLabel("閃爍門檻:"), row, 0)
        self.flicker_threshold_spin = QDoubleSpinBox()
        self.flicker_threshold_spin.setRange(0.01, 0.2)
        self.flicker_threshold_spin.setSingleStep(0.01)
        self.flicker_threshold_spin.setValue(0.06)
        self.flicker_threshold_spin.setStyleSheet("QDoubleSpinBox { background: #374151; color: white; }")
        group_layout.addWidget(self.flicker_threshold_spin, row, 1)

        # Timer 白像素範圍
        row += 1
        group_layout.addWidget(QLabel("Timer 白像素範圍:"), row, 0)
        timer_layout = QHBoxLayout()
        self.timer_min_spin = QDoubleSpinBox()
        self.timer_min_spin.setRange(0.01, 0.5)
        self.timer_min_spin.setSingleStep(0.01)
        self.timer_min_spin.setValue(0.03)
        self.timer_max_spin = QDoubleSpinBox()
        self.timer_max_spin.setRange(0.01, 0.5)
        self.timer_max_spin.setSingleStep(0.01)
        self.timer_max_spin.setValue(0.20)
        for spin in [self.timer_min_spin, self.timer_max_spin]:
            spin.setStyleSheet("QDoubleSpinBox { background: #374151; color: white; }")
        timer_layout.addWidget(self.timer_min_spin)
        timer_layout.addWidget(QLabel("-"))
        timer_layout.addWidget(self.timer_max_spin)
        group_layout.addLayout(timer_layout, row, 1)

        layout.addWidget(group)

    def setup_status_display(self, layout):
        """設定狀態顯示組"""
        group = QGroupBox("📊 即時狀態")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
        """)
        group_layout = QVBoxLayout(group)

        # 相位燈號
        phase_layout = QHBoxLayout()
        phase_layout.addWidget(QLabel("階段:"))
        self.phase_indicator = QLabel("UNKNOWN")
        self.phase_indicator.setAlignment(Qt.AlignCenter)
        self.phase_indicator.setStyleSheet("""
            QLabel {
                background: #374151;
                color: #9ca3af;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                min-width: 100px;
            }
        """)
        phase_layout.addWidget(self.phase_indicator)
        phase_layout.addStretch()
        group_layout.addLayout(phase_layout)

        # 數值顯示
        self.status_grid = QGridLayout()
        self.status_labels = {}

        status_items = [
            ("狀態", "decision"), ("NCC請", "ncc_qing"), ("Hue", "hue"),
            ("Sat", "sat"), ("Val", "val"), ("綠區", "in_green_gate"),
            ("開啟", "open_counter"), ("關閉", "close_counter"), ("開中", "open_hit")
        ]

        for i, (label, key) in enumerate(status_items):
            row, col = divmod(i, 3)
            self.status_grid.addWidget(QLabel(f"{label}:"), row*2, col)

            value_label = QLabel("--")
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setStyleSheet("""
                QLabel {
                    background: #1f2937;
                    color: #e5e7eb;
                    padding: 2px 4px;
                    border-radius: 3px;
                    font-family: monospace;
                    font-size: 12px;
                }
            """)
            self.status_labels[key] = value_label
            self.status_grid.addWidget(value_label, row*2+1, col)

        group_layout.addLayout(self.status_grid)
        layout.addWidget(group)

    def setup_log_display(self, layout):
        """設定日誌顯示組"""
        group = QGroupBox("📝 檢測日誌 (最近30行)")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
        """)
        group_layout = QVBoxLayout(group)

        self.log_display = QTextEdit()
        self.log_display.setMaximumHeight(200)
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background: #111827;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 10px;
            }
        """)
        group_layout.addWidget(self.log_display)

        # 日誌操作按鈕
        log_btn_layout = QHBoxLayout()
        export_log_btn = QPushButton("📤 匯出日誌")
        export_log_btn.clicked.connect(self.export_log)
        export_log_btn.setStyleSheet("""
            QPushButton {
                background: #065f46;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background: #047857; }
        """)

        clear_log_btn = QPushButton("🗑️ 清空")
        clear_log_btn.clicked.connect(self.clear_log)
        clear_log_btn.setStyleSheet("""
            QPushButton {
                background: #7f1d1d;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background: #991b1b; }
        """)

        log_btn_layout.addWidget(export_log_btn)
        log_btn_layout.addWidget(clear_log_btn)
        log_btn_layout.addStretch()
        group_layout.addLayout(log_btn_layout)

        layout.addWidget(group)

    def init_detection_timer(self):
        """初始化檢測定時器"""
        self.detection_timer.timeout.connect(self.process_frame)
        self.detection_timer.setInterval(120)  # 120ms

    def capture_screen(self):
        """截取螢幕"""
        try:
            app = QGuiApplication.instance()
            screen = app.primaryScreen()
            screenshot = screen.grabWindow(0)

            # 轉換為 OpenCV 格式
            qimg = screenshot.toImage()
            width, height = qimg.width(), qimg.height()
            ptr = qimg.constBits()
            arr = np.array(ptr).reshape(height, width, 4)  # RGBA
            self.current_frame = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

            # 更新預覽
            self.preview.set_pixmap(screenshot)

            # 更新 ROI 到新預覽
            if hasattr(self.preview, 'roi_items'):
                self.preview.roi_items["overlay"].setRect(QRectF(
                    self.overlay_roi["x"], self.overlay_roi["y"],
                    self.overlay_roi["w"], self.overlay_roi["h"]
                ))
                self.preview.roi_items["timer"].setRect(QRectF(
                    self.timer_roi["x"], self.timer_roi["y"],
                    self.timer_roi["w"], self.timer_roi["h"]
                ))

            self.log_message("截取螢幕成功")

        except Exception as e:
            self.log_message(f"截取螢幕失敗: {e}")

    def toggle_detection(self):
        """切換檢測狀態"""
        if self.detection_active:
            self.stop_detection()
        else:
            self.start_detection()

    def start_detection(self):
        """開始檢測"""
        if self.source_mode == "screen" and self.current_frame is None:
            QMessageBox.warning(self, "警告", "請先截取螢幕")
            return
        if self.source_mode == "image" and self.current_frame is None:
            QMessageBox.warning(self, "警告", "請先載入圖片")
            return

        # 創建檢測器
        if not self.create_detector():
            return

        self.detection_active = True
        self.detection_timer.start()
        self.start_btn.setText("⏸️ 停止檢測")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background: #b91c1c; }
        """)

        self.log_message("開始即時檢測")

    def stop_detection(self):
        """停止檢測"""
        self.detection_active = False
        self.detection_timer.stop()
        self.start_btn.setText("開始檢測")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: #10b981;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background: #059669; }
        """)

        self.log_message("⏸️ 停止檢測")

    def create_detector(self):
        """創建檢測器"""
        try:
            from src.autobet.detectors import ProductionOverlayDetector

            config = {
                "open_threshold": 0.60,  # NCC_請 閾值
                "close_threshold": 0.45,  # 關閉閾值
                "k_open": 2,  # 開啟需要連續2幀
                "k_close": 2,  # 關閉需要連續2幀
                "green_hue_range": [95, 150],  # GREEN 色彩護欄
                "green_sat_min": 0.45,
                "green_val_min": 0.55,
                "max_open_wait_ms": 8000,  # 8秒超時保護
                "cancel_on_close": True
            }

            self.detector = ProductionOverlayDetector(config)
            self.detector.set_rois(self.overlay_roi, self.timer_roi)

            # 載入「請」模板（落地版只需要這個）
            if self.template_paths.get("qing"):
                self.detector.load_qing_template(self.template_paths["qing"])

            return True

        except Exception as e:
            self.log_message(f"❌ 創建檢測器失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"創建檢測器失敗:\n{e}")
            return False

    def process_frame(self):
        """處理幀"""
        if not self.detection_active or not self.detector:
            return

        try:
            # 計算 FPS
            self.calculate_fps()

            if self.source_mode == "screen":
                # 重新截取螢幕（即時檢測）
                app = QGuiApplication.instance()
                screen = app.primaryScreen()
                screenshot = screen.grabWindow(0)
                qimg = screenshot.toImage()
                width, height = qimg.width(), qimg.height()
                ptr = qimg.constBits()
                arr = np.array(ptr).reshape(height, width, 4)
                frame = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                self.current_frame = frame

                # 檢測
                result = self.detector.process_frame(frame)

                # 更新預覽與相位
                phase = result.get("phase_smooth", "UNKNOWN").upper()
                self.preview.set_current_phase(phase)
                self.preview.set_pixmap(screenshot)
            else:
                # 圖片模式：直接用現有幀
                if self.current_frame is None:
                    return
                result = self.detector.process_frame(self.current_frame)
                phase = result.get("phase_smooth", "UNKNOWN").upper()
                self.preview.set_current_phase(phase)

            # 更新 UI
            self.update_status_display(result)

            # 記錄日誌
            self.log_detection_result(result)

            self.frame_count += 1

        except Exception as e:
            self.log_message(f"❌ 處理幀失敗: {e}")

    def set_source_mode(self, mode: str):
        """切換來源模式"""
        self.source_mode = "image" if self.src_image.isChecked() else "screen"
        is_image = (self.source_mode == "image")
        self.load_image_btn.setEnabled(is_image)
        self.step_btn.setEnabled(is_image)
        self.log_message(f"來源切換為：{self.source_mode}")

    def load_image_as_source(self):
        """載入圖片作為來源"""
        start_dir = os.path.dirname(self.last_image_path) if self.last_image_path else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "選擇遊戲截圖", start_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if not file_path:
            return
        self.last_image_path = file_path
        img = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            QMessageBox.warning(self, "讀取失敗", "無法讀取圖片")
            return
        self.current_frame = img

        h, w = img.shape[:2]
        qimg = QImage(img.data, w, h, w*3, QImage.Format_BGR888)
        self.preview.set_pixmap(QPixmap.fromImage(qimg))
        # 同步 ROI 到預覽
        if hasattr(self.preview, 'roi_items'):
            self.preview.roi_items["overlay"].setRect(QRectF(
                self.overlay_roi["x"], self.overlay_roi["y"],
                self.overlay_roi["w"], self.overlay_roi["h"]
            ))
            self.preview.roi_items["timer"].setRect(QRectF(
                self.timer_roi["x"], self.timer_roi["y"],
                self.timer_roi["w"], self.timer_roi["h"]
            ))
        self.log_message(f"已載入圖片來源：{os.path.basename(file_path)}")

    def process_one_frame(self):
        """圖片模式下處理當前幀一次"""
        if self.source_mode != "image" or self.current_frame is None:
            return
        if not self.detector and not self.create_detector():
            return
        try:
            result = self.detector.process_frame(self.current_frame)
            phase = result.get("phase_smooth", "UNKNOWN").upper()
            self.preview.set_current_phase(phase)
            self.update_status_display(result)
            self.log_detection_result(result)
        except Exception as e:
            self.log_message(f"❌ 單幀處理失敗: {e}")

    def update_status_display(self, result):
        """更新狀態顯示"""
        # 更新狀態燈號（落地版簡化）
        decision = result.get("decision", "UNKNOWN")
        self.phase_indicator.setText(decision)

        # 設定狀態顏色（落地版：OPEN/CLOSED/UNKNOWN）
        phase_colors = {
            "OPEN": ("#10b981", "#064e3b"),      # 綠色 - 可下注
            "CLOSED": ("#dc2626", "#7f1d1d"),   # 紅色 - 不可下注
            "UNKNOWN": ("#6b7280", "#374151")   # 灰色 - 未知狀態
        }

        bg_color, text_color = phase_colors.get(decision, phase_colors["UNKNOWN"])
        self.phase_indicator.setStyleSheet(f"""
            QLabel {{
                background: {bg_color};
                color: white;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                min-width: 100px;
            }}
        """)

        # 更新數值顯示
        value_formats = {
            "decision": "{}",
            "ncc_qing": "{:.3f}",
            "hue": "{:.1f}°",
            "sat": "{:.3f}",
            "val": "{:.3f}",
            "in_green_gate": "{}",
            "open_counter": "{}",
            "close_counter": "{}",
            "open_hit": "{}"
        }

        for key, label in self.status_labels.items():
            if key in result:
                value = result[key]

                # 特殊處理布林值
                if key == "in_green_gate":
                    display_value = "✓" if value else "✗"
                elif key == "open_hit":
                    display_value = "✓" if value else "✗"
                else:
                    fmt = value_formats.get(key, "{}")
                    display_value = fmt.format(value)

                label.setText(display_value)

    def log_detection_result(self, result):
        """記錄檢測結果與決策理由"""
        timestamp = time.time()

        # 落地版日誌格式
        decision = result.get('decision', 'UNKNOWN')
        ncc_qing = result.get('ncc_qing', 0)
        hue = result.get('hue', 0)
        sat = result.get('sat', 0)
        val = result.get('val', 0)
        in_green = result.get('in_green_gate', False)
        open_counter = result.get('open_counter', '0/3')
        close_counter = result.get('close_counter', '0/2')
        reason = result.get('reason', 'Unknown')

        # 落地版日誌格式：專注於核心資訊
        log_line = f"[Overlay] hue={hue:.0f}/{sat:.2f}/{val:.2f} NCC請={ncc_qing:.2f} green={'✓' if in_green else '✗'} → {decision} (開{open_counter} 關{close_counter}) - {reason}"

        # 添加到緩衝區
        display_line = log_line
        self.log_buffer.append(display_line)

        # 更新 UI 日誌
        self.log_display.clear()
        self.log_display.append("\n".join(self.log_buffer))

        # 滾動到底部
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # 寫入完整日誌到檔案
        try:
            os.makedirs(os.path.dirname(OVERLAY_LOG_FILE), exist_ok=True)
            with open(OVERLAY_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception as e:
            pass  # 靜默處理文件寫入錯誤


    def export_log(self):
        """匯出日誌檔案"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "匯出檢測日誌",
                f"overlay_log_{time.strftime('%Y%m%d_%H%M%S')}.log",
                "Log Files (*.log);;All Files (*)"
            )

            if file_path:
                if os.path.exists(OVERLAY_LOG_FILE):
                    import shutil
                    shutil.copy2(OVERLAY_LOG_FILE, file_path)
                    self.log_message(f"✅ 日誌已匯出到: {os.path.basename(file_path)}")
                    QMessageBox.information(self, "成功", f"日誌已匯出到:\n{file_path}")
                else:
                    QMessageBox.warning(self, "警告", "沒有可匯出的日誌檔案")

        except Exception as e:
            self.log_message(f"❌ 匯出日誌失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"匯出日誌失敗:\n{e}")

    def clear_log(self):
        """清空日誌"""
        reply = QMessageBox.question(
            self, "確認", "確定要清空所有日誌嗎？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.log_buffer.clear()
            self.log_display.clear()

            # 清空日誌檔案
            try:
                with open(OVERLAY_LOG_FILE, "w", encoding="utf-8") as f:
                    f.write("")
                self.log_message("🗑️ 日誌已清空")
            except:
                pass

    def load_template(self, template_type):
        """載入模板"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"選擇「{template_type}」模板", TEMPLATES_DIR,
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )

        if file_path:
            self.template_paths[template_type] = file_path
            self.update_template_status()
            self.log_message(f"載入模板「{template_type}」: {os.path.basename(file_path)}")

    def update_template_status(self):
        """更新模板狀態"""
        loaded_templates = [k for k, v in self.template_paths.items() if v]

        if len(loaded_templates) == 3:
            self.template_status.setText("✅ 所有模板已載入")
            self.template_status.setStyleSheet("""
                QLabel {
                    background: #14532d;
                    color: #86efac;
                    padding: 4px;
                    border-radius: 4px;
                    font-size: 12px;
                }
            """)
        elif len(loaded_templates) > 0:
            self.template_status.setText(f"⚠️ 部分載入 ({len(loaded_templates)}/3)")
            self.template_status.setStyleSheet("""
                QLabel {
                    background: #78350f;
                    color: #fcd34d;
                    padding: 4px;
                    border-radius: 4px;
                    font-size: 12px;
                }
            """)
        else:
            self.template_status.setText("❌ 未載入模板")
            self.template_status.setStyleSheet("""
                QLabel {
                    background: #7f1d1d;
                    color: #fca5a5;
                    padding: 4px;
                    border-radius: 4px;
                    font-size: 12px;
                }
            """)

    def save_rois(self):
        """保存 ROI 和參數到 positions.json"""
        try:
            # 讀取現有配置
            positions_data = {}
            if os.path.exists(POSITIONS_FILE):
                with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                    positions_data = json.load(f)

            # 創建備份 (已停用)
            # if os.path.exists(POSITIONS_FILE):
            #     backup_name = f"positions.{time.strftime('%Y%m%d-%H%M')}.json.bak"
            #     backup_path = os.path.join("configs", backup_name)
            #     import shutil
            #     shutil.copy2(POSITIONS_FILE, backup_path)

            # 更新 ROI
            if "roi" not in positions_data:
                positions_data["roi"] = {}

            positions_data["roi"]["overlay"] = self.overlay_roi
            positions_data["roi"]["timer"] = self.timer_roi

            # 更新 overlay 參數
            if "overlay_params" not in positions_data:
                positions_data["overlay_params"] = {}

            positions_data["overlay_params"].update({
                "consecutive_required": self.consecutive_spin.value(),
                "ncc_threshold": self.ncc_threshold_spin.value(),
                "flicker_threshold": self.flicker_threshold_spin.value(),
                "timer_white_range": [self.timer_min_spin.value(), self.timer_max_spin.value()],
                "timer_interval_ms": self.timer_interval_spin.value(),
                "template_paths": self.template_paths.copy(),
                "source_mode": self.source_mode,
                "last_image_path": self.last_image_path
            })

            # 保存
            os.makedirs(os.path.dirname(POSITIONS_FILE), exist_ok=True)
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(positions_data, f, ensure_ascii=False, indent=2)

            self.log_message("✅ 配置保存成功")

            # 發送狀態更新事件
            has_roi = bool(self.overlay_roi and self.timer_roi)
            threshold = self.ncc_threshold_spin.value()
            APP_STATE.overlayChanged.emit({
                'has_roi': has_roi,
                'threshold': threshold,
                'ready': has_roi and threshold > 0
            })

            # 發送 Toast 通知
            emit_toast("Overlay settings saved successfully", "success")

            QMessageBox.information(self, "成功", "ROI 與檢測參數已保存到 positions.json")

        except Exception as e:
            self.log_message(f"❌ 保存配置失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"保存配置失敗:\n{e}")

    def load_positions(self):
        """載入位置配置和參數"""
        try:
            if os.path.exists(POSITIONS_FILE):
                with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 載入 ROI
                roi_data = data.get("roi", {})
                if "overlay" in roi_data:
                    self.overlay_roi = roi_data["overlay"]
                if "timer" in roi_data:
                    self.timer_roi = roi_data["timer"]

                # 載入檢測參數
                params = data.get("overlay_params", {})
                if params:
                    self.consecutive_spin.setValue(params.get("consecutive_required", 3))
                    self.ncc_threshold_spin.setValue(params.get("ncc_threshold", 0.6))
                    self.flicker_threshold_spin.setValue(params.get("flicker_threshold", 0.06))

                    timer_range = params.get("timer_white_range", [0.03, 0.20])
                    self.timer_min_spin.setValue(timer_range[0])
                    self.timer_max_spin.setValue(timer_range[1])

                    self.timer_interval_spin.setValue(params.get("timer_interval_ms", 120))

                    # 載入模板路徑
                    template_paths = params.get("template_paths", {})
                    self.template_paths.update(template_paths)
                    self.update_template_status()

                    # 載入來源模式與圖片路徑
                    self.source_mode = params.get("source_mode", "screen")
                    self.last_image_path = params.get("last_image_path")
                    if hasattr(self, 'src_image'):
                        self.src_image.setChecked(self.source_mode == "image")
                        self.src_screen.setChecked(self.source_mode != "image")
                        self.load_image_btn.setEnabled(self.source_mode == "image")
                        self.step_btn.setEnabled(self.source_mode == "image")

                self.log_message("📂 載入配置成功")

                # 發送初始狀態到 AppState
                has_roi = bool(self.overlay_roi and self.timer_roi)
                threshold = self.ncc_threshold_spin.value()
                APP_STATE.overlayChanged.emit({
                    'has_roi': has_roi,
                    'threshold': threshold,
                    'ready': has_roi and threshold > 0
                })

                # 同步 ROI 到預覽組件，並在需要時夾回邊界
                if hasattr(self, 'preview'):
                    bounds = self.preview._scene.sceneRect()
                    def clamp_rect(x, y, w, h):
                        r = QRectF(x, y, w, h)
                        if not bounds.isNull():
                            if r.left() < bounds.left():
                                r.moveLeft(bounds.left())
                            if r.top() < bounds.top():
                                r.moveTop(bounds.top())
                            if r.right() > bounds.right():
                                r.moveRight(bounds.right())
                            if r.bottom() > bounds.bottom():
                                r.moveBottom(bounds.bottom())
                            r.setWidth(max(20.0, min(r.width(), bounds.width())))
                            r.setHeight(max(20.0, min(r.height(), bounds.height())))
                        return r

                    self.preview.roi_items["overlay"].setRect(clamp_rect(
                        self.overlay_roi["x"], self.overlay_roi["y"], self.overlay_roi["w"], self.overlay_roi["h"]
                    ))
                    self.preview.roi_items["timer"].setRect(clamp_rect(
                        self.timer_roi["x"], self.timer_roi["y"], self.timer_roi["w"], self.timer_roi["h"]
                    ))

        except Exception as e:
            self.log_message(f"⚠️ 載入配置失敗: {e}")

    def on_roi_changed(self, roi_name: str, roi_dict: dict):
        """ROI 變更回調"""
        if roi_name == "overlay":
            self.overlay_roi = {
                "x": roi_dict["x"],
                "y": roi_dict["y"],
                "w": roi_dict["w"],
                "h": roi_dict["h"]
            }
        elif roi_name == "timer":
            self.timer_roi = {
                "x": roi_dict["x"],
                "y": roi_dict["y"],
                "w": roi_dict["w"],
                "h": roi_dict["h"]
            }

        # 如果檢測器存在，更新 ROI
        if self.detector:
            self.detector.set_rois(self.overlay_roi, self.timer_roi)

    def set_current_roi(self, roi_name: str):
        """設定當前編輯的 ROI"""
        if hasattr(self, 'preview'):
            self.preview.set_current_roi(roi_name)

    def update_timer_interval(self, value: int):
        """更新檢測間隔"""
        self.detection_timer.setInterval(value)
        self.log_message(f"檢測間隔更新為 {value}ms")

    def calculate_fps(self):
        """計算 FPS"""
        current_time = time.time()
        if hasattr(self, 'fps_last_time'):
            delta = current_time - self.fps_last_time
            if delta > 0:
                fps = 1.0 / delta
                self.fps_buffer.append(fps)

                # 計算平均 FPS
                if len(self.fps_buffer) > 0:
                    avg_fps = sum(self.fps_buffer) / len(self.fps_buffer)
                    self.fps_display.setText(f"{avg_fps:.1f}")

        self.fps_last_time = current_time

    def setup_shortcuts(self):
        """設定快捷鍵"""
        # O - 選擇 Overlay ROI
        overlay_shortcut = QShortcut(QKeySequence("O"), self)
        overlay_shortcut.activated.connect(lambda: self.overlay_radio.setChecked(True))

        # T - 選擇 Timer ROI
        timer_shortcut = QShortcut(QKeySequence("T"), self)
        timer_shortcut.activated.connect(lambda: self.timer_radio.setChecked(True))

        # S - 截取螢幕
        capture_shortcut = QShortcut(QKeySequence("S"), self)
        capture_shortcut.activated.connect(self.capture_screen)

        # Space - 開始/停止檢測
        toggle_shortcut = QShortcut(QKeySequence("Space"), self)
        toggle_shortcut.activated.connect(self.toggle_detection)

        # Esc - 停止檢測
        stop_shortcut = QShortcut(QKeySequence("Escape"), self)
        stop_shortcut.activated.connect(self.stop_detection)

    def health_check(self):
        """增強版健康檢查"""
        issues = []
        warnings = []

        # 檢查 ROI 尺寸和邊界
        if self.overlay_roi["w"] <= 0 or self.overlay_roi["h"] <= 0:
            issues.append("❌ Overlay ROI 尺寸無效")
        elif self.overlay_roi["w"] < 100 or self.overlay_roi["h"] < 30:
            warnings.append("⚠️ Overlay ROI 過小，可能影響檢測準確性")

        if self.timer_roi["w"] <= 0 or self.timer_roi["h"] <= 0:
            issues.append("❌ Timer ROI 尺寸無效")
        elif self.timer_roi["w"] < 50 or self.timer_roi["h"] < 50:
            warnings.append("⚠️ Timer ROI 過小，可能影響計時器檢測")

        # 檢查 ROI 邊界（如果有螢幕尺寸的話）
        if self.current_frame is not None:
            screen_h, screen_w = self.current_frame.shape[:2]

            if (self.overlay_roi["x"] + self.overlay_roi["w"] > screen_w or
                self.overlay_roi["y"] + self.overlay_roi["h"] > screen_h):
                issues.append("❌ Overlay ROI 超出螢幕邊界")

            if (self.timer_roi["x"] + self.timer_roi["w"] > screen_w or
                self.timer_roi["y"] + self.timer_roi["h"] > screen_h):
                issues.append("❌ Timer ROI 超出螢幕邊界")

        # 檢查 ROI 重疊
        ox1, oy1 = self.overlay_roi["x"], self.overlay_roi["y"]
        ox2, oy2 = ox1 + self.overlay_roi["w"], oy1 + self.overlay_roi["h"]
        tx1, ty1 = self.timer_roi["x"], self.timer_roi["y"]
        tx2, ty2 = tx1 + self.timer_roi["w"], ty1 + self.timer_roi["h"]

        if not (ox2 <= tx1 or tx2 <= ox1 or oy2 <= ty1 or ty2 <= oy1):
            warnings.append("⚠️ Overlay 和 Timer ROI 重疊，可能互相干擾")

        # 檢查參數範圍
        if self.consecutive_spin.value() < 2:
            warnings.append("⚠️ 平滑幀數過低，可能造成誤判")
        elif self.consecutive_spin.value() > 8:
            warnings.append("⚠️ 平滑幀數過高，可能反應遲緩")

        if self.ncc_threshold_spin.value() < 0.3:
            warnings.append("⚠️ NCC 門檻過低，可能誤判文字")
        elif self.ncc_threshold_spin.value() > 0.9:
            warnings.append("⚠️ NCC 門檻過高，可能錯失正確文字")

        if self.timer_interval_spin.value() < 100:
            warnings.append("⚠️ 檢測間隔過短，可能影響系統效能")

        # 檢查模板
        loaded_templates = [k for k, v in self.template_paths.items() if v and os.path.exists(v)]
        missing_templates = [k for k, v in self.template_paths.items() if v and not os.path.exists(v)]

        if missing_templates:
            issues.append(f"❌ 模板文件不存在: {', '.join(missing_templates)}")

        if len(loaded_templates) == 0:
            warnings.append("⚠️ 無模板載入，僅依賴顏色檢測（準確性較低）")
        elif len(loaded_templates) < 3:
            warnings.append(f"⚠️ 部分模板未載入 ({len(loaded_templates)}/3)，建議載入所有模板")

        # 檢查文件權限
        try:
            os.makedirs(os.path.dirname(OVERLAY_LOG_FILE), exist_ok=True)
            with open(OVERLAY_LOG_FILE, "a", encoding="utf-8") as f:
                f.write("")  # 測試寫入
        except Exception as e:
            issues.append(f"❌ 日誌文件無寫入權限: {e}")

        try:
            os.makedirs(os.path.dirname(POSITIONS_FILE), exist_ok=True)
            test_file = POSITIONS_FILE + ".test"
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("{}")
            os.remove(test_file)
        except Exception as e:
            issues.append(f"❌ 配置目錄無寫入權限: {e}")

        # 檢查螢幕截取功能
        try:
            app = QGuiApplication.instance()
            screen = app.primaryScreen()
            test_screenshot = screen.grabWindow(0, 0, 0, 1, 1)  # 最小截圖測試
            if test_screenshot.isNull():
                issues.append("❌ 螢幕截取功能異常")
        except Exception as e:
            issues.append(f"❌ 螢幕截取測試失敗: {e}")

        # 組合結果
        all_issues = issues + warnings
        severity_counts = {"critical": len(issues), "warning": len(warnings)}

        # 顯示結果
        if all_issues:
            result = f"健康檢查結果 (🚨{severity_counts['critical']} ⚠️{severity_counts['warning']}):\n\n"
            result += "\n".join(all_issues)

            if issues:
                result += "\n\n💡 建議修復所有❌項目後再開始檢測"

            if issues:
                QMessageBox.critical(self, "健康檢查", result)
            else:
                QMessageBox.warning(self, "健康檢查", result)
        else:
            QMessageBox.information(self, "健康檢查",
                "✅ 所有檢查項目正常\n\n系統已準備好進行可下注判斷檢測")

        for issue in all_issues:
            self.log_message(issue)

    def log_message(self, message):
        """記錄一般訊息"""
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        print(formatted)  # 也輸出到控制台