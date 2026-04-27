# Observability and Release Notes

This document describes how to observe and validate the serving layer.

## Metrics exposed by the services

- classifier: `GET /metrics`
- generator: `GET /metrics`
- bridge: `GET /metrics`

Examples:

- `classifier_requests_total`
- `classifier_latency_seconds_*`
- `generator_requests_total`
- `generator_latency_seconds_*`
- `generator_variant_source_total`
- `generator_fallback_reason_total`
- `generator_request_path_total`
- `generator_queue_wait_seconds_*`
- `generator_inflight_requests`
- bridge feedback counters

## Where to view them

Use the shared platform stack deployed in `monitoring`:

- Grafana: `https://grafana.<floating-ip>.nip.io`
- Prometheus: `https://prometheus.<floating-ip>.nip.io`

Replace `<floating-ip>` with the current control-plane floating IP.

## Recommended checks after deploy

1. `kubectl get deploy,pods -n ml-serving`
2. `kubectl rollout status` for classifier, generator, and bridge
3. run the smoke script
4. trigger a real Zulip tone suggestion

## Release gate suggestions

- classifier and generator rollouts succeed
- no restart loop on serving pods
- smoke tests return valid JSON
- Zulip bridge returns suggestions
- generator latency remains acceptable for demo use
- generator fallback ratio stays low enough that the model, not rescue logic, is doing most of the work
- recent feedback approval is healthy enough to trust promotion decisions
- queue wait remains low under canary traffic so the generator is not already saturating

## Rollback trigger examples

- serving deployment fails readiness
- bridge starts timing out consistently
- generator outputs collapse into identical or obviously degenerate rewrites
- model alias registration fails and serving cannot load artifacts
- fallback ratio spikes after a promotion
- thumbs-up or selected feedback drops materially while traffic volume remains meaningful
- queue wait climbs even when classifier latency stays healthy
