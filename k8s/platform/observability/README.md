# Prometheus, Grafana, and Alertmanager

Namespace `monitoring` hosts the shared observability stack:

- `prometheus` stores scraped metrics on the `prometheus-data` PVC
- `grafana` serves dashboards from the `grafana-data` PVC
- `alertmanager` receives alerts from Prometheus
- `kube-state-metrics` exports Kubernetes object state
- `node-exporter` runs on every node and exports host metrics

## Access

- Grafana: `https://grafana.<floating-ip>.nip.io/`
- Prometheus: `https://prometheus.<floating-ip>.nip.io/`

The Grafana admin password lives in the `grafana-admin` Secret:

```bash
kubectl get secret grafana-admin -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d && echo
```

## What Is Monitored

Prometheus scrapes:

- annotated inference and integration pods in `ml-serving`
- `kube-state-metrics` for deployment, pod, and node state
- `node-exporter` for host CPU and memory usage

This supports both platform and serving views from a single Prometheus instance.

## Dashboards

Grafana provisions the `MLOps` folder automatically. The current dashboards are:

- `ML Serving Health`
  - request rate
  - p95 latency
  - error rate
  - feedback counters for the tone assistant services
- `Infrastructure Health`
  - node CPU and memory pressure
  - deployment replica availability
  - pod restart behavior
  - Kubernetes node readiness

If dashboards are changed, re-apply:

```bash
kubectl apply -k k8s/platform/observability/
```

## Alerts

Prometheus evaluates alert rules from `configmap-prometheus.yaml` and forwards them to Alertmanager.

Current platform alerts:

- `Watchdog`
- `PlatformNodeNotReady`
- `PlatformDeploymentUnavailableReplicas`
- `PlatformPodRestartsHigh`
- `PlatformNodeCpuHigh`
- `PlatformNodeMemoryHigh`

Current serving alerts:

- `ServingClassifierHighErrorRatio`
- `ServingClassifierLatencyP95High`
- `ServingGeneratorHighErrorRatio`
- `ServingGeneratorLatencyP95High`
- `ServingGeneratorFallbackRatioHigh`
- `ServingGeneratorFeedbackApprovalLow`
- `ServingGeneratorQueueWaitP95High`

Alertmanager supports SMTP email delivery through deployment-time variable injection. Set these before running `deploy_platform.yml`:

- `ALERT_EMAIL_TO`
- `ALERT_EMAIL_FROM`
- `ALERT_EMAIL_SMARTHOST`
- `ALERT_EMAIL_AUTH_USERNAME`
- `ALERT_EMAIL_AUTH_PASSWORD`

The repo keeps placeholders only; `deploy_platform.yml` patches the copied VM manifest before `kubectl apply`, so credentials do not need to be stored in Git.

## Autoscaling

HorizontalPodAutoscalers are configured for:

- `classifier-pytorch-staging`
- `classifier-pytorch-canary`
- `classifier-pytorch-prod`
- `tone-generator-staging`
- `tone-generator-canary`
- `tone-generator-prod`

The classifier HPAs target `70%` CPU utilization and the generator HPAs target `65%`.

Validated live on the current cluster:

- `classifier-pytorch-staging` scaled from `1` replica to `4` replicas under sustained request load
- after the load completed and the downscale stabilization window elapsed, it returned from `4` replicas to `1`

## Rollout Note

Prometheus uses a single PVC-backed TSDB, so its Deployment uses a `Recreate` strategy. This prevents overlapping pods from competing for the same storage lock during rollouts.

## Evidence

See [EVIDENCE.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\platform\observability\EVIDENCE.md) for the live validation checklist and the observed monitoring, alerting, and autoscaling results captured from the current cluster.
