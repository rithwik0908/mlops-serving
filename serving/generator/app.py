"""
Tone Generator Microservice — FastAPI
Calls the classifier first, then generates 3 tone variants.

  POST /generate   → full pipeline (classify + generate all 3 variants)
  GET  /health     → liveness check
  GET  /ready      → readiness check
  GET  /metrics    → Prometheus metrics

CLASSIFIER_URL env var: URL of the classifier service (default: http://classifier:8001)
"""

import asyncio
import os
import logging
import threading
import time
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import JSONResponse, Response

from audit_log import log_generator_audit
from model import ToneGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLASSIFIER_URL = os.environ.get("CLASSIFIER_URL", "http://classifier:8001")
LATENCY_BUDGET_MS = float(os.environ.get("LATENCY_BUDGET_MS", "600"))
GENERATOR_MAX_CONCURRENT = max(1, int(os.environ.get("GENERATOR_MAX_CONCURRENT", "1")))
GENERATOR_MAX_QUEUE_WAIT_MS = float(os.environ.get("GENERATOR_MAX_QUEUE_WAIT_MS", "250"))

REQUEST_COUNT = Counter("generator_requests_total", "Total generator requests", ["status"])
LATENCY_HIST = Histogram(
    "generator_latency_seconds",
    "Generator inference latency",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.5, 2.0],
)
FEEDBACK_COUNT = Counter(
    "generator_feedback_total",
    "User feedback signals for generator outputs",
    ["user_action", "tone_shown"],
)
VARIANT_SOURCE_COUNT = Counter(
    "generator_variant_source_total",
    "Source of each generator tone variant",
    ["tone", "source"],
)
FALLBACK_REASON_COUNT = Counter(
    "generator_fallback_reason_total",
    "Fallback reasons observed for generator variants",
    ["tone", "reason"],
)
REQUEST_PATH_COUNT = Counter(
    "generator_request_path_total",
    "How often generator requests were fully model-backed vs fallback-assisted",
    ["path"],
)
INFLIGHT_GAUGE = Gauge(
    "generator_inflight_requests",
    "Current generator requests admitted for model execution",
)
QUEUE_WAIT_HIST = Histogram(
    "generator_queue_wait_seconds",
    "Time spent waiting for generator execution capacity",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.4, 0.8],
)
OVERLOAD_COUNT = Counter(
    "generator_overload_total",
    "Generator overload signals such as queue timeout",
    ["reason"],
)
LATENCY_BUDGET_EXCEEDED_COUNT = Counter(
    "generator_latency_budget_exceeded_total",
    "Generator requests that exceeded the configured latency budget",
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    message_id: str = Field(..., example="msg_0042")
    text: str = Field(..., min_length=1, max_length=2000,
                      example="yo can u just fix the bug already its been 3 days lol")
    message_type: str = Field(default="stream", example="stream")

class ToneVariant(BaseModel):
    text: str
    confidence: float | None = None
    source: str | None = None
    fallback_reason: str | None = None
    quality_flags: list[str] | None = None

class GenerateResponse(BaseModel):
    message_id: str
    original_text: str
    variants: dict[str, ToneVariant]
    classifier_result: dict
    generation_diagnostics: dict
    offensive_content_flagged: bool
    total_latency_ms: float


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
generator = None
classifier_client: httpx.AsyncClient | None = None
_load_exc: BaseException | None = None
_load_done = threading.Event()
_generator_lock = threading.Lock()
_generation_semaphore: asyncio.Semaphore | None = None


def _classifier_fallback() -> dict:
    return {"predicted_tone": "unknown", "probabilities": {}, "confidence": 0.0, "latency_ms": 0.0}


async def _fetch_classifier_result(message_id: str, text: str, message_type: str) -> dict:
    if classifier_client is None:
        return _classifier_fallback()
    try:
        cls_resp = await classifier_client.post(
            f"{CLASSIFIER_URL}/predict",
            json={"message_id": message_id, "text": text, "message_type": message_type},
        )
        cls_resp.raise_for_status()
        return cls_resp.json()
    except Exception as exc:
        logger.warning("Classifier call failed: %s — proceeding without classifier result", exc)
        return _classifier_fallback()


def _generate_with_lock(text: str) -> dict:
    with _generator_lock:
        if generator is None:
            raise RuntimeError("Generator not loaded")
        return generator.generate_all(text)


def _record_generation_diagnostics(diagnostics: dict) -> None:
    REQUEST_PATH_COUNT.labels(path=str(diagnostics.get("request_path", "unknown"))).inc()
    variant_diagnostics = diagnostics.get("variant_diagnostics") or {}
    if not isinstance(variant_diagnostics, dict):
        return
    for tone, tone_diag in variant_diagnostics.items():
        if not isinstance(tone_diag, dict):
            continue
        source = str(tone_diag.get("source") or "unknown")
        VARIANT_SOURCE_COUNT.labels(tone=str(tone), source=source).inc()
        reason = tone_diag.get("fallback_reason")
        if reason:
            FALLBACK_REASON_COUNT.labels(tone=str(tone), reason=str(reason)).inc()


def _load_generator_in_thread() -> None:
    global generator, _load_exc
    max_retries = 5
    wait_s = 15
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Loading generator (attempt %d/%d)", attempt, max_retries)
            generator = ToneGenerator()
            logger.info("Generator ready")
            last_exc = None
            break
        except BaseException as exc:
            last_exc = exc
            logger.exception("Generator load attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                logger.info("Retrying generator load in %ds...", wait_s)
                time.sleep(wait_s)
                wait_s = min(wait_s * 2, 120)
    _load_exc = last_exc
    _load_done.set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global generator, classifier_client, _load_exc, _generation_semaphore
    generator = None
    _load_exc = None
    _load_done.clear()
    _generation_semaphore = asyncio.Semaphore(GENERATOR_MAX_CONCURRENT)
    classifier_client = httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=0.5))
    thread = threading.Thread(target=_load_generator_in_thread, name="generator-load", daemon=True)
    thread.start()
    yield
    if classifier_client is not None:
        await classifier_client.aclose()
    classifier_client = None
    generator = None
    _load_exc = None
    _load_done.clear()
    _generation_semaphore = None


