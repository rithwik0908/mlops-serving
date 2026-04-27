from __future__ import annotations

import pandas as pd

from zulip_data_quality_monitoring.checks.base import BaseCheck
from zulip_data_quality_monitoring.metrics import (
    char_count_stats,
    class_distribution,
    duplicate_rate,
    invalid_label_rate,
    null_rate,
    ratio,
    word_count_stats,
)
from zulip_data_quality_monitoring.models import CheckResult


class RawDatasetCheck(BaseCheck):
    name = "raw_dataset"

    def run(self, store, config) -> CheckResult:
        version = config.dataset.raw_version
        train = store.read_parquet(f"raw/{version}/train.parquet")
        val = store.read_parquet(f"raw/{version}/val.parquet")
        test = store.read_parquet(f"raw/{version}/test.parquet")
        manifest = store.read_json(f"raw/{version}/manifest.json")
        full = pd.concat([train, val, test], ignore_index=True)

        metrics = {
            "train_rows": len(train),
            "val_rows": len(val),
            "test_rows": len(test),
            "total_rows": len(full),
            "manifest_total_rows": manifest.get("total_rows"),
            "null_text_rate": null_rate(full["text"]),
            "duplicate_text_rate": duplicate_rate(full["text"]),
            "invalid_label_rate": invalid_label_rate(full["binary_label"]),
            "synthetic_rate": ratio(float(full.get("synthetic", pd.Series(dtype=bool)).fillna(False).sum()), float(len(full))),
            "label_distribution": class_distribution(full["binary_label"]),
            "word_count": word_count_stats(full["text"]),
            "char_count": char_count_stats(full["text"]),
        }
        passed = (
            metrics["null_text_rate"] <= config.thresholds["max_null_text_rate"]
            and metrics["duplicate_text_rate"] <= config.thresholds["max_duplicate_text_rate"]
            and metrics["invalid_label_rate"] <= config.thresholds["max_invalid_label_rate"]
            and metrics["train_rows"] >= config.thresholds["min_train_rows"]
            and metrics["manifest_total_rows"] == metrics["total_rows"]
        )
        summary = (
            f"Raw dataset has {metrics['total_rows']} rows across train/val/test; "
            f"duplicate_text_rate={metrics['duplicate_text_rate']}, invalid_label_rate={metrics['invalid_label_rate']}."
        )
        recommendations = []
        if metrics["duplicate_text_rate"] > config.thresholds["max_duplicate_text_rate"]:
            recommendations.append("Deduplicate repeated messages created by augmentation or repeated ingestion.")
        if metrics["manifest_total_rows"] != metrics["total_rows"]:
            recommendations.append("Keep raw manifest row counts in sync with uploaded parquet splits.")
        if metrics["invalid_label_rate"] > 0:
            recommendations.append("Enforce binary_label in {-1, 0, 1} before upload.")
        return CheckResult(
            name=self.name,
            status="pass" if passed else "fail",
            metrics=metrics,
            summary=summary,
            recommendations=recommendations,
        )
