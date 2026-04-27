# Safeguarding Plan — Multi-Tone Communication Assistant

This document describes the **active safeguarding mechanisms** implemented across the system.
It covers the six principles required by the course rubric: Fairness, Explainability, Transparency,
Privacy, Accountability, and Robustness. Each section identifies **where** the mechanism lives in the
codebase and **how** it is enforced at runtime.

---

## 1. Fairness

**Requirement:** The system must not systematically disadvantage any communication style (tone class).

### Mechanisms

| Mechanism | Location | How it works |
|-----------|----------|--------------|
| Per-class F1 quality gate | `k8s/training/register-bundle/job.yaml` | `--min-classifier-worst-class-f1=0.55` — a new model is promoted to `@canary` only if _every_ tone class (formal / friendly / neutral) achieves F1 ≥ 0.55. Prevents a model that is accurate on average but ignores a minority class. |
| Macro F1 gate | same | `--min-classifier-f1-macro=0.70` — overall macro-averaged F1 (gives equal weight to each class regardless of frequency). |
| Per-class metrics in MLflow | `training_proj15-main/training/train.py` | Logs `f1_formal`, `f1_friendly`, `f1_neutral` alongside `f1_macro` and `accuracy` for every training run, enabling post-hoc audit. |
| Balanced evaluation split | training data pipeline | `data/batch/batch_pipeline.py` samples feedback uniformly across tone labels when constructing training manifests. |

---

## 2. Explainability

**Requirement:** Users must be able to understand why the system made a suggestion.

### Mechanisms

| Mechanism | Location | How it works |
|-----------|----------|--------------|
| Confidence score in every response | `serving/classifier/app.py` → `ClassifierResponse` | Each `/predict` response includes `predicted_tone`, `probabilities` (all three classes), and `confidence` (max probability). The Zulip bridge surfaces these to the user. |
| Probability breakdown | `serving/classifier/app.py` → `ToneProbabilities` | Returns all three class probabilities, not just the winner. Users can see how uncertain the classifier is. |
| DUMMY_MODE flag surfaced in response | `ClassifierResponse.backend` field | Indicates whether the response came from a real model or the heuristic stub, so engineers can identify stub-backed responses in logs. |
| Grafana dashboard | `k8s/platform/observability/dashboards/ml-serving-tone.json` | Real-time latency, error ratio, and feedback approval rates are visible to the team. |

---

## 3. Transparency

**Requirement:** The full lifecycle of models must be observable and reproducible.

### Mechanisms

| Mechanism | Location | How it works |
|-----------|----------|--------------|
| MLflow experiment tracking | `training_proj15-main/training/train.py`, `train_llm.py` | Every training run logs hyperparameters, metrics, and model artifacts. Experiments `teamchat_tone_clf` and `teamchat_tone_generator_llm` are queryable via MLflow UI (`https://mlflow.<host>`). |
| Model registry with versioned aliases | `k8s/training/register-bundle/scripts/register_and_alias_latest.py` | Models are promoted through named aliases (`@canary`, `@prod`). Each alias points to a specific numbered version; the full promotion history is preserved in MLflow. |
| Git-tracked training code | `training_proj15-main/` | All training scripts, configs, and dependency files are version-controlled. Any run can be reproduced by checking out the commit that trained it (recorded in MLflow `mlflow.source.git.commit` tag). |
| GitHub Actions audit trail | `.github/workflows/` | Every build, deploy, retrain, promote, and rollback action is logged in GitHub Actions history with actor, timestamp, and inputs. |
| CI/CD pipeline definitions as code | `.github/workflows/` | All automation is in version-controlled YAML — no manual shell scripts on the server. |

---

## 4. Privacy

**Requirement:** User data must be minimised, protected, and not leaked.

### Mechanisms

| Mechanism | Location | How it works |
|-----------|----------|--------------|
| Input text is never stored in the classifier response or logs | `serving/classifier/app.py` `log_classifier_audit()` | The audit log records `message_id`, predicted tone, confidence, and latency — **not** the original message text. |
| Feedback records contain only signal, not content | `data/online/online_features.py` | Online feature records store user-action labels (`thumbs_up`, `selected`, etc.) keyed by `message_id`; original message text is not persisted. |
| MinIO credentials in Kubernetes Secrets, never in manifests | `k8s/platform/minio/deployment.yaml`, `SECURITY.md` | `minio-root` Secret is created out-of-band by the Ansible `deploy_platform` playbook and is replicated across namespaces at deploy time. No credentials appear in tracked YAML. |
| `.gitignore` blocks secrets | `.gitignore`, `SECURITY.md` | `terraform.tfvars`, `values-secret.yaml`, `inventory.ini`, kubeconfigs, and `*.pem` files are ignored. |
| Namespace isolation | `k8s/base/namespaces.yaml` | `ml-data`, `ml-training`, `ml-serving`, and `ml-platform` are separate Kubernetes namespaces with no cross-namespace service access except via explicit Service DNS names. |

