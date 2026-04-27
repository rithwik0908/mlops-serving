from __future__ import annotations

import json
from io import BytesIO

import boto3
import pandas as pd
from botocore.client import Config as BotoConfig

from zulip_data_quality_monitoring.config import StorageConfig


class MinioStore:
    def __init__(self, config: StorageConfig) -> None:
        self.bucket = config.bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            verify=config.verify_ssl,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": config.addressing_style},
            ),
        )

    def read_json(self, key: str) -> dict:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return json.loads(body)

    def read_parquet(self, key: str) -> pd.DataFrame:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return pd.read_parquet(BytesIO(body))

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return keys

    def write_text(self, key: str, text: str, content_type: str = "text/plain") -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType=content_type,
        )
