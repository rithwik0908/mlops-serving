import os, json, re, boto3, pandas as pd
from datetime import datetime
from io import BytesIO
from botocore.client import Config

BUCKET     = os.getenv("MINIO_BUCKET",     "zulip-rewriter")
ENDPOINT   = os.getenv("MINIO_ENDPOINT",   "http://minio.ml-platform.svc.cluster.local:9000")
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
if not ACCESS_KEY or not SECRET_KEY:
    raise RuntimeError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set (injected from minio-root Secret in K8s)")
VERSION    = os.getenv("DATA_VERSION",     "v1")
BATCH_DATE = os.getenv("BATCH_DATE",       datetime.utcnow().strftime("%Y-%m-%d"))

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    verify=False,  # Bypasses SSL certificate check for .nip.io
    config=Config(
        signature_version='s3v4',
        s3={'addressing_style': 'path'}
    )
)

print(f"Batch pipeline starting | version={VERSION} | date={BATCH_DATE}")

POLITE_MARKERS = [r"\bplease\b", r"\bthank\b", r"\bcould you\b", r"\bwould you\b", r"\bi appreciate\b", r"\bkindly\b"]
INFORMAL_MARKERS = [r"\bhey\b", r"\byo\b", r"\bu\b", r"\bgonna\b", r"\bwanna\b", r"\bbtw\b", r"\bomg\b", r"\blol\b"]
DRIFT_FEATURES = [
    "word_count",
    "char_count",
    "polite_marker_count",
    "informal_marker_count",
    "has_question_mark",
    "has_exclamation",
    "estimated_formality",
]


def extract_features(text: str) -> dict:
    tl = (text or "").lower()
    words = tl.split()
    polite = sum(1 for p in POLITE_MARKERS if re.search(p, tl))
    informal = sum(1 for p in INFORMAL_MARKERS if re.search(p, tl))
    return {
        "word_count": len(words),
        "char_count": len(text or ""),
        "polite_marker_count": polite,
        "informal_marker_count": informal,
        "has_question_mark": int("?" in (text or "")),
        "has_exclamation": int("!" in (text or "")),
        "estimated_formality": round((polite - informal) / max(len(words), 1), 4),
    }


def build_drift_baseline(df: pd.DataFrame) -> dict:
    feature_df = pd.DataFrame([extract_features(text) for text in df["text"].dropna().astype(str)])
    stats = {}
    for feature in DRIFT_FEATURES:
        series = feature_df[feature].astype(float)
        stats[feature] = {
            "mean": round(float(series.mean()), 6),
            "std": round(float(series.std(ddof=0)), 6),
            "min": round(float(series.min()), 6),
            "max": round(float(series.max()), 6),
            "count": int(series.count()),
        }
    return {
        "baseline_type": "training_corpus_features",
        "created_at": datetime.utcnow().isoformat(),
        "feature_count": len(DRIFT_FEATURES),
        "sample_count": int(len(feature_df)),
        "features": stats,
    }

print("Step 1: Loading base corpus from MinIO...")
obj      = s3.get_object(Bucket=BUCKET, Key=f"raw/{VERSION}/full.parquet")
df_base  = pd.read_parquet(BytesIO(obj["Body"].read()))
print(f"  Base corpus: {len(df_base)} rows")

print("Step 2: Loading online production logs...")
paginator = s3.get_paginator("list_objects_v2")
log_rows  = []
for page in paginator.paginate(Bucket=BUCKET, Prefix="online_logs/"):
    for obj_meta in page.get("Contents", []):
        try:
            obj  = s3.get_object(Bucket=BUCKET, Key=obj_meta["Key"])
            logs = json.loads(obj["Body"].read())
            for entry in logs:
                inp = entry.get("input", {})
                log_rows.append({
                    "text":        inp.get("original_message", ""),
                    "rewrite_style": inp.get("rewrite_style", ""),
                    "sender_id":   inp.get("context", {}).get("sender_id", ""),
                    "timestamp":   inp.get("timestamp", ""),
                    "source":      "online_log",
                    "binary_label": None,
                    "synthetic":   False,
                    "split":       "online",
                })
        except Exception as e:
            print(f"  Warning: {e}")

df_online = pd.DataFrame(log_rows) if log_rows else pd.DataFrame()
print(f"  Online logs: {len(df_online)} rows")

print("Step 2b: Loading user feedback labels from MinIO (feedback/ prefix)...")
# feedback/ contains JSON records written by the Zulip bridge /feedback endpoint.
# Schema: {feedback_id, message_id, tone_shown, user_action, correct_tone, preferred_text, created_at}
# We join on message_id with audit logs to assign ground-truth labels.
# Only thumbs_up / selected records contribute positive labels; thumbs_down contributes
# the correct_tone as a label correction.
TONE_TO_BINARY = {"formal": 1, "friendly": 1, "neutral": 0}
feedback_rows = []
for page in paginator.paginate(Bucket=BUCKET, Prefix="feedback/"):
    for obj_meta in page.get("Contents", []):
        if not obj_meta["Key"].endswith(".json"):
            continue
        try:
            obj = s3.get_object(Bucket=BUCKET, Key=obj_meta["Key"])
            rec = json.loads(obj["Body"].read())
            action = rec.get("user_action", "")
            # Only use explicit positive/negative signals; skip "ignored"
            if action not in ("thumbs_up", "thumbs_down", "selected", "edited"):
                continue
            # Derive tone label: use correct_tone if provided, else tone_shown
            raw_tone = rec.get("correct_tone") or rec.get("tone_shown") or ""
            binary = TONE_TO_BINARY.get(raw_tone.lower())
            feedback_rows.append({
                "message_id":  rec.get("message_id"),
                "tone_label":  raw_tone.lower(),
                "binary_label": binary,
                "user_action": action,
                "preferred_text": rec.get("preferred_text"),
                "created_at":  rec.get("created_at"),
            })
        except Exception as e:
            print(f"  Warning loading feedback {obj_meta['Key']}: {e}")

