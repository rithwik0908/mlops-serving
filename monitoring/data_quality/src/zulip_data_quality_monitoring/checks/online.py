from __future__ import annotations

import json

import pandas as pd

from zulip_data_quality_monitoring.checks.base import BaseCheck
from zulip_data_quality_monitoring.metrics import entropy, ratio
from zulip_data_quality_monitoring.models import CheckResult


class OnlineLogsCheck(BaseCheck):
    name = "online_logs"

    def run(self, store, config) -> CheckResult:
        keys = store.list_keys("online_logs/")
        rows: list[dict] = []
        for key in keys:
            payload = store.read_json(key)
            if isinstance(payload, list):
                rows.extend(payload)
        frame = pd.DataFrame(rows)

        if frame.empty:
            return CheckResult(
                name=self.name,
                status="warn",
                metrics={"log_files": len(keys), "events": 0},
                summary="No online log events were found.",
                recommendations=["Verify the generator service is flushing `online_logs/` objects to MinIO."],
            )

        rewrite_styles = frame["input"].apply(lambda x: x.get("rewrite_style") if isinstance(x, dict) else None)
        statuses = frame["http_status"].fillna(0)
        metrics = {
            "log_files": len(keys),
            "events": len(frame),
            "error_rate": ratio(float((statuses == 0).sum() + (statuses >= 500).sum()), float(len(frame))),
            "style_entropy": entropy(rewrite_styles.dropna().astype(str)),
            "style_distribution": rewrite_styles.value_counts(normalize=True).round(4).to_dict(),
        }
        passed = metrics["error_rate"] <= config.thresholds["max_online_error_rate"]
        recommendations = []
        if metrics["error_rate"] > config.thresholds["max_online_error_rate"]:
            recommendations.append("Alert on rewrite service failures before they contaminate online-log-based training data.")
        if len(metrics["style_distribution"]) < 2:
            recommendations.append("Increase rewrite_style coverage so online data is not dominated by one serving mode.")
        return CheckResult(
            name=self.name,
            status="pass" if passed else "warn",
            metrics=metrics,
            summary=f"Observed {metrics['events']} online events across {metrics['log_files']} flushed log files.",
            recommendations=recommendations,
        )
