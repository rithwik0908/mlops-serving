# Serving

The serving layer exposes the classifier and tone generator services used by Zulip.

## Main components

- `classifier`: predicts the current tone
- `generator`: produces `formal`, `friendly`, and `neutral` suggestions
- `zulip-bridge`: adapts Zulip requests to the generator API

## Local development

```bash
cd serving
docker compose build
docker compose up -d classifier-pytorch generator
```

## Cluster deployment

Cluster deployment is managed by:

- [k8s/inference/](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\inference)
- [k8s/integration/](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\integration)
- [infra/ansible/playbooks/deploy_ml_workloads.yml](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\playbooks\deploy_ml_workloads.yml)

## Useful docs

- [INTEGRATION_FOR_ZULIP.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\serving\INTEGRATION_FOR_ZULIP.md)
- [OBSERVABILITY_AND_RELEASE.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\serving\OBSERVABILITY_AND_RELEASE.md)
- [SERVING_OPTIONS.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\serving\SERVING_OPTIONS.md)

## Quick smoke

```bash
bash serving/scripts/smoke_predict_generate.sh http://127.0.0.1:8001 http://127.0.0.1:8010
```

## Current operational note

The generator includes repo-side fallback cleanup logic for weak rewrites. In the cluster, that logic is mounted through the inference ConfigMap path so the repo and running behavior stay aligned.
