# src/autobet/health.py
"""
系統健康檢查模組

提供完整的系統健康檢查功能：
1. 配置文件驗證
2. 組件狀態檢查
3. 性能指標檢查
4. 資源使用檢查
5. 生成健康報告
"""

from __future__ import annotations

import time
import json
import sys
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class HealthStatus(str, Enum):
    """健康狀態"""
    HEALTHY = "healthy"      # 健康
    DEGRADED = "degraded"    # 降級（有警告但可運行）
    UNHEALTHY = "unhealthy"  # 不健康（有錯誤）
    UNKNOWN = "unknown"      # 未知


@dataclass
class HealthCheckResult:
    """健康檢查結果"""
    component: str                      # 組件名稱
    status: HealthStatus               # 健康狀態
    message: str                       # 狀態消息
    details: Dict[str, Any] = field(default_factory=dict)  # 詳細信息
    timestamp: float = field(default_factory=time.time)    # 檢查時間
    duration_ms: float = 0.0           # 檢查耗時（毫秒）

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SystemHealthReport:
    """系統健康報告"""
    overall_status: HealthStatus
    timestamp: float
    checks: List[HealthCheckResult]
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "overall_status": self.overall_status.value,
            "timestamp": self.timestamp,
            "checks": [check.to_dict() for check in self.checks],
            "summary": self.summary,
        }