---

## 5. Accountability

**Requirement:** It must be possible to trace any system output back to the model version, training run, and human decision that produced it.

### Mechanisms

| Mechanism | Location | How it works |
|-----------|----------|--------------|
| Audit log per inference | `serving/classifier/audit_log.py`, `serving/generator/audit_log.py` | Every prediction is written to a structured audit entry with `message_id`, `predicted_tone`, `confidence`, `backend`, and `inference_latency_ms`. Logs are streamed to stdout and collected by the cluster log aggregator. |
| Deployment tier tag in response | `ClassifierResponse.backend` and `DEPLOYMENT_TIER` env var | Every serving pod reports which tier (staging / canary / production) handled the request, enabling post-hoc blame analysis. |
| MLflow model version lineage | `register_and_alias_latest.py` | Each registered model version includes tags `registered_from_run_id` and `quality_gate_status`, linking an alias to the exact training run. |
| Rollback workflow | `.github/workflows/rollback-inference.yml` | A one-click `kubectl rollout undo` for any tier is available without SSH. Rollbacks are also logged in GitHub Actions. |
| Retrain trigger record | `data/retrain_trigger/retrain_trigger.py` | Every automated retrain writes a JSON trigger record to MinIO (`triggers/YYYY-MM-DD/trigger_<ts>.json`) capturing the conditions that fired, the metric values, and whether it was eventually processed. |

---

## 6. Robustness

**Requirement:** The system must handle degraded conditions gracefully without silent failure.

### Mechanisms

| Mechanism | Location | How it works |
|-----------|----------|--------------|
| DUMMY_MODE fallback | `serving/classifier/model.py`, `serving/generator/model.py` | Staging always runs with `DUMMY_MODE=true`, guaranteeing a functional endpoint even before a real model is available. Canary and prod use real models; if the model load fails after 5 retries, the pod is marked unready (not serving traffic). |
| Retry with exponential backoff on model load | `serving/classifier/app.py` `_load_classifier_in_thread()` | Up to 5 attempts with 30 s → 60 s → 120 s backoff. Handles transient MLflow/S3 connectivity issues on startup without requiring a pod restart. |
| Readiness / liveness probes | `k8s/inference/base/classifier-pytorch.yaml`, canary + prod patches | `/ready` returns 503 until the model is fully loaded. `/health` answers immediately. Kubernetes removes unready pods from the Service endpoints automatically. |
| HPA (Horizontal Pod Autoscaler) | `k8s/inference/base/hpa-classifier.yaml`, `hpa-generator.yaml` | Scales classifier to 1–4 replicas at 70% CPU, generator similarly, preserving SLOs under traffic spikes. |
| Prometheus alerting | `k8s/platform/observability/configmap-prometheus.yaml` | Fires `ServingClassifierHighErrorRatio` (error rate > 5% for 10 min) and `ServingClassifierLatencyP95High` (p95 > 150 ms for 15 min) to Alertmanager, which can page the on-call engineer. |
| Automated rollback on quality gate failure | `.github/workflows/retrain-on-trigger.yml` | If post-training quality gates fail, the `@prod` alias is NOT updated; production continues serving the previous model. Canary keeps the new model for further investigation. |
| MinIO bucket init health check | `k8s/data/minio-bucket-init-job.yaml` | The bucket init job polls `GET /minio/health/ready` for up to 2 minutes before running `mc` commands, preventing hangs when MinIO is still starting. |
| Input sanitisation | `serving/classifier/app.py` `/predict` | Strips whitespace; rejects blank text with HTTP 422 before reaching the model, preventing tokeniser edge cases. Max 2 000 characters enforced by Pydantic. |

---

## Summary checklist

| Principle | Gate/Runtime | Monitoring | Audit trail |
|-----------|-------------|------------|-------------|
| Fairness | Per-class F1 gate in register-bundle | Grafana feedback approval | MLflow per-class metrics per run |
| Explainability | Probabilities + confidence in API | — | Audit log per prediction |
| Transparency | Quality gates in CI, MLflow registry | MLflow UI, Grafana | GitHub Actions, MLflow run history |
| Privacy | No text in audit log, Secrets-only creds | — | `.gitignore`, SECURITY.md |
| Accountability | Audit log, tier tag, rollback workflow | — | Trigger records, GitHub Actions |
| Robustness | DUMMY_MODE, retry, HPA, probes | Prometheus alerts | Rollback history, liveness logs |
