from __future__ import annotations

from datetime import datetime, timezone

from zulip_data_quality_monitoring.checks.batch import BatchDatasetCheck
from zulip_data_quality_monitoring.checks.drift import DriftCheck
from zulip_data_quality_monitoring.checks.feedback import FeedbackCheck
from zulip_data_quality_monitoring.checks.online import OnlineLogsCheck
from zulip_data_quality_monitoring.checks.raw_dataset import RawDatasetCheck
from zulip_data_quality_monitoring.config import AppConfig
from zulip_data_quality_monitoring.models import Report
from zulip_data_quality_monitoring.reporting import overall_status
from zulip_data_quality_monitoring.storage import MinioStore


def run_all_checks(config: AppConfig) -> Report:
    store = MinioStore(config.storage)
    checks = [
        RawDatasetCheck(),
        BatchDatasetCheck(),
        OnlineLogsCheck(),
        FeedbackCheck(),
        DriftCheck(),
    ]
    results = [check.run(store, config) for check in checks]
    return Report(
        generated_at=datetime.now(timezone.utc).isoformat(),
        overall_status=overall_status(results),
        checks=results,
    )