class HealthChecker:
    """
    系統健康檢查器

    檢查所有關鍵組件的健康狀態
    """

    def __init__(self, project_root: Optional[Path] = None):
        """
        初始化健康檢查器

        Args:
            project_root: 項目根目錄（None 則自動檢測）
        """
        if project_root is None:
            # 自動檢測項目根目錄
            current = Path(__file__).parent
            while current.parent != current:
                if (current / "configs").exists():
                    project_root = current
                    break
                current = current.parent
            else:
                project_root = Path.cwd()

        self.project_root = project_root
        self.results: List[HealthCheckResult] = []

    def check_all(self, include_performance: bool = False) -> SystemHealthReport:
        """
        執行所有健康檢查

        Args:
            include_performance: 是否包含性能檢查（需要運行中的系統）

        Returns:
            系統健康報告
        """
        self.results = []

        # 1. 配置文件檢查
        self._check_configs()

        # 2. 組件狀態檢查
        self._check_components()

        # 3. 環境檢查
        self._check_environment()

        # 4. 性能檢查（可選）
        if include_performance:
            self._check_performance()

        # 計算總體狀態
        overall_status = self._calculate_overall_status()

        # 生成摘要
        summary = self._generate_summary()

        return SystemHealthReport(
            overall_status=overall_status,
            timestamp=time.time(),
            checks=self.results,
            summary=summary,
        )

    def _check_configs(self) -> None:
        """檢查配置文件"""
        start_time = time.time()

        # 檢查必要配置文件是否存在
        required_configs = [
            ("positions.json", "configs/positions.json"),
            ("chip_profile", "configs/chip_profiles/default.json"),
            (".env", ".env"),
        ]

        missing_configs = []
        found_configs = []

        for name, path in required_configs:
            config_path = self.project_root / path
            if config_path.exists():
                found_configs.append(name)
            else:
                missing_configs.append(name)

        if missing_configs:
            status = HealthStatus.UNHEALTHY
            message = f"缺少必要配置文件: {', '.join(missing_configs)}"
            details = {
                "missing": missing_configs,
                "found": found_configs,
            }
        else:
            status = HealthStatus.HEALTHY
            message = "所有必要配置文件存在"
            details = {
                "found": found_configs,
            }

        duration_ms = (time.time() - start_time) * 1000.0

        self.results.append(HealthCheckResult(
            component="configs",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        ))

        # 檢查配置文件有效性（使用 validate_config.py）
        self._check_config_validity()

    def _check_config_validity(self) -> None:
        """檢查配置文件有效性"""
        start_time = time.time()

        try:
            # 導入配置驗證器
            import sys
            sys.path.insert(0, str(self.project_root))

            from scripts.validate_config import ConfigValidator

            # 創建驗證器
            validator = ConfigValidator(self.project_root, verbose=False)

            # 執行驗證
            error_count = validator.validate_all()

            # 分析問題
            critical_count = sum(1 for issue in validator.issues
                                if issue.severity.value == "CRITICAL")
            error_count_only = sum(1 for issue in validator.issues
                                   if issue.severity.value == "ERROR")
            warning_count = sum(1 for issue in validator.issues
                               if issue.severity.value == "WARNING")

            if critical_count > 0:
                status = HealthStatus.UNHEALTHY
                message = f"配置文件有 {critical_count} 個嚴重錯誤"
            elif error_count_only > 0:
                status = HealthStatus.UNHEALTHY
                message = f"配置文件有 {error_count_only} 個錯誤"
            elif warning_count > 0:
                status = HealthStatus.DEGRADED
                message = f"配置文件有 {warning_count} 個警告"
            else:
                status = HealthStatus.HEALTHY
                message = "配置文件驗證通過"

            details = {
                "critical_count": critical_count,
                "error_count": error_count_only,
                "warning_count": warning_count,
                "total_issues": len(validator.issues),
            }

        except Exception as e:
            status = HealthStatus.UNKNOWN
            message = f"配置驗證失敗: {e}"
            details = {"error": str(e)}

        duration_ms = (time.time() - start_time) * 1000.0

        self.results.append(HealthCheckResult(
            component="config_validity",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        ))

    def _check_components(self) -> None:
        """檢查組件狀態"""
        start_time = time.time()

        # 檢查關鍵模組是否可導入
        required_modules = [
            "src.autobet.autobet_engine",
            "src.autobet.lines.orchestrator",
            "src.autobet.phase_detector",
            "src.autobet.lines.performance",
            "ui.workers.engine_worker",
        ]

        importable = []
        not_importable = []

        for module_name in required_modules:
            try:
                __import__(module_name)
                importable.append(module_name)
            except ImportError as e:
                not_importable.append(f"{module_name}: {e}")

        if not_importable:
            status = HealthStatus.UNHEALTHY
            message = f"{len(not_importable)} 個模組無法導入"
            details = {
                "importable": importable,
                "not_importable": not_importable,
            }
        else:
            status = HealthStatus.HEALTHY
            message = "所有關鍵模組可正常導入"
            details = {
                "importable": importable,
            }

        duration_ms = (time.time() - start_time) * 1000.0

        self.results.append(HealthCheckResult(
            component="components",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        ))

    def _check_environment(self) -> None:
        """檢查環境配置"""
        start_time = time.time()

        details = {
            "python_version": sys.version,
            "platform": sys.platform,
        }

        # 檢查 Python 版本
        if sys.version_info < (3, 8):
            status = HealthStatus.UNHEALTHY
            message = f"Python 版本過低: {sys.version_info.major}.{sys.version_info.minor}"
        else:
            status = HealthStatus.HEALTHY
            message = f"Python 版本正常: {sys.version_info.major}.{sys.version_info.minor}"
            details["python_version_ok"] = True

        # 檢查關鍵依賴
        try:
            import PySide6
            details["PySide6_version"] = PySide6.__version__
        except ImportError:
            status = HealthStatus.UNHEALTHY
            message = "缺少 PySide6 依賴"
            details["PySide6_installed"] = False

        try:
            import cv2
            details["opencv_version"] = cv2.__version__
        except ImportError:
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.DEGRADED
            message = "缺少 OpenCV 依賴（影像檢測功能不可用）"
            details["opencv_installed"] = False

        duration_ms = (time.time() - start_time) * 1000.0

        self.results.append(HealthCheckResult(
            component="environment",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        ))

    def _check_performance(self) -> None:
        """檢查性能指標（需要運行中的系統）"""
        start_time = time.time()

        # 這個檢查需要系統正在運行，暫時標記為 UNKNOWN
        status = HealthStatus.UNKNOWN
        message = "性能檢查需要運行中的系統"
        details = {
            "note": "使用 orchestrator.performance.get_summary() 獲取性能數據"
        }

        duration_ms = (time.time() - start_time) * 1000.0

        self.results.append(HealthCheckResult(
            component="performance",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        ))

    def _calculate_overall_status(self) -> HealthStatus:
        """計算總體健康狀態"""
        if not self.results:
            return HealthStatus.UNKNOWN

        # 如果有任何 UNHEALTHY，整體就是 UNHEALTHY
        if any(r.status == HealthStatus.UNHEALTHY for r in self.results):
            return HealthStatus.UNHEALTHY

        # 如果有 DEGRADED，整體就是 DEGRADED
        if any(r.status == HealthStatus.DEGRADED for r in self.results):
            return HealthStatus.DEGRADED

        # 如果全是 HEALTHY，整體就是 HEALTHY
        if all(r.status == HealthStatus.HEALTHY for r in self.results):
            return HealthStatus.HEALTHY

        # 否則是 UNKNOWN
        return HealthStatus.UNKNOWN

    def _generate_summary(self) -> Dict[str, Any]:
        """生成健康檢查摘要"""
        status_counts = {
            "healthy": 0,
            "degraded": 0,
            "unhealthy": 0,
            "unknown": 0,
        }

        for result in self.results:
            status_counts[result.status.value] += 1

        total_duration_ms = sum(r.duration_ms for r in self.results)

        return {
            "total_checks": len(self.results),
            "status_counts": status_counts,
            "total_duration_ms": total_duration_ms,
            "components_checked": [r.component for r in self.results],
        }

    def print_report(self, report: SystemHealthReport) -> None:
        """
        打印健康報告（用於 CLI）

        Args:
            report: 系統健康報告
        """
        print("=" * 80)
        print("系統健康檢查報告")
        print("=" * 80)
        print()

        # 總體狀態
        status_symbols = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.UNHEALTHY: "❌",
            HealthStatus.UNKNOWN: "❓",
        }

        symbol = status_symbols.get(report.overall_status, "❓")
        print(f"總體狀態: {symbol} {report.overall_status.value.upper()}")
        print()

        # 摘要
        summary = report.summary
        print(f"檢查項目: {summary['total_checks']}")
        print(f"總耗時: {summary['total_duration_ms']:.2f}ms")
        print()
        print("狀態分佈:")
        for status, count in summary['status_counts'].items():
            if count > 0:
                symbol = status_symbols.get(HealthStatus(status), "❓")
                print(f"  {symbol} {status.upper()}: {count}")
        print()

        # 詳細檢查結果
        print("-" * 80)
        print("詳細檢查結果:")
        print("-" * 80)
        print()

        for check in report.checks:
            symbol = status_symbols.get(check.status, "❓")
            print(f"{symbol} [{check.component}] {check.message}")

            if check.details:
                for key, value in check.details.items():
                    if isinstance(value, (list, dict)):
                        print(f"    {key}: {json.dumps(value, ensure_ascii=False)}")
                    else:
                        print(f"    {key}: {value}")

            print(f"    耗時: {check.duration_ms:.2f}ms")
            print()

        print("=" * 80)


def check_system_health(project_root: Optional[Path] = None, verbose: bool = True) -> SystemHealthReport:
    """
    檢查系統健康狀態（便捷函數）

    Args:
        project_root: 項目根目錄
        verbose: 是否打印報告

    Returns:
        系統健康報告
    """
    checker = HealthChecker(project_root)
    report = checker.check_all()

    if verbose:
        checker.print_report(report)

    return report
