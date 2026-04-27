from __future__ import annotations

from zulip_data_quality_monitoring.checks.base import BaseCheck
from zulip_data_quality_monitoring.metrics import class_distribution, duplicate_rate, null_rate
from zulip_data_quality_monitoring.models import CheckResult


class BatchDatasetCheck(BaseCheck):
    name = "batch_dataset"

    def run(self, store, config) -> CheckResult:
        batch_version = config.dataset.batch_version
        train = store.read_parquet(f"batch/{batch_version}/train.parquet")
        test = store.read_parquet(f"batch/{batch_version}/test.parquet")
        manifest = store.read_json(f"batch/{batch_version}/manifest.json")

        metrics = {
            "train_rows": len(train),
            "test_rows": len(test),
            "online_log_rows": manifest.get("online_log_rows", 0),
            "feedback_rows_merged": manifest.get("feedback_rows_merged", 0),
            "feedback_approval_rate": manifest.get("feedback_approval_rate"),
            "train_null_text_rate": null_rate(train["text"]),
            "train_duplicate_text_rate": duplicate_rate(train["text"]),
            "train_label_distribution": class_distribution(train["binary_label"]),
            "leakage_policy": manifest.get("leakage_policy"),
        }
        approval_rate = metrics["feedback_approval_rate"]
        passed = (
            metrics["train_null_text_rate"] <= config.thresholds["max_null_text_rate"]
            and metrics["train_duplicate_text_rate"] <= config.thresholds["max_duplicate_text_rate"]
            and (approval_rate is None or approval_rate >= config.thresholds["min_feedback_approval_rate"])
        )
        recommendations = []
        if metrics["train_duplicate_text_rate"] > config.thresholds["max_duplicate_text_rate"]:
            recommendations.append("De-duplicate online-log rows before merging into batch training data.")
        if approval_rate is not None and approval_rate < config.thresholds["min_feedback_approval_rate"]:
            recommendations.append("Gate batch promotion when user approval falls below the quality threshold.")
        return CheckResult(
            name=self.name,
            status="pass" if passed else "warn",
            metrics=metrics,
            summary=f"Batch dataset {batch_version} merges online logs and feedback into {len(train)} train rows.",
            recommendations=recommendations,
        )