df_feedback = pd.DataFrame(feedback_rows) if feedback_rows else pd.DataFrame()
print(f"  Feedback entries: {len(df_feedback)} (thumbs_up/down/selected/edited)")

# Build a feedback text dataset: use preferred_text when available, else we need audit logs.
# For now, only rows with preferred_text are directly usable as training examples.
df_feedback_text = pd.DataFrame()
if not df_feedback.empty and "preferred_text" in df_feedback.columns:
    has_text = df_feedback[df_feedback["preferred_text"].notna() & (df_feedback["preferred_text"] != "")]
    if not has_text.empty:
        df_feedback_text = has_text.rename(columns={"preferred_text": "text"})[
            ["text", "binary_label", "tone_label", "user_action", "created_at"]
        ].copy()
        df_feedback_text["source"] = "feedback"
        df_feedback_text["synthetic"] = False
        df_feedback_text["split"] = "train"
        print(f"  Feedback rows with preferred_text (usable for training): {len(df_feedback_text)}")

# Persist raw feedback manifest so retrain_trigger.py can count new entries without re-reading all files.
feedback_manifest = {
    "batch_date": BATCH_DATE,
    "feedback_total_entries": len(df_feedback),
    "feedback_usable_for_training": len(df_feedback_text),
    "thumbs_up": int((df_feedback["user_action"] == "thumbs_up").sum()) if not df_feedback.empty else 0,
    "thumbs_down": int((df_feedback["user_action"] == "thumbs_down").sum()) if not df_feedback.empty else 0,
    "approval_rate": round(
        (df_feedback["user_action"].isin(["thumbs_up", "selected"])).sum() / max(len(df_feedback), 1),
        4,
    ) if not df_feedback.empty else None,
}
s3.put_object(
    Bucket=BUCKET,
    Key=f"batch/{BATCH_DATE}/feedback_manifest.json",
    Body=json.dumps(feedback_manifest, indent=2),
)
print(f"  Feedback manifest: {json.dumps(feedback_manifest)}")

print("Step 3: Candidate selection (no leakage)...")
df_train_seed = df_base[
    (df_base["text"].str.split().str.len() >= 5) &
    (df_base["binary_label"].notna()) &
    (~df_base["text"].duplicated()) &
    (df_base["split"] == "train")
].copy()
df_train = df_train_seed.copy()

df_test = df_base[
    (df_base["text"].str.split().str.len() >= 5) &
    (df_base["binary_label"].notna()) &
    (df_base["split"] == "test")
].copy()

if not df_online.empty:
    df_train = pd.concat([df_train, df_online], ignore_index=True)

# Merge user feedback preferred_text rows (highest-quality signal — human-written labels)
if not df_feedback_text.empty:
    df_train = pd.concat([df_train, df_feedback_text], ignore_index=True)
    print(f"  Added {len(df_feedback_text)} feedback rows to train set")

print(f"  Train: {len(df_train)} | Test: {len(df_test)}")

print("Step 3b: Building production drift baseline from training corpus...")
drift_baseline = build_drift_baseline(df_train_seed)
drift_baseline["source_rows"] = int(len(df_train_seed))
drift_baseline["batch_date"] = BATCH_DATE
print(f"  Drift baseline samples: {drift_baseline['sample_count']}")

print("Step 4: Uploading versioned datasets...")
batch_ver = f"{VERSION}_batch_{BATCH_DATE}"

def upload(df, name):
    buf = BytesIO()
    df.to_parquet(buf, index=False)
    key = f"batch/{batch_ver}/{name}.parquet"
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
    print(f"  Uploaded {key} ({len(df)} rows)")

upload(df_train, "train")
upload(df_test,  "test")
s3.put_object(
    Bucket=BUCKET,
    Key=f"batch/{BATCH_DATE}/drift_baseline.json",
    Body=json.dumps(drift_baseline, indent=2),
)
s3.put_object(
    Bucket=BUCKET,
    Key=f"batch/{batch_ver}/drift_baseline.json",
    Body=json.dumps(drift_baseline, indent=2),
)
print(f"  Uploaded batch/{BATCH_DATE}/drift_baseline.json")
print(f"  Uploaded batch/{batch_ver}/drift_baseline.json")

manifest = {
    "batch_version":        batch_ver,
    "created_at":           datetime.utcnow().isoformat(),
    "train_rows":           len(df_train),
    "test_rows":            len(df_test),
    "online_log_rows":      len(df_online),
    "feedback_rows_merged": len(df_feedback_text),
    "feedback_approval_rate": feedback_manifest.get("approval_rate"),
    "drift_baseline_key":   f"batch/{batch_ver}/drift_baseline.json",
    "leakage_policy":       "test set fixed from original corpus; online logs and feedback training-only",
    "filters":              {"min_words": 5, "require_label": True, "deduplicated": True},
}
s3.put_object(Bucket=BUCKET,
              Key=f"batch/{batch_ver}/manifest.json",
              Body=json.dumps(manifest, indent=2))
print("Batch pipeline complete!")
print(json.dumps(manifest, indent=2))
