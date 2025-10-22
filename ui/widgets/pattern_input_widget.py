# ui/widgets/pattern_input_widget.py
"""Entry Pattern 輸入控件 + 語法幫助"""
from __future__ import annotations

import re
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDialog,
    QTextBrowser,
)


class PatternSyntaxHelpDialog(QDialog):
    """Pattern 語法說明對話框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Entry Pattern 語法說明")
        self.setMinimumSize(700, 600)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 說明文字 (支援 Markdown)
        help_text = QTextBrowser()
        help_text.setOpenExternalLinks(True)
        help_text.setStyleSheet("""
            QTextBrowser {
                background-color: #1f2937;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 16px;
                font-size: 11pt;
            }
        """)
        help_text.setMarkdown("""
# Entry Pattern 語法說明

## 基本格式
```
<歷史序列> then bet <投注目標>
```

---

## 符號說明

| 符號 | 意義 | 範例 |
|-----|------|------|
| `B` | 莊家 (Banker) | BB = 兩個莊 |
| `P` | 閒家 (Player) | PP = 兩個閒 |
| `T` | 和局 (Tie) | BT = 莊和 |

---

## 常用範例

### 1️⃣ 兩莊後押閒
```
BB then bet P
```
**說明:** 當連續開出兩個莊家,下一手押閒家
**適用:** 切斷長龍策略

---

### 2️⃣ 三閒後押莊
```
PPP then bet B
```
**說明:** 當連續開出三個閒家,下一手押莊家
**適用:** 反龍策略

---

### 3️⃣ 莊閒莊後押閒
```
BPB then bet P
```
**說明:** 當依序開出 莊→閒→莊,下一手押閒家
**適用:** 節奏型策略

---

### 4️⃣ 追長龍 (兩莊後繼續押莊)
```
BB then bet B
```
**說明:** 兩莊後繼續押莊,追隨趨勢
**適用:** 長龍策略

---

### 5️⃣ 閒閒莊後押莊
```
PPB then bet B
```
**說明:** 兩閒一莊後押莊
**適用:** 轉向策略

---

### 6️⃣ 兩莊後押和
```
BB then bet T
```
**說明:** 連續開出兩個莊家,下一手押和局
**適用:** 特殊押和策略

---

## 語法規則

✅ **大小寫不敏感**
`BB`、`bb`、`Bb` 都視為相同

✅ **必須包含 then bet**
`then` 和 `bet` 前後必須有空格

✅ **投注目標單一**
`bet` 後只能接一個符號 (B、P 或 T)

✅ **支援押和**
可以使用 `then bet T` 押和局

---

## 進階技巧

### 使用較長序列
```
BBBB then bet P
```
等待更確定的信號(四莊)再進場

### 混合序列
```
BPBP then bet B
```
偵測跳牌節奏後進場

---

## 常見錯誤

| 錯誤寫法 | 原因 | 正確寫法 |
|---------|------|---------|
| `BB bet P` | 缺少 then | `BB then bet P` |
| `BB thenbet P` | then bet 沒空格 | `BB then bet P` |
| `BB then P` | 缺少 bet | `BB then bet P` |
| `BB then bet BP` | 目標多個 | 分成兩個策略 |

---

## 提示

💡 **從簡單開始**: 新手建議先用 `BB then bet P` 或 `PP then bet B`
💡 **測試驗證**: 使用策略模擬功能測試效果
💡 **配合去重**: 記得設定去重模式避免重複進場

""")

        layout.addWidget(help_text)

        # 關閉按鈕
        close_btn = QPushButton("關閉")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #1f2937;
                color: #f3f4f6;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class PatternInputWidget(QWidget):
    """Entry Pattern 輸入框 + 語法幫助 + 快速範例"""

    pattern_changed = Signal(str)  # 當 pattern 改變時發送信號

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 標題列
        header = QHBoxLayout()
        label = QLabel("Pattern (進場條件):")
        label.setStyleSheet("font-weight: bold; color: #f3f4f6;")

        help_btn = QPushButton("❓ 語法說明")
        help_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e40af;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #1e3a8a;
            }
        """)
        help_btn.setMaximumWidth(100)
        help_btn.clicked.connect(self.show_syntax_help)

        header.addWidget(label)
        header.addStretch()
        header.addWidget(help_btn)

        layout.addLayout(header)

        # 輸入框 + 即時驗證
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("例: BB then bet P")
        self.pattern_input.setStyleSheet("""
            QLineEdit {
                background-color: #1f2937;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 6px;
                padding: 8px;
                font-size: 11pt;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        self.pattern_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.pattern_input)

        # 驗證提示
        self.validation_label = QLabel()
        self.validation_label.setStyleSheet("color: #9ca3af; font-size: 10pt;")
        layout.addWidget(self.validation_label)

        # 快速範例
        examples_label = QLabel("快速範例:")
        examples_label.setStyleSheet("font-weight: bold; color: #d1d5db; font-size: 10pt;")
        layout.addWidget(examples_label)

        examples_flow = QHBoxLayout()
        examples_flow.setSpacing(8)

        examples = [
            ("兩莊押閒", "BB then bet P"),
            ("兩閒押莊", "PP then bet B"),
            ("三莊押閒", "BBB then bet P"),
            ("追莊龍", "BB then bet B"),
            ("兩莊押和", "BB then bet T"),
        ]

        for display, pattern in examples:
            btn = QPushButton(display)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 6px 12px;
                    border-radius: 4px;
                    background-color: #1f2937;
                    color: #d1d5db;
                    border: 1px solid #4b5563;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #4b5563;
                    border-color: #6b7280;
                }
            """)
            btn.clicked.connect(lambda checked, p=pattern: self.set_pattern(p))
            examples_flow.addWidget(btn)

        examples_flow.addStretch()
        layout.addLayout(examples_flow)

    def _on_text_changed(self, text: str):
        """當文字改變時驗證並發送信號"""
        self.validate_pattern(text)
        self.pattern_changed.emit(text)

    def validate_pattern(self, text: str):
        """即時驗證語法"""
        if not text:
            self.validation_label.setText("")
            return

        # 簡單正則驗證 - 現在支援押和 (T)
        pattern = r"^[BPT]+\s+then\s+bet\s+[BPT]$"

        if re.match(pattern, text, re.IGNORECASE):
            self.validation_label.setText("✅ 語法正確")
            self.validation_label.setStyleSheet("color: #10b981; font-size: 10pt;")
        else:
            self.validation_label.setText("⚠️ 語法可能有誤,請參考語法說明")
            self.validation_label.setStyleSheet("color: #f59e0b; font-size: 10pt;")

    def show_syntax_help(self):
        """顯示語法說明對話框"""
        dialog = PatternSyntaxHelpDialog(self)
        dialog.exec_()

    def get_pattern(self) -> str:
        """取得 Pattern"""
        return self.pattern_input.text().strip()

    def set_pattern(self, pattern: str):
        """設定 Pattern"""
        self.pattern_input.setText(pattern)
