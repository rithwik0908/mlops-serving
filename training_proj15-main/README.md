# Training Code

This directory contains the model training code used by the cluster training jobs.

## Main components

- `training/train.py`: classifier training
- `training/train_llm.py`: generator training
- `training/configs/`: config-driven training settings
- `training/Dockerfile`: classifier training image
- `training/Dockerfile.llm`: generator training image

## Runtime flow

- training reads prepared data from MinIO
- runs are logged to MLflow
- trained models are registered and aliased for serving

## Local build examples

```bash
docker build -f training/Dockerfile -t tone-train ./training
docker build -f training/Dockerfile.llm -t llm-train ./training
```

## Related docs

- [training/DEPLOYMENT.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\training_proj15-main\training\DEPLOYMENT.md)
- [../k8s/training/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\training\README.md)
