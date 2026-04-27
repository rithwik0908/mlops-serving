# Inference

The inference stack lives in namespace `ml-serving` and is organized as a base plus tier overlays.

## Structure

| Path | Purpose |
|------|---------|
| `base/` | shared classifier and generator manifests |
| `overlays/staging/` | lower-risk staging tier |
| `overlays/canary/` | pre-production validation tier |
| `overlays/prod/` | production tier |
| `backends/` | optional alternate classifier backends |
| `ingress/` | optional browser-facing ingress |

## Important behavior

- `classifier-pytorch-*` deployments load models from MLflow aliases.
- `tone-generator-*` deployments call the matching classifier tier.
- The generator logic is mounted from `base/generator-model.py` through a ConfigMap so the running cluster can use the latest repo-side generator logic without waiting for a rebuilt image.

## Main service names

- `classifier-pytorch-staging`
- `classifier-pytorch-canary`
- `classifier-pytorch-prod`
- `tone-generator-staging`
- `tone-generator-canary`
- `tone-generator-prod`

## Apply

```bash
kubectl apply -k k8s/inference/
```

In normal operation this is handled by [deploy_ml_workloads.yml](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\playbooks\deploy_ml_workloads.yml).

## Dependencies

- `minio-root` secret replicated into `ml-serving`
- MLflow reachable at `mlflow.ml-platform.svc.cluster.local`
- MinIO reachable at `minio.ml-platform.svc.cluster.local`
- model aliases registered in MLflow

## Verification

```bash
kubectl get deploy,pods,svc -n ml-serving
kubectl rollout status deployment/classifier-pytorch-prod -n ml-serving
kubectl rollout status deployment/tone-generator-prod -n ml-serving
```
