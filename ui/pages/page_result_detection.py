# ui/pages/page_result_detection.py
"""
珠盤檢測配置頁面

配置珠盤 (Bead Plate / 珠路圖) 的檢測區域
使用差異檢測 + HSV 顏色識別自動辨識新出現的珠子
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np
import pyautogui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QMessageBox, QFileDialog,
    QSizePolicy, QScrollArea, QFrame, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
    QSplitter
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QBrush, QCursor
)

from ..app_state import emit_toast

CONFIG_FILE = "configs/bead_plate_detection.json"


class ResultROIItem(QGraphicsRectItem):
    """結果 ROI 矩形（可拖動調整）"""

    HANDLE_SIZE = 8.0

    def __init__(self, bounds_rect: QRectF):
        super().__init__(QRectF(100, 100, 300, 100))
        self.setZValue(10)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self._bounds = bounds_rect
        self._dragging = None
        self._start_rect = QRectF(self.rect())
        self._start_pos = QPointF()

    def set_bounds(self, r: QRectF):
        self._bounds = QRectF(r)
        self._clamp()

    def paint(self, painter: QPainter, option, widget=None):
        r = self.rect()

        # 繪製矩形框
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#22c55e"), 3)
        pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)

        # 半透明填充
        fill_color = QColor("#22c55e")
        fill_color.setAlpha(30)
        painter.setBrush(QBrush(fill_color))
        painter.drawRect(r)

        # 標籤
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#22c55e")))
        fm = painter.fontMetrics()
        label_text = "結果顯示區域"
        tw = fm.horizontalAdvance(label_text) + 16
        th = fm.height() + 8
        label_rect = QRectF(r.left() + 4, r.top() + 4, tw, th)
        painter.drawRoundedRect(label_rect, 4, 4)
        painter.setPen(QColor("white"))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label_text)
        painter.restore()

        # 四角控制點
        painter.setBrush(QBrush(QColor("#22c55e")))
        painter.setPen(QPen(QColor("white"), 1))
        for pt in self._corner_points(r):
            s = self.HANDLE_SIZE
            painter.drawEllipse(QRectF(pt.x() - s/2, pt.y() - s/2, s, s))

    def _corner_points(self, r: QRectF):
        return [r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()]

    def _hit_handle(self, pos: QPointF) -> Optional[str]:
        corners = ["tl", "tr", "bl", "br"]
        for name, pt in zip(corners, self._corner_points(self.rect())):
            if QRectF(pt.x() - 10, pt.y() - 10, 20, 20).contains(pos):
                return name
        if self.rect().contains(pos):
            return "move"
        return None

    def hoverMoveEvent(self, event):
        hit = self._hit_handle(event.pos())
        if hit == "tl" or hit == "br":
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif hit == "tr" or hit == "bl":
            self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif hit == "move":
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mousePressEvent(self, event):
        self._dragging = self._hit_handle(event.pos())
        self._start_rect = QRectF(self.rect())
        self._start_pos = QPointF(event.pos())
        if self._dragging == "move":
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return

        r = QRectF(self._start_rect)
        delta = event.pos() - self._start_pos

        if self._dragging == "move":
            r.moveTopLeft(r.topLeft() + delta)
        elif self._dragging == "tl":
            r.setTopLeft(r.topLeft() + delta)
        elif self._dragging == "tr":
            r.setTopRight(r.topRight() + delta)
        elif self._dragging == "bl":
            r.setBottomLeft(r.bottomLeft() + delta)
        elif self._dragging == "br":
            r.setBottomRight(r.bottomRight() + delta)

        self.setRect(r.normalized())
        self._clamp()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = None
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self._clamp()
        event.accept()

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

        # 最小尺寸 50x30
        if r.width() < 50:
            r.setWidth(50)
        if r.height() < 30:
            r.setHeight(30)

        self.setRect(r)


class TemplatePreview(QFrame):
    """模板預覽小卡片"""

    def __init__(self, template_type: str, display_name: str, color: str, parent=None):
        super().__init__(parent)
        self.template_type = template_type
        self.display_name = display_name
        self.template_path = None

        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet(f"border: 2px solid {color}; border-radius: 6px; padding: 8px;")
        self.setMaximumWidth(200)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # 標題
        title = QLabel(display_name)
        title.setStyleSheet(f"color: {color}; font-weight: bold; border: none; padding: 0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 預覽
        self.preview_label = QLabel("未選擇")
        self.preview_label.setMinimumSize(150, 60)
        self.preview_label.setMaximumSize(180, 80)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background: #f3f4f6; border: 1px dashed #d1d5db; color: #9ca3af;")
        layout.addWidget(self.preview_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 尺寸
        self.info_label = QLabel("-")
        self.info_label.setStyleSheet("color: #6b7280; font-size: 11px; border: none; padding: 0;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)

        # 選擇按鈕
        self.btn_select = QPushButton("選擇")
        self.btn_select.clicked.connect(self.select_template)
        self.btn_select.setMaximumWidth(120)
        layout.addWidget(self.btn_select, alignment=Qt.AlignmentFlag.AlignCenter)

    def select_template(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"選擇 {self.display_name} 模板", "", "圖片 (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.set_template(file_path)

    def set_template(self, file_path: str):
        try:
            img = cv2.imread(file_path)
            if img is None:
                raise ValueError("無法讀取圖片")

            self.template_path = file_path
            h, w = img.shape[:2]

            # 縮放預覽
            max_w, max_h = 180, 80
            scale = min(max_w / w, max_h / h, 1.0)
            if scale < 1.0:
                img = cv2.resize(img, (int(w * scale), int(h * scale)))

            # 轉換為 QPixmap
            h2, w2 = img.shape[:2]
            q_img = QImage(img.data, w2, h2, 3 * w2, QImage.Format.Format_RGB888)
            q_img = q_img.rgbSwapped()
            pixmap = QPixmap.fromImage(q_img)

            self.preview_label.setPixmap(pixmap)
            self.preview_label.setStyleSheet("background: white; border: 1px solid #d1d5db;")
            self.info_label.setText(f"{w}x{h}")

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"載入失敗: {e}")

    def load_from_config(self, path: str):
        if os.path.exists(path):
            self.set_template(path)


class PageResultDetection(QWidget):
    """珠盤檢測配置頁面"""

    def __init__(self):
        super().__init__()

        self.screenshot = None
        self.scene = QGraphicsScene()
        self.pixmap_item = None
        self.roi_item = None

        self._init_ui()
        self._load_config()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 說明
        info_group = QGroupBox("🎯 珠盤檢測設定")
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "此頁面用於設定珠盤（珠路圖）的檢測區域。\n\n"
            "檢測原理：\n"
            "• 使用差異檢測自動識別新出現的珠子\n"
            "• 使用 HSV 顏色識別判斷莊/閒/和\n"
            "• 自動過濾歷史珠子，只檢測新增的珠子\n\n"
            "步驟：\n"
            "1. 點擊「截取螢幕」按鈕截取遊戲畫面\n"
            "2. 拖動綠色框到左下角的珠盤區域（包含整個珠路圖）\n"
            "3. 點擊「保存配置」"
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # ROI 設定區域
        roi_group = QGroupBox("📍 珠盤 ROI 設定")
        roi_layout = QVBoxLayout()

        # 按鈕
        btn_layout = QHBoxLayout()
        self.btn_screenshot = QPushButton("📸 截取螢幕")
        self.btn_screenshot.clicked.connect(self._take_screenshot)
        btn_layout.addWidget(self.btn_screenshot)

        self.btn_reset = QPushButton("🔄 重置位置")
        self.btn_reset.clicked.connect(self._reset_roi)
        self.btn_reset.setEnabled(False)
        btn_layout.addWidget(self.btn_reset)

        btn_layout.addStretch()
        roi_layout.addLayout(btn_layout)

        # 圖形視圖
        self.view = QGraphicsView(self.scene)
        self.view.setMinimumSize(600, 400)
        roi_layout.addWidget(self.view)

        # 座標顯示
        self.coord_label = QLabel("ROI: 未設定")
        self.coord_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        roi_layout.addWidget(self.coord_label)

        roi_group.setLayout(roi_layout)
        layout.addWidget(roi_group)

        # 底部按鈕
        bottom_layout = QHBoxLayout()

        self.btn_save = QPushButton("💾 保存配置")
        self.btn_save.clicked.connect(self._save_config)
        self.btn_save.setMinimumWidth(150)
        bottom_layout.addWidget(self.btn_save)

        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)

        # 提示
        tip_label = QLabel(
            "💡 提示：框選整個珠盤區域（包含所有珠子），系統會自動檢測新出現的珠子"
        )
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(tip_label)

    def _take_screenshot(self):
        """直接截圖，不顯示對話框"""
        try:
            # 直接截圖，不需要隱藏視窗或等待
            screenshot = pyautogui.screenshot()
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            self.screenshot = img
            self._display_screenshot()

            emit_toast("success", "截圖成功", "已捕獲螢幕畫面")

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"截圖失敗: {e}")
            emit_toast("error", "截圖失敗", str(e))

    def _display_screenshot(self):
        if self.screenshot is None:
            return

        h, w = self.screenshot.shape[:2]
        q_img = QImage(self.screenshot.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        q_img = q_img.rgbSwapped()
        pixmap = QPixmap.fromImage(q_img)

        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(0, 0, w, h)

        # 建立單一 ROI
        bounds = QRectF(0, 0, w, h)
        self.roi_item = ResultROIItem(bounds)

        # 從配置載入位置，或使用預設
        x = w // 2 - 150
        y = h // 2 - 50
        self.roi_item.setRect(QRectF(x, y, 300, 100))

        self.scene.addItem(self.roi_item)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        self.btn_reset.setEnabled(True)
        self._update_coord_label()

    def _reset_roi(self):
        if self.screenshot is None or self.roi_item is None:
            return

        h, w = self.screenshot.shape[:2]
        x = w // 2 - 150
        y = h // 2 - 50
        self.roi_item.setRect(QRectF(x, y, 300, 100))
        self._update_coord_label()

    def _update_coord_label(self):
        if self.roi_item:
            r = self.roi_item.rect()
            self.coord_label.setText(
                f"ROI: ({int(r.x())}, {int(r.y())}) {int(r.width())}x{int(r.height())}"
            )

    def _save_config(self):
        try:
            # 檢查 ROI 是否已設置
            if not self.roi_item:
                QMessageBox.warning(self, "警告", "請先截取螢幕並設定珠盤 ROI 區域")
                return

            # 收集珠盤 ROI
            r = self.roi_item.rect()
            bead_plate_roi = {
                "x": int(r.x()),
                "y": int(r.y()),
                "w": int(r.width()),
                "h": int(r.height())
            }

            # 讀取或建立配置
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            # 更新珠盤 ROI
            config["bead_plate_roi"] = bead_plate_roi

            # 確保檢測配置存在
            if "detection_config" not in config:
                config["detection_config"] = {
                    "check_interval_ms": 200,
                    "consecutive_required": 3,
                    "cooldown_ms": 5000,
                    "diff_threshold": 20,
                    "min_change_area": 50,
                    "max_change_area": 2000,
                    "banker_hsv_range": [[0, 50, 50], [10, 255, 255]],
                    "player_hsv_range": [[100, 50, 50], [130, 255, 255]],
                    "tie_hsv_range": [[35, 50, 50], [85, 255, 255]],
                    "blackout_threshold": 15,
                    "whitewash_threshold": 240,
                    "abnormal_pixel_ratio": 0.9
                }

            # 保存
            Path(CONFIG_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            emit_toast("success", "保存成功", "珠盤檢測配置已保存")
            QMessageBox.information(self, "成功", f"配置已保存到 {CONFIG_FILE}")

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"保存失敗: {e}")

    def _load_config(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                return

            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 載入珠盤 ROI
            bead_plate_roi = config.get("bead_plate_roi", {})
            if bead_plate_roi and all(k in bead_plate_roi for k in ["x", "y", "w", "h"]):
                r = bead_plate_roi
                self.coord_label.setText(
                    f"珠盤 ROI: ({r['x']}, {r['y']}) {r['w']}x{r['h']}"
                )

        except Exception as e:
            print(f"載入配置失敗: {e}")
