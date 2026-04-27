# Demo Script — Serving Track
**Role:** Serving — Rithwik Amajala | **Time: ~6 min**

---

## Before the demo (5 min before)

```bash
# Open 2 browser tabs:
# 1. https://grafana.129.114.27.192.nip.io/  (admin / grafana-password)
# 2. https://prometheus.129.114.27.192.nip.io/

# SSH into VM
ssh -i ~/.ssh/id_rsa_chameleon cc@129.114.25.7
cd Multi-Tone-Communication-Assistant-for-Zulip---MLOps/serving

# Confirm containers are healthy
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Quick sanity check
bash scripts/smoke_predict_generate.sh http://127.0.0.1:8001 http://127.0.0.1:8010
# Expected: OK: smoke checks passed
```

---

## Part 1 — What we built (1 min)

> "My role is **serving**. I own the two microservices that power the tone assistant — a **classifier** and a **generator**. When a Zulip user sends a message, the classifier reads it and predicts whether the tone is formal, friendly, or neutral. The generator then rewrites the same message in all three tones so the user can pick the one that fits best."

> "Both services run as FastAPI apps — containerised with Docker locally and deployed as Kubernetes pods in the cluster. There's also a Zulip bridge that connects them to the actual bot. My job is to make sure these services are fast, reliable, observable, and keep improving over time from real user feedback."

```
Zulip message → /zulip/webhook (bridge)
    → generator /generate
        → classifier /predict  (DistilBERT, 3-class tone)
    ← 3 tone variants back to Zulip
```

---

## Part 2 — Walk through the API design (1 min)

> "Rather than running a live call right now, let me walk you through what the APIs actually look like, because the design is what matters here."

**Show `serving/classifier/app.py` or just talk through it:**

> "The classifier exposes a `POST /predict` endpoint. You send it a message with a `message_id`, the text, and the message type — stream or direct message. It runs the text through a DistilBERT model and returns the `predicted_tone`, the full probability distribution across formal, friendly, and neutral, and the `latency_ms`. The `message_id` is just a UUID the caller generates — but it's critical because every downstream piece, the audit log, the feedback record, the training row — they all join on that same ID."

> "The generator wraps the classifier. Same input shape. Internally it calls `/predict` first to understand the current tone, then generates three rewrites — one per tone. The response has a `variants` object with `formal`, `friendly`, and `neutral` fields. There's also an `offensive_content_flagged` boolean — if the input contains profanity, the output is suppressed entirely and the flag is set."

**Show `serving/classifier/audit_log.py`:**

> "Every request writes a structured audit line to stdout. We're treating container logs as our audit trail — `message_id`, predicted tone, confidence score, latency. Deliberately no raw message text, to keep it low-PII. This is what the data team's batch pipeline reads to build training rows — it joins these audit lines with the user's feedback signal by `message_id`."

---

## Part 3 — Prometheus + Grafana (2 min)

### Prometheus first
**Open https://prometheus.129.114.27.192.nip.io/ → Status → Targets**

> "First, Prometheus. You can see it's scraping the pods in the `ml-serving` namespace via Kubernetes service discovery — no static IPs, no manual config. Any pod with the `prometheus.io/scrape: true` annotation gets picked up automatically. The classifier and generator both have that annotation."

**Go to Graph tab, paste this query:**
```
histogram_quantile(0.95, sum(rate(classifier_latency_seconds_bucket[5m])) by (le))
```
> "This is the p95 latency query for the classifier — the same one that's in our alert rules. If this value stays above 150ms for 15 minutes, an alert fires. The dashboards in Grafana are just running queries like this behind the scenes."

---

### Grafana
**Open https://grafana.129.114.27.192.nip.io/ → Dashboards → MLOps → "ML Serving — Classifier, Generator & Feedback"**