app = FastAPI(
    title="Tone Generator Service",
    description="LLM-based multi-tone message rewriter (Formal / Friendly / Neutral)",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not _load_done.is_set():
        return JSONResponse(status_code=503, content={"status": "loading"})
    if _load_exc is not None:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(_load_exc)})
    if generator is None:
        return JSONResponse(status_code=503, content={"status": "unknown"})
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    if not _load_done.is_set():
        raise HTTPException(status_code=503, detail="Model still loading")
    if _load_exc is not None:
        raise HTTPException(status_code=503, detail="Model load failed")
    if generator is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text field must not be blank")

    t_start = time.perf_counter()
    classifier_task = asyncio.create_task(
        _fetch_classifier_result(request.message_id, text, request.message_type)
    )
    if _generation_semaphore is None:
        classifier_task.cancel()
        with suppress(asyncio.CancelledError):
            await classifier_task
        raise HTTPException(status_code=503, detail="Generator capacity controller unavailable")

    admitted = False
    queue_wait_s = 0.0
    queue_started = time.perf_counter()
    try:
        await asyncio.wait_for(
            _generation_semaphore.acquire(),
            timeout=max(GENERATOR_MAX_QUEUE_WAIT_MS, 1.0) / 1000.0,
        )
        admitted = True
        queue_wait_s = time.perf_counter() - queue_started
        QUEUE_WAIT_HIST.observe(queue_wait_s)
        INFLIGHT_GAUGE.inc()
    except TimeoutError as exc:
        classifier_task.cancel()
        with suppress(asyncio.CancelledError):
            await classifier_task
        OVERLOAD_COUNT.labels(reason="queue_timeout").inc()
        REQUEST_COUNT.labels(status="error").inc()
        raise HTTPException(status_code=503, detail="Generator overloaded; try again shortly") from exc

    # Step 2: generate tone variants
    try:
        gen_result = await asyncio.to_thread(_generate_with_lock, text)
    except Exception as exc:
        classifier_task.cancel()
        with suppress(asyncio.CancelledError):
            await classifier_task
        REQUEST_COUNT.labels(status="error").inc()
        logger.exception("Generation error: %s", exc)
        raise HTTPException(status_code=500, detail="Generation error") from exc
    finally:
        if admitted:
            INFLIGHT_GAUGE.dec()
            _generation_semaphore.release()
    cls_result = await classifier_task
    diagnostics = dict(gen_result.get("diagnostics") or {})
    diagnostics["queue_wait_ms"] = round(queue_wait_s * 1000, 2)

    total_ms = (time.perf_counter() - t_start) * 1000
    REQUEST_COUNT.labels(status="ok").inc()
    LATENCY_HIST.observe(total_ms / 1000)
    if total_ms > LATENCY_BUDGET_MS:
        LATENCY_BUDGET_EXCEEDED_COUNT.inc()
        diagnostics["latency_budget_exceeded"] = True
        logger.warning(
            "Generator latency budget exceeded: %.2fms > %.2fms for message_id=%s",
            total_ms,
            LATENCY_BUDGET_MS,
            request.message_id,
        )
    else:
        diagnostics["latency_budget_exceeded"] = False
    _record_generation_diagnostics(diagnostics)

    variants = {
        tone: ToneVariant(
            text=v["text"],
            source=v.get("source"),
            fallback_reason=v.get("fallback_reason"),
            quality_flags=v.get("quality_flags"),
        )
        for tone, v in gen_result["variants"].items()
    }

    log_generator_audit(
        message_id=request.message_id,
        text=text,
        classifier_result=cls_result,
        variants=gen_result["variants"],
        generation_diagnostics=diagnostics,
        offensive_content_flagged=gen_result["offensive_content_flagged"],
        total_latency_ms=round(total_ms, 2),
    )

    return GenerateResponse(
        message_id=request.message_id,
        original_text=text,
        variants=variants,
        classifier_result=cls_result,
        generation_diagnostics=diagnostics,
        offensive_content_flagged=gen_result["offensive_content_flagged"],
        total_latency_ms=round(total_ms, 2),
    )


@app.post("/feedback")
async def generator_feedback(payload: dict):
    """Record user feedback signal. Increments Prometheus counter for Grafana visibility."""
    action = str(payload.get("user_action", "unknown"))
    tone = str(payload.get("tone_shown", "unknown"))
    FEEDBACK_COUNT.labels(user_action=action, tone_shown=tone).inc()
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
