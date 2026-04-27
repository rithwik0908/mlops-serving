# Training Deployment Notes

This training code is intended to run either in containers locally or through the Kubernetes jobs in `k8s/training/`.

## Environment

- `MLFLOW_TRACKING_URI`
- `MLFLOW_S3_ENDPOINT_URL`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_FORCE_PATH_STYLE=true`

## Build examples

```bash
docker build -f training/Dockerfile -t tone-train ./training
docker build -f training/Dockerfile.llm -t llm-train ./training
```

## Cluster path

The normal cluster path is:

1. data prepared in `ml-data`
2. classifier and generator training jobs in `ml-training`
3. registry job assigns aliases
4. serving loads models by alias

For current operational usage, prefer the Kubernetes path documented in [k8s/training/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\training\README.md).
