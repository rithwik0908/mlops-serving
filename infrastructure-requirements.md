# Infrastructure Requirements

This document summarizes the expected infrastructure profile for the current repository layout.

## Cluster shape

- 1 control-plane node
- 1 worker node
- both nodes are currently CPU-only
- public floating IP on the control-plane

## Platform storage

Expected persistent data:

- MLflow PVC
- MinIO PVC
- Prometheus PVC
- Grafana PVC
- Zulip PostgreSQL PVC
- Zulip application PVC

## Workload expectations

- platform services are moderate CPU and memory consumers
- data jobs are bursty and storage-heavy
- training jobs are the slowest part of the workflow
- serving runs continuously in `staging`, `canary`, and `prod`

## Monitoring and scaling

The current cluster includes a shared observability stack in the `monitoring` namespace:

- Prometheus on a persistent volume
- Grafana on a persistent volume
- Alertmanager
- kube-state-metrics
- node-exporter

This stack monitors:

- node readiness, CPU, and memory pressure
- deployment replica availability
- pod restart rates
- serving request rate, latency, and error rate

Serving autoscaling is enabled with HorizontalPodAutoscalers:

- classifier deployments target `70%` CPU
- generator deployments target `65%` CPU

Validated behavior on the live cluster:

- the staging classifier scaled from `1` replica to `4` replicas under load
- after traffic stopped, it scaled back down to `1`

## Important practical note

Even in the two-node layout, persistence is still based on `local-path`, so disk pressure and node-local storage placement still matter. A second node helps scheduling and headroom, but it does not turn the cluster into shared-storage infrastructure.

## Operational advice

- keep enough root disk space for images, logs, and PVC-backed workloads
- clean completed jobs and stale images if the node hits `DiskPressure`
- keep the control-plane reachable on ports `22`, `80`, and `443`
