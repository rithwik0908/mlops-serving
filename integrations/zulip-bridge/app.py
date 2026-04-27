"""
HTTP bridge: Zulip outgoing webhook / slash-command style payloads → tone generator /generate.

- Validates optional ZULIP_WEBHOOK_SECRET against body.token (Zulip outgoing webhooks).
- Returns Zulip-compatible JSON: {"content": "..."} for bot replies.
- Rate limit: simple in-process limiter per client IP (demo-grade; use Redis in real prod).
- POST /feedback: persists user thumbs-up/down + tone corrections to MinIO for retraining.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Literal

import boto3
import httpx
from botocore.client import Config
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GENERATOR_URL = os.environ.get("GENERATOR_URL", "http://tone-generator-prod:8010").rstrip("/")
ZULIP_WEBHOOK_SECRET = os.environ.get("ZULIP_WEBHOOK_SECRET", "").strip()
MAX_MESSAGE_LEN = int(os.environ.get("MAX_MESSAGE_LEN", "2000"))
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", "65536"))
RATE_PER_MINUTE = int(os.environ.get("RATE_PER_MINUTE", "60"))
REDACT_LOGS = os.environ.get("REDACT_LOGS", "true").lower() in ("1", "true", "yes")

# MinIO / S3 config for feedback persistence
_MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio.ml-platform.svc.cluster.local:9000")
_MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "zulip-rewriter")
_MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
_MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")

# Prometheus feedback counters (visible in Grafana via /metrics)
FEEDBACK_COUNTER = Counter(
    "bridge_feedback_total",
    "User feedback signals received",
    ["user_action", "tone_shown"],
)
FEATURE_LOG_COUNTER = Counter(
    "bridge_feature_log_total",
    "Production request feature logs written for drift detection",
)

POLITE_MARKERS = [
    r"\bplease\b",
    r"\bthank\b",
    r"\bcould you\b",
    r"\bwould you\b",
    r"\bi appreciate\b",
    r"\bkindly\b",
]
INFORMAL_MARKERS = [
    r"\bhey\b",
    r"\byo\b",
    r"\bu\b",
    r"\bgonna\b",
    r"\bwanna\b",
    r"\bbtw\b",
    r"\bomg\b",
    r"\blol\b",
]


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=_MINIO_ENDPOINT,
        aws_access_key_id=_MINIO_ACCESS_KEY,
        aws_secret_access_key=_MINIO_SECRET_KEY,
        verify=False,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _write_feedback_to_minio(record: dict) -> None:
    """Write one feedback JSON record to MinIO under feedback/YYYY-MM-DD/{uuid}.json."""
    if not _MINIO_ACCESS_KEY:
        logger.debug("MINIO_ACCESS_KEY not set — feedback not persisted")
        return
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"feedback/{today}/{record['feedback_id']}.json"
        _s3_client().put_object(
            Bucket=_MINIO_BUCKET,
            Key=key,
            Body=json.dumps(record, ensure_ascii=False).encode(),
            ContentType="application/json",
        )
        logger.info("feedback persisted key=%s", key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("feedback MinIO write failed (non-fatal): %s", exc)


def _extract_text_features(text: str) -> dict[str, float | int]:
    tl = text.lower()
    words = tl.split()
    polite = sum(1 for pattern in POLITE_MARKERS if re.search(pattern, tl))
    informal = sum(1 for pattern in INFORMAL_MARKERS if re.search(pattern, tl))
    return {
        "word_count": len(words),
        "char_count": len(text),
        "polite_marker_count": polite,
        "informal_marker_count": informal,
        "has_question_mark": int("?" in text),
        "has_exclamation": int("!" in text),
        "estimated_formality": round((polite - informal) / max(len(words), 1), 4),
    }


def _write_feature_log_to_minio(message_id: str, text: str, message_type: str) -> None:
    """Persist privacy-preserving live request features for drift detection."""
    if not _MINIO_ACCESS_KEY:
        logger.debug("MINIO_ACCESS_KEY not set — feature log not persisted")
        return

    now = datetime.now(timezone.utc)
    record = {
        "log_id": str(uuid.uuid4()),
        "message_id": message_id,
        "message_type": message_type,
        "created_at": now.isoformat(),
        "features": _extract_text_features(text),
    }
    key = f"feature_logs/{now.strftime('%Y-%m-%d')}/{record['log_id']}_{message_id}.json"
    try:
        _s3_client().put_object(
            Bucket=_MINIO_BUCKET,
            Key=key,
            Body=json.dumps(record, ensure_ascii=False).encode(),
            ContentType="application/json",
        )
        FEATURE_LOG_COUNTER.inc()
        logger.info("feature log persisted key=%s", key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("feature log MinIO write failed (non-fatal): %s", exc)

app = FastAPI(title="Zulip tone bridge", version="1.0.0")

# --- naive sliding-window rate limit per IP ---
_window: deque[tuple[float, str]] = deque()


def _rate_ok(client_ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - 60.0
    while _window and _window[0][0] < cutoff:
        _window.popleft()
    recent = sum(1 for t, ip in _window if ip == client_ip)
    if recent >= RATE_PER_MINUTE:
        return False
    _window.append((now, client_ip))
    return True


def _redact(s: str, max_len: int = 80) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ")
    return (s[:max_len] + "…") if len(s) > max_len else s


def _extract_user_text(payload: dict[str, Any]) -> tuple[str, str]:
    """Returns (message_id, plain_text_for_model)."""
    # Direct API (curl / tests): same shape as contracts/classifier_input.json
    if "text" in payload and isinstance(payload["text"], str):
        mid = str(payload.get("message_id") or payload.get("id") or "zulip-0")
        return mid, payload["text"].strip()

    # Zulip outgoing webhook / generic bot payload
    msg = payload.get("message")
    if isinstance(msg, dict):
        content = (msg.get("content") or "").strip()
        mid = str(msg.get("id") or payload.get("message_id") or "zulip-0")
        # Strip common leading @**bot** ... mentions (best-effort)
        content = re.sub(r"^\s*@\*\*[^\n]+\*\*\s*", "", content)
        return mid, content.strip()

    data = payload.get("data")
    if isinstance(data, str) and data.strip():
        return str(payload.get("message_id") or "zulip-0"), data.strip()

    raise ValueError("No usable text in payload (expected `text` or `message.content`)")


def _zulip_reply_markdown(gen_json: dict[str, Any]) -> str:
    lines = ["### Tone suggestions", ""]
    variants = gen_json.get("variants") or {}
    for tone, body in variants.items():
        if isinstance(body, dict):
            text = (body.get("text") or "").strip()
        else:
            text = str(body).strip()
        lines.append(f"- **{tone}:** {text}")
    lines.append("")
    cr = gen_json.get("classifier_result") or {}
    tone = cr.get("predicted_tone") or cr.get("label") or "unknown"
    lines.append(f"_Classifier: `{tone}`_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Feedback schemas
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="message_id from the /generate response")
    tone_shown: str = Field(..., description="Which tone variant was presented (formal/friendly/neutral)")
    user_action: Literal["thumbs_up", "thumbs_down", "selected", "edited", "ignored"] = Field(
        ..., description="Signal: thumbs_up=positive, thumbs_down=negative, selected=user picked this tone, edited=user modified it, ignored=user discarded"
    )
    correct_tone: str | None = Field(None, description="If thumbs_down: which tone the user preferred")
    preferred_text: str | None = Field(None, description="If edited: the user's rewritten text (max 2000 chars)")

class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str
    message_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/feedback", response_model=FeedbackResponse)
def feedback(req: FeedbackRequest) -> FeedbackResponse:
    """
    Persist user feedback for a previous /generate call.
    Keyed by message_id so it can be joined with audit logs for retraining.

    Zulip bot flow:
      1. Bot calls /zulip/webhook → gets tone suggestions → posts them with reactions.
      2. User reacts with 👍/👎 (or clicks a tone button) → bot calls POST /feedback.
      3. Feedback lands in MinIO feedback/YYYY-MM-DD/ → batch pipeline joins it with
         classifier audit logs → training dataset for next retrain.
    """
    fid = str(uuid.uuid4())
    record = {
        "feedback_id": fid,
        "message_id": req.message_id,
        "tone_shown": req.tone_shown,
        "user_action": req.user_action,
        "correct_tone": req.correct_tone,
        "preferred_text": (req.preferred_text or "")[:2000] if req.preferred_text else None,
        "source": "zulip-bridge",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    FEEDBACK_COUNTER.labels(user_action=req.user_action, tone_shown=req.tone_shown).inc()
    _write_feedback_to_minio(record)
    logger.info(
        "feedback id=%s message_id=%s action=%s tone=%s correct=%s",
        fid, req.message_id, req.user_action, req.tone_shown, req.correct_tone,
    )
    return FeedbackResponse(status="ok", feedback_id=fid, message_id=req.message_id)


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/zulip/webhook")
async def zulip_webhook(request: Request) -> JSONResponse:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")

    client = request.client.host if request.client else "unknown"
    if not _rate_ok(client):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc

    if ZULIP_WEBHOOK_SECRET:
        token = str(payload.get("token") or "")
        if token != ZULIP_WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="invalid webhook token")

    try:
        message_id, text = _extract_user_text(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not text:
        return JSONResponse({"content": "_No text to rewrite._"})

    if len(text) > MAX_MESSAGE_LEN:
        text = text[:MAX_MESSAGE_LEN]

    if REDACT_LOGS:
        logger.info("bridge request id=%s text_len=%s", message_id, len(text))
    else:
        logger.info("bridge request id=%s text=%s", message_id, _redact(text))

    gen_payload = {
        "message_id": message_id,
        "text": text,
        "message_type": str(payload.get("message_type") or "stream"),
    }
    _write_feature_log_to_minio(
        message_id=message_id,
        text=text,
        message_type=gen_payload["message_type"],
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client_http:
            r = await client_http.post(
                f"{GENERATOR_URL}/generate",
                json=gen_payload,
            )
            r.raise_for_status()
            gen_json = r.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("generator HTTP error: %s", exc)
        return JSONResponse(
            {"content": f"_Generator error (`{exc.response.status_code}`). Try again later._"},
            status_code=200,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("generator call failed: %s", exc)
        return JSONResponse(
            {"content": "_Tone service temporarily unavailable._"},
            status_code=200,
        )

    return JSONResponse({"content": _zulip_reply_markdown(gen_json)})


@app.post("/generate")
async def proxy_generate(request: Request) -> Response:
    """Passthrough POST body to generator /generate (smoke tests)."""
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    ct = request.headers.get("content-type", "application/json")
    async with httpx.AsyncClient(timeout=120.0) as client_http:
        r = await client_http.post(
            f"{GENERATOR_URL}/generate",
            content=body,
            headers={"Content-Type": ct},
        )
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )
