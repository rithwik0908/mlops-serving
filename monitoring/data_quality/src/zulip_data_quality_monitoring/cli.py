from __future__ import annotations

import argparse

from zulip_data_quality_monitoring.config import load_config
from zulip_data_quality_monitoring.reporting import write_json, write_markdown
from zulip_data_quality_monitoring.runner import run_all_checks


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Zulip data quality checks.")
    parser.add_argument("--config", required=True, help="Path to YAML config.")
    args = parser.parse_args()

    config = load_config(args.config)
    report = run_all_checks(config)
    write_json(report, config.reports.json_path)
    write_markdown(report, config.reports.markdown_path)
    print(f"Overall status: {report.overall_status}")
    print(f"JSON report: {config.reports.json_path}")
    print(f"Markdown report: {config.reports.markdown_path}")
