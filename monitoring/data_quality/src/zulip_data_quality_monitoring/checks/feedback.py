from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from zulip_data_quality_monitoring.checks.base import BaseCheck
from zulip_data_quality_monitoring.metrics import ratio
from zulip_data_quality_monitoring.models import CheckResult


class FeedbackCheck(BaseCheck):
    name = "feedback_quality"

    def run(self, store, config) -> CheckResult:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=config.dataset.lookback_days)
        keys = store.list_keys("feedback/")
        recent_keys = []
        for key in keys:
            parts = key.split("/")
            if len(parts) < 3:
                continue
            try:
                day = datetime.strptime(parts[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if day >= cutoff and key.endswith(".json"):
                recent_keys.append(key)

        rows = [store.read_json(key) for key in recent_keys]
        frame = pd.DataFrame(rows)
        if frame.empty:
            return CheckResult(
                name=self.name,
                status="warn",
                metrics={"recent_feedback_rows": 0},
                summary="No recent feedback records were found.",
                recommendations=["Capture explicit thumbs_up, thumbs_down, selected, or edited events from the Zulip bridge."],
            )

        approvals = frame["user_action"].isin(["thumbs_up", "selected"])
        corrections = frame["user_action"].isin(["thumbs_down", "edited"])
        preferred_text = frame.get("preferred_text", pd.Series(dtype=str)).fillna("").astype(str).str.strip() != ""
        metrics = {
            "recent_feedback_rows": len(frame),
            "approval_rate": ratio(float(approvals.sum()), float(len(frame))),
            "correction_rate": ratio(float(corrections.sum()), float(len(frame))),
            "preferred_text_rate": ratio(float(preferred_text.sum()), float(len(frame))),
            "missing_preferred_text_rate": 1 - ratio(float(preferred_text.sum()), float(len(frame))),
            "tone_shown_distribution": frame.get("tone_shown", pd.Series(dtype=str)).fillna("unknown").value_counts(normalize=True).round(4).to_dict(),
        }
        passed = (
            metrics["approval_rate"] >= config.thresholds["min_feedback_approval_rate"]
            and metrics["missing_preferred_text_rate"] <= config.thresholds["max_missing_preferred_text_rate"]
        )
        recommendations = []
        if metrics["preferred_text_rate"] < 0.3:
            recommendations.append("Collect more user-edited or selected text so feedback can contribute stronger supervised training signal.")
        if metrics["approval_rate"] < config.thresholds["min_feedback_approval_rate"]:
            recommendations.append("Escalate low approval rate as a retraining and product-quality issue.")
        return CheckResult(
            name=self.name,
            status="pass" if passed else "warn",
            metrics=metrics,
            summary=f"Recent feedback approval_rate={metrics['approval_rate']} across {metrics['recent_feedback_rows']} records.",
            recommendations=recommendations,
        )