> "This is the serving dashboard. I set it up so it provisions automatically from the repo — the JSON is checked in under `k8s/platform/observability/dashboards/`, and a ConfigMap mounts it into Grafana at startup. So if I update the dashboard and push, it shows up here without anyone having to click Import."

> "There are three rows. The first is the classifier — RPS, p95 and p50 latency side by side, and an error ratio panel. The colour thresholds are set so green means below 1% errors, it turns red above 5%. Second row is the same layout for the generator."

> "The third row is the interesting one from an MLOps perspective — it tracks user feedback signals coming through the Zulip bridge. There's an approval rate panel, a breakdown of feedback signal types, and a chart of thumbs-down counts by tone. So if 'formal' rewrites keep getting rejected, that shows up here as a signal before it becomes a big enough problem to trigger a retrain."

> *(If panels show no data)* "The panels are wired up — they just need live traffic flowing through the Kubernetes services to show numbers. The queries and thresholds are all in place."

---

## Part 4 — Feedback → retraining loop (1 min)

```bash
curl -sS -X POST http://127.0.0.1:8010/feedback \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","tone_shown":"formal","user_action":"thumbs_up"}'
```

> "This is what the full feedback loop looks like. The Zulip bridge exposes a `/feedback` endpoint. When a user taps thumbs-up or thumbs-down on a rewrite, this call is made. It writes a JSON record into MinIO — the same MinIO that stores our models and training artifacts. The record includes the `message_id`, the tone that was shown, and what the user did."

> "Every night the batch pipeline reads all the feedback records from that day, joins them by `message_id` back to the classifier's audit log, and builds a labeled dataset. That feeds the retrain trigger, which checks three things:"

```
DATA_TRIGGER:    >= 500 new labeled examples?      → model hasn't seen enough new data
QUALITY_TRIGGER: approval rate < 70%?              → users are rejecting too many responses
DRIFT_TRIGGER:   production F1 < 0.60?             → model quality confirmed degrading

→ if any fires: full retrain pipeline runs in CI
→ new models registered in MLflow with new experiment run
→ promotion gate: must beat current production F1 on holdout + last 30d feedback slice
→ on pass: model gets the 'production' alias → deploy workflow picks it up
```

> "The key design decision here is that nothing is hardcoded. The thresholds — 500 rows, 70%, 0.60 — are all environment variables on the Kubernetes CronJob. You can tune them without rebuilding any image. And the promotion gate is strict: a new model has to beat the current production model on both the fixed holdout set and on recent real-world feedback. If latency p95 regresses by more than 20%, the promotion is blocked too."

---

## Wrap-up (15 sec)

> "So to summarize what serving owns end-to-end: two FastAPI microservices — classifier and generator — running on Kubernetes, with Prometheus metrics and a live Grafana dashboard covering latency, throughput, errors, and now user feedback. Structured audit logs for every model output. A `/feedback` endpoint that feeds directly into our training data. And automated data, quality, and drift triggers that close the loop from production usage back to model improvement — all without anyone having to manually SSH in or run a training job by hand. That's the full MLOps lifecycle on the serving side."

---

## Q&A cheat sheet

| Question | Answer |
|----------|--------|
| Why `DUMMY_MODE=true` in K8s? | Safe default — flip env var + redeploy once real MLflow artifacts are aliased `prod` |
| How does Prometheus find the pods? | `prometheus.io/scrape: true` annotation + `kubernetes_sd_configs` in Prometheus ConfigMap |
| Promotion gate? | New model beats baseline F1 on holdout + last 30d feedback; p95 regression >20% → rollback |
| Retrain triggers too often? | Thresholds are env vars on the CronJob — change without rebuild |

---

## Emergency fallbacks

| Problem | Fix |
|---------|-----|
| Containers down | `docker start classifier-pytorch generator` |
| Grafana blank | `curl http://127.0.0.1:8001/metrics` — show raw Prometheus output |
| Generator slow | Demo classifier only — same story |
| SSH broken | Show audit log JSON / Grafana screenshots |
