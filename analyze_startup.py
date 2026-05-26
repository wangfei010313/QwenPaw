#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive startup analysis for QwenPaw.
Analyzes startup logs and provides detailed performance metrics.
"""

import re
import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class StartupLogAnalyzer:
    """Analyze QwenPaw startup logs for performance metrics."""

    # Regex patterns for log parsing
    PATTERNS = {
        "server_ready": r"Uvicorn running on (.*)",
        "critical_time": r"Critical startup completed in ([\d.]+) seconds",
        "total_time": r"Background startup completed in ([\d.]+) seconds total",
        "agent_startup": r"Starting.*agents",
        "plugin_init": r"Initializing plugin system",
        "local_model_resume": r"Starting local model resume",
        "error": r"ERROR|Exception|RuntimeError",
        "phase_complete": r"(\w+) phase.*completed",
    }

    def __init__(self):
        self.logs: List[str] = []
        self.metrics: Dict = {}
        self.errors: List[str] = []

    def load_logs(self, log_file: Path) -> bool:
        """Load logs from file."""
        try:
            with open(log_file, encoding="utf-8", errors="replace") as f:
                self.logs = f.readlines()
            return True
        except FileNotFoundError:
            print(f"✗ 日志文件不存在: {log_file}")
            return False

    def analyze(self) -> bool:
        """Analyze loaded logs."""

        if not self.logs:
            print("✗ 没有日志可分析")
            return False

        # Extract metrics
        for log_line in self.logs:
            for key, pattern in self.PATTERNS.items():
                if match := re.search(pattern, log_line, re.IGNORECASE):
                    if key == "critical_time":
                        self.metrics["critical_time"] = float(match.group(1))
                    elif key == "total_time":
                        self.metrics["total_time"] = float(match.group(1))
                    elif key == "server_ready":
                        self.metrics["server_ready"] = match.group(1)
                    elif key == "error":
                        self.errors.append(log_line.strip())

        return True

    def get_report(self) -> str:
        """Generate analysis report."""

        report = "\n" + "=" * 70 + "\n"
        report += "QwenPaw 启动性能分析报告\n"
        report += "=" * 70 + "\n\n"

        # Metrics section
        report += "性能指标:\n"
        report += "-" * 70 + "\n"

        if "server_ready" in self.metrics:
            report += f"Server URL:        {self.metrics['server_ready']}\n"

        if "critical_time" in self.metrics:
            ct = self.metrics["critical_time"]
            report += f"Critical时间:      {ct:.3f}s\n"

            # Performance assessment
            if ct < 0.3:
                rating = "⭐⭐⭐⭐⭐ 极优"
            elif ct < 0.5:
                rating = "⭐⭐⭐⭐ 优秀"
            elif ct < 0.8:
                rating = "⭐⭐⭐ 良好"
            elif ct < 1.0:
                rating = "⭐⭐ 可接受"
            else:
                rating = "⭐ 需改进"
            report += f"  {rating}\n"

        if "total_time" in self.metrics:
            tt = self.metrics["total_time"]
            report += f"总启动时间:        {tt:.3f}s\n"

            # Performance assessment
            if tt < 1.0:
                rating = "⭐⭐⭐⭐⭐ 极优"
            elif tt < 1.5:
                rating = "⭐⭐⭐⭐ 优秀"
            elif tt < 2.0:
                rating = "⭐⭐⭐ 良好"
            elif tt < 2.5:
                rating = "⭐⭐ 可接受"
            else:
                rating = "⭐ 需改进"
            report += f"  {rating}\n"

        # Error section
        report += "\n错误检查:\n"
        report += "-" * 70 + "\n"

        if self.errors:
            report += f"❌ 发现 {len(self.errors)} 个错误:\n\n"
            for i, error in enumerate(self.errors[:5], 1):  # Show first 5
                report += f"  {i}. {error}\n"
            if len(self.errors) > 5:
                report += f"  ... 以及 {len(self.errors) - 5} 个其他错误\n"
        else:
            report += "✅ 未发现错误\n"

        # Optimization check
        report += "\n优化效果检查:\n"
        report += "-" * 70 + "\n"

        checks = [
            ("并行加载配置", "Parallel config loading"),
            ("ProgressiveInitializer", "Progressive initialization"),
            ("本地模型恢复", "Local model resume"),
            ("插件系统", "Plugin system"),
            ("后台初始化", "Background initialization"),
        ]

        for check_name, pattern in checks:
            if any(pattern.lower() in log.lower() for log in self.logs):
                report += f"  ✓ {check_name}\n"
            else:
                report += f"  ? {check_name} (未找到)\n"

        # Recommendations
        report += "\n建议:\n"
        report += "-" * 70 + "\n"

        recommendations = []

        if "critical_time" in self.metrics:
            if self.metrics["critical_time"] > 0.5:
                recommendations.append("- 考虑进一步并行化关键路径任务")

        if self.errors:
            recommendations.append("- 修复检测到的错误")

        if not recommendations:
            recommendations.append("- 性能良好，继续监控")

        for rec in recommendations:
            report += f"{rec}\n"

        report += "\n" + "=" * 70 + "\n"

        return report


def main():
    """Main analysis function."""

    print("=" * 70)
    print("QwenPaw 启动分析工具")
    print("=" * 70)
    print()

    project_root = Path(__file__).parent

    # Try to find log file
    log_candidates = [
        project_root / "startup.log",
        project_root / "app.log",
        project_root / "debug.log",
    ]

    log_file = None
    for candidate in log_candidates:
        if candidate.exists():
            log_file = candidate
            break

    if not log_file:
        print("⚠ 未找到日志文件")
        print("\n如何生成日志:")
        print(
            "1. 运行: python -m qwenpaw app --log-level debug 2>&1 | tee app.log"
        )
        print("2. 等待启动完成")
        print("3. 按 Ctrl+C 停止服务器")
        print("4. 重新运行此脚本")
        return False

    print(f"分析日志文件: {log_file.relative_to(project_root)}\n")

    # Analyze
    analyzer = StartupLogAnalyzer()

    if not analyzer.load_logs(log_file):
        return False

    if not analyzer.analyze():
        return False

    # Print report
    print(analyzer.get_report())

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
