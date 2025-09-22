#!/usr/bin/env python3
"""
模板檢查工具 - NCC/灰階分布檢查模板品質與門檻
"""

import os
import sys
import cv2
import json
import numpy as np
import pyautogui
from typing import Dict, Any, List, Tuple, Optional

# 禁用 pyautogui 安全機制
pyautogui.FAILSAFE = False


class TemplateChecker:
    """模板檢查器"""

    def __init__(self, positions_file: str = "configs/positions.sample.json"):
        self.positions_file = positions_file
        self.positions = {}
        self.templates_dir = "templates"
        self.results = {}

        # 模板檢查配置
        self.ncc_thresholds = {
            "excellent": 0.9,
            "good": 0.8,
            "acceptable": 0.7,
            "poor": 0.6
        }

    def load_positions(self) -> bool:
        """載入位置配置"""
        try:
            if not os.path.exists(self.positions_file):
                print(f"❌ 位置配置檔案不存在: {self.positions_file}")
                return False

            with open(self.positions_file, 'r', encoding='utf-8') as f:
                self.positions = json.load(f)

            print(f"✓ 位置配置已載入: {self.positions_file}")
            return True

        except Exception as e:
            print(f"❌ 載入位置配置失敗: {e}")
            return False

    def check_all_templates(self) -> Dict[str, Any]:
        """檢查所有模板"""
        if not self.load_positions():
            return {}

        print("\n開始模板檢查...")
        print("=" * 60)

        # 截取當前螢幕
        screenshot = self._capture_full_screen()
        if screenshot is None:
            print("❌ 無法截取螢幕")
            return {}

        # 檢查各類型模板
        self._check_chip_templates(screenshot)
        self._check_bet_templates(screenshot)
        self._check_control_templates(screenshot)
        self._check_overlay_template(screenshot)

        # 顯示總結
        self._show_summary()

        return self.results

    def _capture_full_screen(self) -> Optional[np.ndarray]:
        """截取全螢幕"""
        try:
            screenshot = pyautogui.screenshot()
            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"截取螢幕失敗: {e}")
            return None

    def _check_chip_templates(self, screenshot: np.ndarray):
        """檢查籌碼模板"""
        print("\n🪙 檢查籌碼模板:")
        print("-" * 40)

        chip_points = self.positions.get("points", {}).get("chips", {})

        for chip_name, point_data in chip_points.items():
            template_path = f"{self.templates_dir}/chips/{chip_name}.png"
            result = self._check_single_template(
                template_path, point_data, screenshot, chip_name
            )
            self.results[f"chips.{chip_name}"] = result

    def _check_bet_templates(self, screenshot: np.ndarray):
        """檢查下注區域模板"""
        print("\n🎯 檢查下注區域模板:")
        print("-" * 40)

        bet_points = self.positions.get("points", {}).get("bets", {})

        for bet_name, point_data in bet_points.items():
            template_path = f"{self.templates_dir}/bets/bet_{bet_name}.png"
            result = self._check_single_template(
                template_path, point_data, screenshot, bet_name
            )
            self.results[f"bets.{bet_name}"] = result

    def _check_control_templates(self, screenshot: np.ndarray):
        """檢查控制按鈕模板"""
        print("\n🔘 檢查控制按鈕模板:")
        print("-" * 40)

        control_points = self.positions.get("points", {}).get("controls", {})

        for control_name, point_data in control_points.items():
            template_path = f"{self.templates_dir}/controls/btn_{control_name}.png"
            result = self._check_single_template(
                template_path, point_data, screenshot, control_name
            )
            self.results[f"controls.{control_name}"] = result

    def _check_overlay_template(self, screenshot: np.ndarray):
        """檢查 overlay 模板"""
        print("\n📊 檢查 Overlay 模板:")
        print("-" * 40)

        overlay_roi = self.positions.get("roi", {}).get("overlay", {})
        if overlay_roi:
            template_path = f"{self.templates_dir}/controls/overlay_anchor.png"

            # 為 overlay 創建虛擬點位數據
            point_data = {
                "x": overlay_roi["x"] + overlay_roi["w"] // 2,
                "y": overlay_roi["y"] + overlay_roi["h"] // 2,
                "template_w": overlay_roi["w"],
                "template_h": overlay_roi["h"]
            }

            result = self._check_single_template(
                template_path, point_data, screenshot, "overlay_anchor"
            )
            self.results["controls.overlay_anchor"] = result

    def _check_single_template(self, template_path: str, point_data: Dict[str, Any],
                              screenshot: np.ndarray, name: str) -> Dict[str, Any]:
        """檢查單個模板"""
        result = {
            "name": name,
            "template_path": template_path,
            "exists": False,
            "loaded": False,
            "ncc_score": 0.0,
            "quality_level": "not_found",
            "position": (point_data.get("x", 0), point_data.get("y", 0)),
            "match_location": None,
            "gray_stats": {},
            "recommendations": []
        }

        # 檢查模板檔案是否存在
        if not os.path.exists(template_path):
            print(f"  ❌ {name}: 模板檔案不存在")
            result["recommendations"].append("需要創建模板檔案")
            return result

        result["exists"] = True

        # 載入模板
        try:
            template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            if template is None:
                print(f"  ❌ {name}: 無法載入模板")
                result["recommendations"].append("模板檔案可能損壞")
                return result

            result["loaded"] = True

        except Exception as e:
            print(f"  ❌ {name}: 載入模板失敗 - {e}")
            return result

        # 執行模板匹配
        try:
            gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

            # NCC 匹配
            match_result = cv2.matchTemplate(gray_screenshot, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(match_result)

            result["ncc_score"] = float(max_val)
            result["match_location"] = max_loc

            # 判斷品質等級
            if max_val >= self.ncc_thresholds["excellent"]:
                result["quality_level"] = "excellent"
                status = "🟢 優秀"
            elif max_val >= self.ncc_thresholds["good"]:
                result["quality_level"] = "good"
                status = "🟡 良好"
            elif max_val >= self.ncc_thresholds["acceptable"]:
                result["quality_level"] = "acceptable"
                status = "🟠 可接受"
            elif max_val >= self.ncc_thresholds["poor"]:
                result["quality_level"] = "poor"
                status = "🔴 差"
            else:
                result["quality_level"] = "very_poor"
                status = "⚫ 極差"

            print(f"  {status} {name}: NCC={max_val:.3f}")

            # 灰階統計
            result["gray_stats"] = self._analyze_template_gray_stats(template)

            # 生成建議
            result["recommendations"] = self._generate_recommendations(result)

        except Exception as e:
            print(f"  ❌ {name}: 模板匹配失敗 - {e}")
            result["recommendations"].append("模板匹配過程出錯")

        return result

    def _analyze_template_gray_stats(self, template: np.ndarray) -> Dict[str, float]:
        """分析模板灰階統計"""
        return {
            "mean": float(np.mean(template)),
            "std": float(np.std(template)),
            "min": float(np.min(template)),
            "max": float(np.max(template)),
            "contrast": float(np.max(template) - np.min(template))
        }

    def _generate_recommendations(self, result: Dict[str, Any]) -> List[str]:
        """生成改進建議"""
        recommendations = []

        ncc_score = result["ncc_score"]
        gray_stats = result["gray_stats"]

        if ncc_score < self.ncc_thresholds["acceptable"]:
            recommendations.append("NCC 分數過低，建議重新擷取模板")

        if gray_stats.get("contrast", 0) < 50:
            recommendations.append("模板對比度不足，建議選擇更清晰的區域")

        if gray_stats.get("std", 0) < 10:
            recommendations.append("模板變化度不足，可能難以區分")

        if ncc_score < self.ncc_thresholds["good"]:
            recommendations.append("建議調整模板大小或重新定位")

        return recommendations

    def _show_summary(self):
        """顯示檢查總結"""
        print("\n" + "=" * 60)
        print("📋 模板檢查總結")
        print("=" * 60)

        # 統計各品質等級數量
        quality_counts = {
            "excellent": 0,
            "good": 0,
            "acceptable": 0,
            "poor": 0,
            "very_poor": 0,
            "not_found": 0
        }

        for result in self.results.values():
            quality_counts[result["quality_level"]] += 1

        # 顯示統計
        total = len(self.results)
        print(f"\n總共檢查: {total} 個模板")
        print(f"🟢 優秀: {quality_counts['excellent']}")
        print(f"🟡 良好: {quality_counts['good']}")
        print(f"🟠 可接受: {quality_counts['acceptable']}")
        print(f"🔴 差: {quality_counts['poor']}")
        print(f"⚫ 極差: {quality_counts['very_poor']}")
        print(f"❌ 未找到: {quality_counts['not_found']}")

        # 計算通過率
        passed = quality_counts['excellent'] + quality_counts['good'] + quality_counts['acceptable']
        pass_rate = (passed / total * 100) if total > 0 else 0

        print(f"\n通過率: {pass_rate:.1f}% ({passed}/{total})")

        # 顯示需要注意的模板
        problematic = [
            name for name, result in self.results.items()
            if result["quality_level"] in ["poor", "very_poor", "not_found"]
        ]

        if problematic:
            print(f"\n⚠️ 需要改進的模板:")
            for name in problematic:
                result = self.results[name]
                print(f"  - {name}: {result['quality_level']}")
                for rec in result["recommendations"]:
                    print(f"    • {rec}")

        # 建議的門檻值
        self._suggest_thresholds()

    def _suggest_thresholds(self):
        """建議模板匹配門檻值"""
        print(f"\n🎯 建議的模板匹配門檻值:")

        # 按類別統計 NCC 分數
        categories = {}
        for name, result in self.results.items():
            if result["loaded"] and result["ncc_score"] > 0:
                category = name.split(".")[0]
                if category not in categories:
                    categories[category] = []
                categories[category].append(result["ncc_score"])

        for category, scores in categories.items():
            if scores:
                min_score = min(scores)
                avg_score = sum(scores) / len(scores)
                suggested_threshold = max(0.7, min_score * 0.9)  # 保守估計

                print(f"  {category}: {suggested_threshold:.3f} (平均: {avg_score:.3f}, 最低: {min_score:.3f})")

    def save_report(self, output_file: str = "template_check_report.json") -> bool:
        """儲存檢查報告"""
        try:
            report = {
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "positions_file": self.positions_file,
                "templates_dir": self.templates_dir,
                "thresholds": self.ncc_thresholds,
                "results": self.results,
                "summary": self._generate_summary_stats()
            }

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            print(f"\n✓ 檢查報告已儲存: {output_file}")
            return True

        except Exception as e:
            print(f"❌ 儲存報告失敗: {e}")
            return False

    def _generate_summary_stats(self) -> Dict[str, Any]:
        """生成總結統計"""
        quality_counts = {}
        ncc_scores = []

        for result in self.results.values():
            quality = result["quality_level"]
            quality_counts[quality] = quality_counts.get(quality, 0) + 1

            if result["ncc_score"] > 0:
                ncc_scores.append(result["ncc_score"])

        return {
            "total_templates": len(self.results),
            "quality_distribution": quality_counts,
            "ncc_stats": {
                "min": min(ncc_scores) if ncc_scores else 0,
                "max": max(ncc_scores) if ncc_scores else 0,
                "mean": sum(ncc_scores) / len(ncc_scores) if ncc_scores else 0,
                "count": len(ncc_scores)
            }
        }


def main():
    """主函數"""
    import argparse

    parser = argparse.ArgumentParser(description="百家樂模板檢查工具")
    parser.add_argument(
        "--positions",
        default="configs/positions.sample.json",
        help="位置配置檔案路徑"
    )
    parser.add_argument(
        "--output",
        default="template_check_report.json",
        help="報告輸出檔案"
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="儲存詳細報告"
    )

    args = parser.parse_args()

    print("百家樂模板檢查工具")
    print("=" * 30)

    try:
        checker = TemplateChecker(args.positions)
        results = checker.check_all_templates()

        if results and args.save_report:
            checker.save_report(args.output)

        print(f"\n檢查完成！")

        if results:
            # 計算總體品質
            good_count = sum(1 for r in results.values()
                           if r["quality_level"] in ["excellent", "good", "acceptable"])
            total_count = len(results)

            if good_count == total_count:
                print("🎉 所有模板品質良好，可以開始使用！")
            else:
                print(f"⚠️ {total_count - good_count} 個模板需要改進")
                print("建議先修復問題模板再進行實際測試")

    except KeyboardInterrupt:
        print("\n\n用戶中斷，程式結束")
    except Exception as e:
        print(f"\n程式錯誤: {e}")


if __name__ == "__main__":
    main()