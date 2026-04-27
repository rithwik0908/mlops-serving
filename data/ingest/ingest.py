import json
import os

import boto3
import pandas as pd
from botocore.client import Config

BUCKET = os.getenv("MINIO_BUCKET", "zulip-rewriter")
ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio.ml-platform.svc.cluster.local:9000")
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
VERSION = os.getenv("DATA_VERSION", "v1")


def build_seed_corpus() -> pd.DataFrame:
    rows = [
        {"id": "seed-001", "text": "Could you please review this patch when you have a moment?", "binary_label": 1, "community": "seed", "split": "train"},
        {"id": "seed-002", "text": "Thank you for flagging the issue so quickly.", "binary_label": 1, "community": "seed", "split": "train"},
        {"id": "seed-003", "text": "Would you mind sharing the stack trace for this failure?", "binary_label": 1, "community": "seed", "split": "train"},
        {"id": "seed-004", "text": "I appreciate the help with the deployment checklist.", "binary_label": 1, "community": "seed", "split": "train"},
        {"id": "seed-005", "text": "Please update the ticket once the hotfix is deployed.", "binary_label": 1, "community": "seed", "split": "train"},
        {"id": "seed-006", "text": "Can you send the metrics after the next training run?", "binary_label": 0, "community": "seed", "split": "train"},
        {"id": "seed-007", "text": "The service restarted again after the config change.", "binary_label": 0, "community": "seed", "split": "train"},
        {"id": "seed-008", "text": "I pushed a new model version to the registry.", "binary_label": 0, "community": "seed", "split": "train"},
        {"id": "seed-009", "text": "The logs show a timeout on the MinIO upload step.", "binary_label": 0, "community": "seed", "split": "train"},
        {"id": "seed-010", "text": "We should compare the staging and production metrics.", "binary_label": 0, "community": "seed", "split": "train"},
        {"id": "seed-011", "text": "hey fix this now", "binary_label": -1, "community": "seed", "split": "train"},
        {"id": "seed-012", "text": "yo can you stop breaking the pipeline", "binary_label": -1, "community": "seed", "split": "train"},
        {"id": "seed-013", "text": "just push the model already", "binary_label": -1, "community": "seed", "split": "train"},
        {"id": "seed-014", "text": "why did you ignore the error again", "binary_label": -1, "community": "seed", "split": "train"},
        {"id": "seed-015", "text": "this dashboard is useless lol", "binary_label": -1, "community": "seed", "split": "train"},
        {"id": "seed-016", "text": "Could you help confirm the worker node is healthy?", "binary_label": 1, "community": "seed", "split": "test"},
        {"id": "seed-017", "text": "Please double-check the ingress host after the redeploy.", "binary_label": 1, "community": "seed", "split": "test"},
        {"id": "seed-018", "text": "The experiment completed and logged metrics to MLflow.", "binary_label": 0, "community": "seed", "split": "test"},
        {"id": "seed-019", "text": "Can you share the prediction latency numbers?", "binary_label": 0, "community": "seed", "split": "test"},
        {"id": "seed-020", "text": "hey this rollout is still broken", "binary_label": -1, "community": "seed", "split": "test"},
        {"id": "seed-021", "text": "just restart the pod and hope it works", "binary_label": -1, "community": "seed", "split": "test"},
    ]
    df = pd.DataFrame(rows)
    score_map = {1: 0.85, 0: 0.0, -1: -0.85}
    df["normalized_score"] = df["binary_label"].map(score_map)
    df["synthetic"] = False
    return df


def augment(df: pd.DataFrame) -> pd.DataFrame:
    polite_prefixes = ["Could you please ", "Would you mind ", "I would appreciate it if "]
    informal_prefixes = ["hey ", "just ", "yo can you "]
    synthetic_rows = []

    for row in df.to_dict("records"):
        if row["binary_label"] == 1:
            for prefix in polite_prefixes:
                new_row = dict(row)
                new_row["text"] = prefix + row["text"]
                new_row["synthetic"] = True
                synthetic_rows.append(new_row)
        elif row["binary_label"] == -1:
            for prefix in informal_prefixes:
                new_row = dict(row)
                new_row["text"] = prefix + row["text"]
                new_row["synthetic"] = True
                synthetic_rows.append(new_row)

    return pd.concat([df, pd.DataFrame(synthetic_rows)], ignore_index=True)


def stratified_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_parts = []
    val_parts = []
    test_parts = []

    for label, group in df.groupby("binary_label", dropna=False):
        shuffled = group.sample(frac=1.0, random_state=42).reset_index(drop=True)
        n = len(shuffled)
        n_test = max(1, round(n * 0.1))
        n_val = max(1, round(n * 0.1))
        if n_test + n_val >= n:
            n_test = 1
            n_val = 1 if n > 2 else 0
        test_parts.append(shuffled.iloc[:n_test])
        val_parts.append(shuffled.iloc[n_test : n_test + n_val])
        train_parts.append(shuffled.iloc[n_test + n_val :])

    return (
        pd.concat(train_parts, ignore_index=True),
        pd.concat(val_parts, ignore_index=True),
        pd.concat(test_parts, ignore_index=True),
    )


print("Step 1: Building seed politeness corpus...")
df = build_seed_corpus()
print(f"Loaded {len(df)} seed rows")
print(df["binary_label"].value_counts().to_dict())

print("Step 2: Synthetic augmentation...")
df_aug = augment(df)
print(f"After augmentation: {len(df_aug)} rows")

print("Step 3: Train/val/test split...")
df_train, df_val, df_test = stratified_split(df_aug)
print(f"Train: {len(df_train)} | Val: {len(df_val)} | Test: {len(df_test)}")

print("Step 4: Uploading to MinIO...")
s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    verify=False,
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)

try:
    s3.create_bucket(Bucket=BUCKET)
    print(f"Bucket '{BUCKET}' created")
except Exception:
    print(f"Bucket '{BUCKET}' already exists")


def upload(df_part: pd.DataFrame, name: str) -> None:
    path = f"/tmp/{name}.parquet"
    df_part.to_parquet(path, index=False)
    key = f"raw/{VERSION}/{name}.parquet"
    s3.upload_file(path, BUCKET, key)
    print(f"Uploaded {key} ({len(df_part)} rows)")


upload(df_train, "train")
upload(df_val, "val")
upload(df_test, "test")
upload(df_aug, "full")

manifest = {
    "version": VERSION,
    "source": "embedded-seed-corpus",
    "total_rows": len(df_aug),
    "original_rows": len(df),
    "synthetic_rows": int(df_aug["synthetic"].sum()),
    "splits": {"train": len(df_train), "val": len(df_val), "test": len(df_test)},
    "schema": {
        "id": "string - sample ID",
        "text": "string - message text",
        "normalized_score": "float - approximate politeness score",
        "binary_label": "int - 1=polite, 0=neutral, -1=impolite",
        "community": "string - source domain",
        "split": "string - source split",
        "synthetic": "bool - True if augmented",
    },
    "ingested_at": pd.Timestamp.utcnow().isoformat(),
}
with open("/tmp/manifest.json", "w", encoding="utf-8") as file_obj:
    json.dump(manifest, file_obj, indent=2)
s3.upload_file("/tmp/manifest.json", BUCKET, f"raw/{VERSION}/manifest.json")
print("Manifest uploaded.")
print("Ingestion complete!")
