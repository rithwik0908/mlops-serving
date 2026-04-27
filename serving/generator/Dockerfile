# Tone Generator Service
# Build:  docker build -t tone-generator .
# Run (dummy mode, no GPU needed — default):
#   docker run -p 8010:8010 tone-generator
#
# Run (real seq2seq on GPU — Flan-T5):
#   docker run --gpus all \
#     -e DUMMY_MODE=false \
#     -e GENERATOR_BACKEND=seq2seq \
#     -e MODEL_NAME=google/flan-t5-base \
#     -e CLASSIFIER_URL=http://classifier:8001 \
#     -p 8010:8010 tone-generator
#
# Run (real causal + LoRA — same stack as training_proj15 train_llm.py):
#   docker run --gpus all \
#     -e DUMMY_MODE=false \
#     -e GENERATOR_BACKEND=causal \
#     -e MODEL_NAME=HuggingFaceTB/SmolLM2-135M-Instruct \
#     -e PEFT_MODEL_PATH=/models/lora \
#     -v /path/to/lora_checkpoint:/models/lora:ro \
#     -p 8010:8010 tone-generator

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Core API deps + optional torch/transformers/peft for DUMMY_MODE=false
COPY requirements.txt requirements-llm.txt ./
ARG INSTALL_LLM_DEPS=true
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_LLM_DEPS" = "true" ]; then \
      pip install --no-cache-dir -r requirements-llm.txt; \
    fi

COPY app.py audit_log.py model.py ./

# Non-root user
RUN useradd -m -u 1000 appuser
USER appuser

ENV DUMMY_MODE=true
ENV GENERATOR_BACKEND=seq2seq
ENV MODEL_NAME=google/flan-t5-base
ENV PEFT_MODEL_PATH=
ENV CLASSIFIER_URL=http://classifier:8001
ENV LATENCY_BUDGET_MS=600
ENV GENERATOR_MAX_CONCURRENT=1
ENV GENERATOR_MAX_QUEUE_WAIT_MS=250

EXPOSE 8010

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:8010/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
