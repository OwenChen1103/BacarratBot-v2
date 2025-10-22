"""視覺化 Pattern 建構器 - 輕量卡片樣式"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QRadioButton,
    QButtonGroup,
    QSizePolicy,
)


THEME = {
    "background": "#0f172a",
    "surface": "#131f33",
    "surface_alt": "#182538",
    "surface_subtle": "#1f2f45",
    "overlay": "rgba(255, 255, 255, 0.02)",
    "border": "rgba(255, 255, 255, 0.07)",
    "border_focus": "#4f8dff",
    "primary": "#2563eb",
    "primary_soft": "#60a5fa",
    "text_primary": "#e7edf6",
    "text_secondary": "#9eabc6",
    "caption": "#7c8aa6",
    "danger": "#f87171",
    "danger_hover": "#dc2626",
    "banker": "#ef4444",
    "player": "#3b82f6",
    "tie": "#22c55e",
}


class OutcomeButton(QPushButton):
    """開牌結果按鈕"""

    def __init__(self, outcome: str, parent: Optional[QWidget] = None):
        super().__init__(outcome, parent)
        self.outcome = outcome
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def _apply_style(self):
        colors = {
            "莊": THEME["banker"],
            "閒": THEME["player"],
            "和": THEME["tie"],
        }
        hover = {
            "莊": "#ff6b6b",
            "閒": "#6fa7ff",
            "和": "#3edb7c",
        }
        pressed = {
            "莊": "#d92424",
            "閒": "#1d4ed8",
            "和": "#16a34a",
        }

        base = colors.get(self.outcome, "#6b7280")
        hover_base = hover.get(self.outcome, "#9ca3af")
        pressed_base = pressed.get(self.outcome, "#4b5563")

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {base};
                color: #ffffff;
                border: none;
                border-radius: 9px;
                padding: 6px 14px;
                font-size: 12.5pt;
                font-weight: 600;
                min-width: 64px;
                min-height: 40px;
            }}
            QPushButton:hover {{
                background-color: {hover_base};
            }}
            QPushButton:pressed {{
                background-color: {pressed_base};
            }}
        """)


