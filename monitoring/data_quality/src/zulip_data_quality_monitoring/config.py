from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

import yaml


@dataclass
class StorageConfig:
    endpoint_url: str
    bucket: str
    access_key_env: str
    secret_key_env: str
    verify_ssl: bool = False
    addressing_style: str = "path"

    @property
    def access_key(self) -> str:
        return os.getenv(self.access_key_env, "")

    @property
    def secret_key(self) -> str:
        return os.getenv(self.secret_key_env, "")


@dataclass
class DatasetConfig:
    raw_version: str
    batch_version: str
    lookback_days: int = 7


@dataclass
class ReportConfig:
    json_path: str
    markdown_path: str


@dataclass
class AppConfig:
    storage: StorageConfig
    dataset: DatasetConfig
    thresholds: dict[str, float]
    reports: ReportConfig


def load_config(config_path: str | Path) -> AppConfig:
    with open(config_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return AppConfig(
        storage=StorageConfig(**raw["storage"]),
        dataset=DatasetConfig(**raw["dataset"]),
        thresholds=raw["thresholds"],
        reports=ReportConfig(**raw["reports"]),
    )
