from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from zulip_data_quality_monitoring.models import CheckResult, Report


def overall_status(checks: list[CheckResult]) -> str:
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "warn" for check in checks):
        return "warn"
    return "pass"


def write_json(report: Report, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")


def write_markdown(report: Report, path: str) -> None:
    lines = [
        "# Data Quality Report",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- Overall status: `{report.overall_status}`",
        "",
    ]
    for check in report.checks:
        lines.extend(
            [
                f"## {check.name}",
                "",
                f"- Status: `{check.status}`",
                f"- Summary: {check.summary}",
                "- Metrics:",
                "```json",
                json.dumps(check.metrics, indent=2),
                "```",
            ]
        )
        if check.recommendations:
            lines.append("- Recommendations:")
            for rec in check.recommendations:
                lines.append(f"  - {rec}")
        lines.append("")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
