# Observability Evidence

This note captures the live validation performed against the current Chameleon cluster for the DevOps/platform evaluation and monitoring requirement.

## Monitoring Stack

Validated live in namespace `monitoring`:

- `prometheus`
- `grafana`
- `alertmanager`
- `kube-state-metrics`
- `node-exporter` on both cluster nodes

Observed result:

- all monitoring pods reached `Running`
- Grafana dashboards provisioned successfully
- Prometheus target discovery showed `kube-state-metrics` and `node-exporter` as `up`

## Dashboards

Validated live in Grafana:

- `ML Serving Health`
- `Infrastructure Health`

Observed result:

- serving request-rate and latency panels populated from live traffic
- node CPU, memory, HPA, replica-availability, and restart panels populated from exported metrics
- healthy/no-event panels were hardened to return `0` instead of `No data`

## Alerting

Validated live through Prometheus and Alertmanager:

- Prometheus alert API returned the `Watchdog` alert
- Alertmanager alert API returned the same `Watchdog` alert in `active` state
- direct SMTP validation from the VM to `sa9876@nyu.edu` completed successfully using the same Gmail relay configuration wired into Alertmanager

Configured platform alerts:

- `Watchdog`
- `PlatformNodeNotReady`
- `PlatformDeploymentUnavailableReplicas`
- `PlatformPodRestartsHigh`
- `PlatformNodeCpuHigh`
- `PlatformNodeMemoryHigh`

Configured serving alerts:

- `ServingClassifierHighErrorRatio`
- `ServingClassifierLatencyP95High`
- `ServingGeneratorHighErrorRatio`
- `ServingGeneratorLatencyP95High`

## Autoscaling

Validated live on `classifier-pytorch-staging`:

- initial state: `1` replica
- under sustained request load: scaled to `4` replicas
- after load stopped and the downscale stabilization window elapsed: returned to `1` replica

Observed HPA values during the test:

- target CPU policy: `70%`
- peak observed CPU target ratio: `240%/70%`
- scale-up progression: `1 -> 3 -> 4`
- scale-down progression: `4 -> 2 -> 1`

## Operational Notes

- Prometheus uses a PVC-backed TSDB and therefore deploys with a `Recreate` strategy to avoid TSDB lock contention during rollouts.
- Alertmanager email delivery is configured through environment-driven deployment-time substitution so SMTP credentials do not need to be stored in Git.
