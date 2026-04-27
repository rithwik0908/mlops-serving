from __future__ import annotations

from zulip_data_quality_monitoring.config import AppConfig
from zulip_data_quality_monitoring.models import CheckResult
from zulip_data_quality_monitoring.storage import MinioStore


class BaseCheck:
    name = "base"

    def run(self, store: MinioStore, config: AppConfig) -> CheckResult:
        raise NotImplementedError
