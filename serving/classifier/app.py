"""
Tone Classifier Microservice — FastAPI
Supports three backends via SERVING_BACKEND env var:
  pytorch   – baseline PyTorch CPU (default)
  onnx      – ONNX Runtime (model-level optimization)
  quantized – INT8 dynamic quantization (model-level optimization)

Usage:
  SERVING_BACKEND=pytorch uvicorn app:app --host 0.0.0.0 --port 8001
"""

import os
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import JSONResponse, Response

from audit_log import log_classifier_audit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND = os.environ.get("SERVING_BACKEND", "pytorch").lower()

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter("classifier_requests_total", "Total classifier requests", ["status"])
LATENCY_HIST = Histogram(
    "classifier_latency_seconds",
    "Classifier inference latency",
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5],
)
# Feedback signals emitted by the Zulip bridge when users react to tone suggestions.
# thumbs_up / thumbs_down / selected / edited / ignored
FEEDBACK_COUNT = Counter(
    "classifier_feedback_total",
    "User feedback signals for classifier predictions",
    ["user_action"],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class ClassifierRequest(BaseModel):
    message_id: str = Field(..., example="msg_0042")
    text: str = Field(..., min_length=1, max_length=2000, example="yo can u just fix the bug already its been 3 days lol")
    message_type: str = Field(default="stream", example="stream")

class ToneProbabilities(BaseModel):
    formal: float
    friendly: float
    neutral: float

class ClassifierResponse(BaseModel):
    message_id: str
    predicted_tone: str
    probabilities: ToneProbabilities
    confidence: float
    latency_ms: float
    backend: str


# ---------------------------------------------------------------------------
# App lifecycle (background load so /health answers while MLflow+torch start)
# ---------------------------------------------------------------------------
classifier = None
_load_exc: BaseException | None = None
_load_done = threading.Event()

def _load_classifier_in_thread() -> None:
    """Runs in a daemon thread so Uvicorn can bind and /health works during long MLflow downloads.

    Retries up to 5 times with exponential backoff (30 s → 60 s → 120 s …) so transient
    errors (MLflow not yet ready, S3 network hiccup) are recovered without a pod restart.
    """
    global classifier, _load_exc
    max_retries = 5
    wait_s = 30
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Loading classifier backend: %s (attempt %d/%d)", BACKEND, attempt, max_retries)
            if BACKEND == "onnx":
                from model_onnx import OnnxToneClassifier
                classifier = OnnxToneClassifier()
            elif BACKEND == "quantized":
                from model_quantized import QuantizedToneClassifier
                classifier = QuantizedToneClassifier()
            else:
                from model import ToneClassifier
                classifier = ToneClassifier()
            logger.info("Classifier ready")
            last_exc = None
            break
        except BaseException as exc:
            last_exc = exc
            logger.exception("Classifier load attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                logger.info("Retrying in %ds...", wait_s)
                time.sleep(wait_s)
                wait_s = min(wait_s * 2, 120)
    _load_exc = last_exc
    _load_done.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global classifier, _load_exc
    classifier = None
    _load_exc = None
    _load_done.clear()
    thread = threading.Thread(target=_load_classifier_in_thread, name="classifier-load", daemon=True)
    thread.start()
    yield
    classifier = None
    _load_exc = None
    _load_done.clear()


app = FastAPI(
    title="Tone Classifier Service",
    description="DistilBERT-based 3-class tone classifier (Formal / Friendly / Neutral)",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    """Process is up (liveness). Does not wait for model download."""
    return {"status": "ok", "backend": BACKEND}


@app.get("/ready")
def ready():
    """Kubernetes readiness: 503 until model load finishes (or fails permanently)."""
    if not _load_done.is_set():
        return JSONResponse(
            status_code=503,
            content={"status": "loading", "backend": BACKEND},
        )
    if _load_exc is not None:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "backend": BACKEND, "detail": str(_load_exc)},
        )
    if classifier is None:
        return JSONResponse(status_code=503, content={"status": "unknown", "backend": BACKEND})
    return {"status": "ok", "backend": BACKEND}


@app.post("/predict", response_model=ClassifierResponse)
def predict(request: ClassifierRequest):
    if not _load_done.is_set():
        raise HTTPException(status_code=503, detail="Model still loading")
    if _load_exc is not None:
        raise HTTPException(status_code=503, detail="Model load failed")
    if classifier is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # Input sanitization: strip whitespace, reject empty after strip
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text field must not be blank")

    try:
        t_start = time.perf_counter()
        result = classifier.predict(text)
        wall_ms = (time.perf_counter() - t_start) * 1000
        REQUEST_COUNT.labels(status="ok").inc()
        LATENCY_HIST.observe(wall_ms / 1000)
        log_classifier_audit(
            message_id=request.message_id,
            text=text,
            predicted_tone=result["predicted_tone"],
            confidence=result["confidence"],
            backend=BACKEND,
            inference_latency_ms=float(result["latency_ms"]),
        )
        return ClassifierResponse(
            message_id=request.message_id,
            predicted_tone=result["predicted_tone"],
            probabilities=ToneProbabilities(**result["probabilities"]),
            confidence=result["confidence"],
            latency_ms=result["latency_ms"],
            backend=BACKEND,
        )
    except Exception as exc:
        REQUEST_COUNT.labels(status="error").inc()
        logger.exception("Prediction error: %s", exc)
        raise HTTPException(status_code=500, detail="Inference error") from exc


@app.post("/feedback")
def classifier_feedback(payload: dict):
    """
    Record a user feedback signal for a previous /predict call.
    Increments the Prometheus counter so Grafana can track approval rates.
    Actual persistence is done by the Zulip bridge writing to MinIO.
    """
    action = str(payload.get("user_action", "unknown"))
    FEEDBACK_COUNT.labels(user_action=action).inc()
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
