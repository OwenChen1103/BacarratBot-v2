# src/autobet/chip_profile_manager.py
"""
籌碼組合管理器
負責載入、保存、驗證 Chip Profile
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .chip_planner import Chip

logger = logging.getLogger(__name__)


@dataclass
class ChipProfile:
    """籌碼組合檔"""
    profile_name: str
    provider: str = "WG/BG"
    table_type: str = "standard"
    chips: List[Chip] = field(default_factory=list)
    bet_positions: Dict[str, Dict] = field(default_factory=dict)
    constraints: Dict[str, int] = field(default_factory=dict)
    created_at: str = ""
    last_updated: str = ""

    def get_calibrated_chips(self) -> List[Chip]:
        """獲取已校準的籌碼"""
        return [chip for chip in self.chips if chip.calibrated]

    def get_chip_by_slot(self, slot: int) -> Optional[Chip]:
        """根據槽位獲取籌碼"""
        for chip in self.chips:
            if chip.slot == slot:
                return chip
        return None

    def get_bet_position(self, name: str) -> Optional[Dict]:
        """獲取下注位置"""
        return self.bet_positions.get(name)

    def is_position_calibrated(self, name: str) -> bool:
        """檢查位置是否已校準"""
        pos = self.get_bet_position(name)
        return pos and pos.get("calibrated", False)


@dataclass
class ValidationResult:
    """驗證結果"""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class ChipProfileManager:
    """籌碼組合管理器"""

    DEFAULT_PROFILE_DIR = Path("configs/chip_profiles")
    DEFAULT_PROFILE_NAME = "default"

    def __init__(self, profile_dir: Optional[Path] = None):
        """
        初始化管理器

        Args:
            profile_dir: 配置檔案目錄，預設為 configs/chip_profiles
        """
        self.profile_dir = profile_dir or self.DEFAULT_PROFILE_DIR
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.current_profile: Optional[ChipProfile] = None

        logger.info(f"ChipProfileManager 初始化: {self.profile_dir}")

    def load_profile(self, name: str = DEFAULT_PROFILE_NAME) -> ChipProfile:
        """
        載入籌碼組合

        Args:
            name: 組合名稱

        Returns:
            ChipProfile
        """
        profile_path = self.profile_dir / f"{name}.json"

        if not profile_path.exists():
            logger.warning(f"Profile 不存在: {profile_path}，使用預設值")
            return self._create_default_profile()

        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            profile = self._parse_profile(data)
            self.current_profile = profile

            logger.info(f"載入 Profile: {profile.profile_name}")
            logger.info(f"  可用籌碼: {len(profile.get_calibrated_chips())} / {len(profile.chips)}")

            return profile

        except Exception as e:
            logger.error(f"載入 Profile 失敗: {e}")
            return self._create_default_profile()

    def save_profile(self, profile: ChipProfile, name: Optional[str] = None) -> bool:
        """
        保存籌碼組合

        Args:
            profile: 要保存的組合
            name: 檔案名稱（不含副檔名），預設使用 profile.profile_name

        Returns:
            是否成功
        """
        if name is None:
            # 從 profile_name 提取檔案名稱
            name = profile.profile_name.replace(" ", "_").lower()

        profile_path = self.profile_dir / f"{name}.json"

        try:
            # 更新時間戳
            profile.last_updated = datetime.now().isoformat()

            data = self._serialize_profile(profile)

            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"保存 Profile 成功: {profile_path}")
            return True

        except Exception as e:
            logger.error(f"保存 Profile 失敗: {e}")
            return False

    def list_profiles(self) -> List[str]:
        """列出所有可用的組合名稱"""
        profiles = []
        for path in self.profile_dir.glob("*.json"):
            profiles.append(path.stem)
        return sorted(profiles)

    def validate_profile(self, profile: ChipProfile) -> ValidationResult:
        """
        驗證組合完整性

        Args:
            profile: 要驗證的組合

        Returns:
            ValidationResult
        """
        result = ValidationResult(valid=True)

        # 檢查是否有可用籌碼
        calibrated_chips = profile.get_calibrated_chips()
        if not calibrated_chips:
            result.valid = False
            result.errors.append("沒有已校準的籌碼")
            result.suggestions.append("至少需要校準一顆籌碼才能開始下注")

        # 檢查必要的下注位置
        required_positions = ["confirm"]  # 確認按鈕是必須的
        for pos_name in required_positions:
            if not profile.is_position_calibrated(pos_name):
                result.valid = False
                result.errors.append(f"未校準必要位置: {pos_name}")

        # 檢查是否至少有一個下注目標
        bet_targets = ["banker", "player", "tie"]
        has_target = any(profile.is_position_calibrated(t) for t in bet_targets)
        if not has_target:
            result.valid = False
            result.errors.append("未校準任何下注目標 (莊家/閒家/和局)")
            result.suggestions.append("至少需要校準一個下注目標")

        # 警告：籌碼過少
        if len(calibrated_chips) == 1:
            result.warnings.append("僅校準 1 顆籌碼，可能無法湊出多種金額")
            result.suggestions.append("建議至少校準 2 種不同面額的籌碼")

        # 警告：缺少小額籌碼
        min_chip_value = min(c.value for c in calibrated_chips) if calibrated_chips else 0
        if min_chip_value > 100:
            result.warnings.append(f"最小籌碼為 {min_chip_value} 元，無法組合更小金額")
            result.suggestions.append("建議校準 100 元籌碼以增加靈活性")

        return result

    def update_chip_calibration(
        self,
        profile: ChipProfile,
        slot: int,
        x: int,
        y: int
    ) -> bool:
        """
        更新籌碼校準位置

        Args:
            profile: 目標組合
            slot: 籌碼槽位 (1-6)
            x: X 座標
            y: Y 座標

        Returns:
            是否成功
        """
        chip = profile.get_chip_by_slot(slot)
        if not chip:
            logger.error(f"找不到槽位 {slot} 的籌碼")
            return False

        chip.x = x
        chip.y = y
        chip.calibrated = True

        logger.info(f"更新 Chip {slot} 校準: ({x}, {y})")
        return True

    def update_position_calibration(
        self,
        profile: ChipProfile,
        position_name: str,
        x: int,
        y: int
    ) -> bool:
        """
        更新下注位置校準

        Args:
            profile: 目標組合
            position_name: 位置名稱 (banker/player/tie/confirm/cancel)
            x: X 座標
            y: Y 座標

        Returns:
            是否成功
        """
        if position_name not in profile.bet_positions:
            logger.error(f"未知的位置: {position_name}")
            return False

        profile.bet_positions[position_name]["x"] = x
        profile.bet_positions[position_name]["y"] = y
        profile.bet_positions[position_name]["calibrated"] = True

        logger.info(f"更新 {position_name} 校準: ({x}, {y})")
        return True

    def _parse_profile(self, data: Dict) -> ChipProfile:
        """從 JSON 資料解析 Profile"""
        # 解析籌碼
        chips = []
        for chip_data in data.get("chips", []):
            chip = Chip(
                slot=chip_data["slot"],
                value=chip_data["value"],
                label=chip_data.get("label", str(chip_data["value"])),
                x=chip_data.get("x", 0),
                y=chip_data.get("y", 0),
                calibrated=chip_data.get("calibrated", False)
            )
            chips.append(chip)

        return ChipProfile(
            profile_name=data.get("profile_name", "未命名"),
            provider=data.get("provider", "WG/BG"),
            table_type=data.get("table_type", "standard"),
            chips=chips,
            bet_positions=data.get("bet_positions", {}),
            constraints=data.get("constraints", {}),
            created_at=data.get("created_at", ""),
            last_updated=data.get("last_updated", "")
        )

    def _serialize_profile(self, profile: ChipProfile) -> Dict:
        """將 Profile 序列化為 JSON 格式"""
        chips_data = []
        for chip in profile.chips:
            chips_data.append({
                "slot": chip.slot,
                "value": chip.value,
                "color": self._get_chip_color(chip.value),
                "label": chip.label,
                "calibrated": chip.calibrated,
                "x": chip.x,
                "y": chip.y
            })

        return {
            "profile_name": profile.profile_name,
            "provider": profile.provider,
            "table_type": profile.table_type,
            "created_at": profile.created_at,
            "last_updated": profile.last_updated,
            "chips": chips_data,
            "bet_positions": profile.bet_positions,
            "constraints": profile.constraints,
            "validation": {
                "last_check": None,
                "status": "unchecked",
                "warnings": []
            }
        }

    def _get_chip_color(self, value: int) -> str:
        """根據金額返回籌碼顏色"""
        color_map = {
            100: "red",
            1000: "orange",
            5000: "blue",
            10000: "green",
            50000: "purple",
            100000: "black"
        }
        return color_map.get(value, "gray")

    def _create_default_profile(self) -> ChipProfile:
        """創建預設組合"""
        chips = [
            Chip(slot=1, value=100, label="100", calibrated=False),
            Chip(slot=2, value=1000, label="1K", calibrated=False),
            Chip(slot=3, value=5000, label="5K", calibrated=False),
            Chip(slot=4, value=10000, label="10K", calibrated=False),
            Chip(slot=5, value=50000, label="50K", calibrated=False),
            Chip(slot=6, value=100000, label="100K", calibrated=False),
        ]

        bet_positions = {
            "banker": {"x": 0, "y": 0, "calibrated": False},
            "player": {"x": 0, "y": 0, "calibrated": False},
            "tie": {"x": 0, "y": 0, "calibrated": False},
            "confirm": {"x": 0, "y": 0, "calibrated": False},
            "cancel": {"x": 0, "y": 0, "calibrated": False}
        }

        constraints = {
            "min_bet": 100,
            "max_bet": 10000,
            "max_clicks_per_hand": 8
        }

        return ChipProfile(
            profile_name="預設籌碼組合",
            provider="WG/BG",
            table_type="standard",
            chips=chips,
            bet_positions=bet_positions,
            constraints=constraints,
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat()
        )