class SequenceSlot(QFrame):
    """序列插槽"""

    clicked = Signal(int)

    COLORS = {
        "莊": THEME["banker"],
        "閒": THEME["player"],
        "和": THEME["tie"],
    }

    def __init__(self, index: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.index = index
        self.outcome: Optional[str] = None
        self._selected = False
        self._build()

    def _build(self):
        self.setMinimumSize(56, 56)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self.label = QLabel("[ + ]")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(f"color: {THEME['caption']}; font-size: 11pt; border: none;")
        layout.addWidget(self.label)

        self.mousePressEvent = lambda e: self.clicked.emit(self.index)
        self._refresh_style()

    def set_outcome(self, outcome: Optional[str]):
        self.outcome = outcome
        if outcome:
            self.label.setText(outcome)
            self.label.setStyleSheet("color: #ffffff; font-size: 15pt; font-weight: 700; border: none;")
        else:
            self.label.setText("[ + ]")
            self.label.setStyleSheet(f"color: {THEME['caption']}; font-size: 11pt; border: none;")
        self._refresh_style()

    def clear(self):
        self.set_outcome(None)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self):
        border = THEME["border_focus"] if self._selected else THEME["border"]
        if self.outcome:
            fill = self.COLORS.get(self.outcome, THEME["surface_subtle"])
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {fill};
                    border: 1px solid {border};
                    border-radius: 9px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {THEME["overlay"]};
                    border: 1px solid {border};
                    border-radius: 9px;
                }}
                QFrame:hover {{
                    border-color: {THEME["primary_soft"]};
                    background-color: rgba(79, 141, 255, 0.10);
                }}
            """)


class VisualPatternBuilder(QWidget):
    """視覺化 Pattern 建構器"""

    pattern_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.sequence_slots: List[SequenceSlot] = []
        self.current_slot_index = 0
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("visualPatternBuilder")
        self.setStyleSheet(f"""
            QWidget#visualPatternBuilder {{
                background-color: {THEME["background"]};
            }}
            QLabel {{
                color: {THEME["text_primary"]};
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_sequence_section())
        layout.addWidget(self._build_target_section())
        layout.addWidget(self._build_preview_section())
        layout.addStretch()

    # ------------------------------------------------------------------
    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME["surface"]};
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
                padding: 12px 16px;
            }}
        """)

        container = QVBoxLayout(frame)
        container.setSpacing(4)

        title = QLabel("視覺化進場條件建構器")
        title.setStyleSheet(
            f"font-size: 12.5pt; font-weight: 600; color: {THEME['text_primary']}; letter-spacing: 0.2px;"
        )
        container.addWidget(title)

        subtitle = QLabel("組合牌局趨勢並快速生成策略語法，保持一致的視覺節奏。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {THEME['caption']}; font-size: 9.5pt; line-height: 140%;")
        container.addWidget(subtitle)

        return frame

    def _build_sequence_section(self) -> QFrame:
        frame = self._create_outer_card()
        layout = QVBoxLayout(frame)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addLayout(self._create_section_header(
            "建立進場序列",
            "依序點擊莊 / 閒 / 和，描述下一輪觸發條件。"
        ))

        # Outcome buttons
        btn_card = self._create_inner_card()
        btn_layout = QVBoxLayout(btn_card)
        btn_layout.setSpacing(4)
        btn_layout.setContentsMargins(10, 10, 10, 10)

        btn_label = QLabel("選擇開牌結果")
        btn_label.setAlignment(Qt.AlignCenter)
        btn_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 9.5pt; font-weight: 600;")
        btn_layout.addWidget(btn_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setAlignment(Qt.AlignCenter)
        for outcome in ["莊", "閒", "和"]:
            button = OutcomeButton(outcome)
            button.clicked.connect(lambda checked=False, o=outcome: self._add_outcome(o))
            btn_row.addWidget(button)
        btn_layout.addLayout(btn_row)
        layout.addWidget(btn_card)

        # Slots
        slots_card = self._create_inner_card()
        slots_layout = QVBoxLayout(slots_card)
        slots_layout.setSpacing(4)
        slots_layout.setContentsMargins(10, 10, 10, 10)

        slots_label = QLabel("目前序列")
        slots_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 9.5pt; font-weight: 600;")
        slots_layout.addWidget(slots_label, alignment=Qt.AlignLeft)

        slots_widget = QWidget()
        self.slots_layout = QHBoxLayout(slots_widget)
        self.slots_layout.setSpacing(6)
        self.slots_layout.setContentsMargins(0, 0, 0, 0)
        self.slots_layout.setAlignment(Qt.AlignCenter)

        for i in range(6):
            slot = SequenceSlot(i)
            slot.clicked.connect(self._on_slot_clicked)
            self.sequence_slots.append(slot)
            self.slots_layout.addWidget(slot)

        slots_layout.addWidget(slots_widget)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.clear_btn = QPushButton("清空序列")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 5px 14px;
                color: {THEME["danger"]};
                background: transparent;
                border: 1px solid {THEME["danger"]};
                border-radius: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: rgba(248, 113, 113, 0.12);
                color: {THEME["danger_hover"]};
                border-color: {THEME["danger_hover"]};
            }}
        """)
        self.clear_btn.clicked.connect(self._clear_sequence)
        controls.addWidget(self.clear_btn, alignment=Qt.AlignLeft)
        controls.addStretch()
        slots_layout.addLayout(controls)

        layout.addWidget(slots_card)
        self._set_active_slot(0)
        return frame

    def _build_target_section(self) -> QFrame:
        frame = self._create_outer_card()
        layout = QVBoxLayout(frame)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addLayout(self._create_section_header(
            "選擇下一手押注對象",
            "在序列成立後，定義自動下注的方位。"
        ))

        target_card = self._create_inner_card()
        target_layout = QHBoxLayout(target_card)
        target_layout.setSpacing(6)
        target_layout.setContentsMargins(10, 10, 10, 10)

        self.target_group = QButtonGroup(self)
        self.radio_player = QRadioButton("押閒")
        self.radio_banker = QRadioButton("押莊")
        self.radio_tie = QRadioButton("押和")
        self.radio_player.setChecked(True)

        for radio in (self.radio_player, self.radio_banker, self.radio_tie):
            radio.setCursor(Qt.PointingHandCursor)
            radio.setStyleSheet(f"""
                QRadioButton {{
                    color: {THEME["text_secondary"]};
                    font-size: 9.5pt;
                    padding: 5px 12px;
                    border-radius: 10px;
                    border: 1px solid {THEME["border"]};
                }}
                QRadioButton::indicator {{
                    width: 0px;
                    height: 0px;
                }}
                QRadioButton:hover {{
                    border-color: {THEME["primary_soft"]};
                    color: {THEME["text_primary"]};
                    background: rgba(96, 165, 250, 0.08);
                }}
                QRadioButton:checked {{
                    color: {THEME["text_primary"]};
                    border-color: {THEME["primary"]};
                    font-weight: 600;
                    background: rgba(37, 99, 235, 0.16);
                }}
            """)
            self.target_group.addButton(radio)
            radio.toggled.connect(self._update_pattern)
            target_layout.addWidget(radio)

        target_layout.addStretch()
        layout.addWidget(target_card)
        return frame

    def _build_preview_section(self) -> QFrame:
        frame = self._create_outer_card()
        layout = QVBoxLayout(frame)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addLayout(self._create_section_header(
            "語法預覽",
            "檢視程式碼片段與白話說明，確認條件是否正確。"
        ))

        preview_card = self._create_inner_card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setSpacing(6)
        preview_layout.setContentsMargins(10, 10, 10, 10)

        preview_title = QLabel("自動生成語法")
        preview_title.setStyleSheet(f"font-weight: 600; color: {THEME['text_secondary']}; font-size: 9.5pt;")
        preview_layout.addWidget(preview_title)

        self.pattern_preview = QLabel("請先建立開牌序列")
        self.pattern_preview.setWordWrap(True)
        self.pattern_preview.setStyleSheet(f"""
            QLabel {{
                color: {THEME["text_primary"]};
                font-size: 11pt;
                font-family: 'Consolas', 'Courier New', monospace;
                background-color: {THEME["surface_subtle"]};
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
                padding: 10px 12px;
            }}
        """)
        preview_layout.addWidget(self.pattern_preview)

        explanation_title = QLabel("白話說明")
        explanation_title.setStyleSheet(f"font-weight: 600; color: {THEME['text_secondary']}; font-size: 9.5pt;")
        preview_layout.addWidget(explanation_title)

        self.explanation_label = QLabel("尚未設定")
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setStyleSheet(f"""
            QLabel {{
                color: {THEME["text_primary"]};
                font-size: 9.5pt;
                background-color: {THEME["surface_subtle"]};
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
                padding: 10px 12px;
            }}
        """)
        preview_layout.addWidget(self.explanation_label)

        layout.addWidget(preview_card)
        return frame

    def _create_outer_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME["surface"]};
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
            }}
        """)
        return card

    def _create_inner_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME["surface_alt"]};
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
            }}
        """)
        return card

    def _create_section_header(self, title: str, subtitle: str) -> QVBoxLayout:
        wrapper = QVBoxLayout()
        wrapper.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: 11pt; font-weight: 600; color: {THEME['text_primary']}; letter-spacing: 0.15px;"
        )
        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 9.2pt; line-height: 135%;")

        wrapper.addWidget(title_label)
        wrapper.addWidget(subtitle_label)
        return wrapper

    # ------------------------------------------------------------------
    def _on_slot_clicked(self, index: int):
        self._set_active_slot(index)

    def _add_outcome(self, outcome: str):
        current = self.sequence_slots[self.current_slot_index]
        if current.outcome is None:
            current.set_outcome(outcome)
            self._advance_active_slot()
            self._update_pattern()
            return

        for idx, slot in enumerate(self.sequence_slots):
            if slot.outcome is None:
                slot.set_outcome(outcome)
                self._set_active_slot(idx)
                self._advance_active_slot()
                self._update_pattern()
                return

    def _clear_sequence(self):
        for slot in self.sequence_slots:
            slot.clear()
        self._set_active_slot(0)
        self._update_pattern()

    def _update_pattern(self):
        mapping = {"莊": "B", "閒": "P", "和": "T"}
        sequence = [mapping[slot.outcome] for slot in self.sequence_slots if slot.outcome]

        if not sequence:
            self.pattern_preview.setText("請先建立開牌序列")
            self.explanation_label.setText("尚未設定")
            self.pattern_changed.emit("")
            return

        if self.radio_player.isChecked():
            target = "P"
        elif self.radio_banker.isChecked():
            target = "B"
        else:
            target = "T"

        pattern = f"{''.join(sequence)} then bet {target}"
        self.pattern_preview.setText(pattern)
        self.explanation_label.setText(self._generate_explanation(sequence, target))
        self.pattern_changed.emit(pattern)

    def _generate_explanation(self, sequence: List[str], target: str) -> str:
        reverse = {"B": "莊", "P": "閒", "T": "和"}
        seq_desc = "".join(reverse[ch] for ch in sequence)
        target_desc = {"P": "閒家", "B": "莊家", "T": "和局"}[target]

        if len(set(sequence)) == 1:
            what = reverse[sequence[0]]
            return f"當連續開出 {len(sequence)} 次{what}時，下一手押 {target_desc}"
        return f"當依序開出「{seq_desc}」時，下一手押 {target_desc}"

    def get_pattern(self) -> str:
        mapping = {"莊": "B", "閒": "P", "和": "T"}
        sequence = [mapping[slot.outcome] for slot in self.sequence_slots if slot.outcome]
        if not sequence:
            return ""

        if self.radio_player.isChecked():
            target = "P"
        elif self.radio_banker.isChecked():
            target = "B"
        else:
            target = "T"
        return f"{''.join(sequence)} then bet {target}"

    def set_pattern(self, pattern: str):
        if not pattern:
            self._clear_sequence()
            return

        try:
            parts = pattern.upper().split(" THEN BET ")
            if len(parts) != 2:
                return
            sequence_str, target = parts[0].strip(), parts[1].strip()
            self._clear_sequence()

            mapping = {"B": "莊", "P": "閒", "T": "和"}
            for idx, ch in enumerate(sequence_str):
                if idx < len(self.sequence_slots) and ch in mapping:
                    self.sequence_slots[idx].set_outcome(mapping[ch])

            if target == "P":
                self.radio_player.setChecked(True)
            elif target == "B":
                self.radio_banker.setChecked(True)
            elif target == "T":
                self.radio_tie.setChecked(True)

            self._advance_active_slot()
            self._update_pattern()
        except Exception as exc:
            print(f"解析 pattern 失敗: {exc}")
            self._clear_sequence()

    def _set_active_slot(self, index: int):
        self.current_slot_index = max(0, min(index, len(self.sequence_slots) - 1))
        for idx, slot in enumerate(self.sequence_slots):
            slot.set_selected(idx == self.current_slot_index)

    def _advance_active_slot(self):
        for idx, slot in enumerate(self.sequence_slots):
            if slot.outcome is None:
                self._set_active_slot(idx)
                return
        self._set_active_slot(len(self.sequence_slots) - 1)
