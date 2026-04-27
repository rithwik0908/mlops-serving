from __future__ import annotations

import pandas as pd

from zulip_data_quality_monitoring.checks.base import BaseCheck
from zulip_data_quality_monitoring.metrics import estimated_formality, psi
from zulip_data_quality_monitoring.models import CheckResult


class DriftCheck(BaseCheck):
    name = "drift"

    def run(self, store, config) -> CheckResult:
        raw_version = config.dataset.raw_version
        batch_version = config.dataset.batch_version
        reference = store.read_parquet(f"raw/{raw_version}/train.parquet")
        current = store.read_parquet(f"batch/{batch_version}/train.parquet")

        ref_word_count = reference["text"].fillna("").astype(str).str.split().str.len()
        cur_word_count = current["text"].fillna("").astype(str).str.split().str.len()
        ref_formality = estimated_formality(reference["text"])
        cur_formality = estimated_formality(current["text"])

        metrics = {
            "reference_rows": len(reference),
            "current_rows": len(current),
            "word_count_psi": psi(ref_word_count, cur_word_count),
            "formality_psi": psi(ref_formality, cur_formality),
            "reference_synthetic_rate": round(float(reference.get("synthetic", pd.Series(dtype=bool)).fillna(False).mean()), 4) if "synthetic" in reference else 0.0,
            "current_synthetic_rate": round(float(current.get("synthetic", pd.Series(dtype=bool)).fillna(False).mean()), 4) if "synthetic" in current else 0.0,
        }
        passed = (
            metrics["word_count_psi"] <= config.thresholds["max_word_count_drift_psi"]
            and metrics["formality_psi"] <= config.thresholds["max_formality_drift_psi"]
        )
        recommendations = []
        if metrics["word_count_psi"] > config.thresholds["max_word_count_drift_psi"]:
            recommendations.append("Inspect whether online or feedback data is shifting message length away from the original training corpus.")
        if metrics["formality_psi"] > config.thresholds["max_formality_drift_psi"]:
            recommendations.append("Check whether user traffic or feedback is skewing tone distribution enough to justify retraining.")
        return CheckResult(
            name=self.name,
            status="pass" if passed else "warn",
            metrics=metrics,
            summary=(
                f"Compared raw/{raw_version}/train.parquet against batch/{batch_version}/train.parquet "
                f"for word-count and tone-formality drift."
            ),
            recommendations=recommendations,
        )
