# Automated Backups to Chameleon Object Storage

This bundle schedules object-storage backups for the stateful services that now live on the
block-backed control-plane node.

## What gets backed up

- `zulip` namespace
  - logical PostgreSQL dump from `zulip-proj15-postgresql`
  - tarball of the Zulip application PVC `zulip-proj15-data`
- `ml-platform` namespace
  - SQLite backup of `mlflow-data`
  - mirrored copy of the `zulip-rewriter` MinIO bucket
- `monitoring` namespace
  - SQLite backup of `grafana-data`
  - Prometheus TSDB snapshot tarball

## Required secret

Every backup namespace expects a Secret named `chameleon-objectstore-backup` with these keys:

- `endpoint`
- `bucket`
- `prefix`
- `access-key`
- `secret-key`
- `region`

The Ansible playbook [infra/ansible/playbooks/deploy_backups.yml](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\playbooks\deploy_backups.yml)
creates that Secret in `zulip`, `ml-platform`, and `monitoring`.

## Manual apply

```bash
kubectl apply -k k8s/platform/backups/zulip/
kubectl apply -k k8s/platform/backups/ml-platform/
kubectl apply -k k8s/platform/backups/monitoring/
```

## Manual trigger

```bash
kubectl create job --from=cronjob/zulip-postgres-backup -n zulip zulip-postgres-backup-manual
kubectl create job --from=cronjob/zulip-data-backup -n zulip zulip-data-backup-manual
kubectl create job --from=cronjob/mlflow-sqlite-backup -n ml-platform mlflow-sqlite-backup-manual
kubectl create job --from=cronjob/minio-bucket-mirror -n ml-platform minio-bucket-mirror-manual
kubectl create job --from=cronjob/grafana-sqlite-backup -n monitoring grafana-sqlite-backup-manual
kubectl create job --from=cronjob/prometheus-snapshot-backup -n monitoring prometheus-snapshot-backup-manual
```

## Verification

```bash
kubectl get cronjobs -n zulip
kubectl get cronjobs -n ml-platform
kubectl get cronjobs -n monitoring
kubectl get jobs -n zulip
kubectl get jobs -n ml-platform
kubectl get jobs -n monitoring
kubectl logs job/<job-name> -n <namespace>
```

Objects are written under:

- `s3://<bucket>/<prefix>/zulip/postgres/`
- `s3://<bucket>/<prefix>/zulip/data/`
- `s3://<bucket>/<prefix>/ml-platform/mlflow/`
- `s3://<bucket>/<prefix>/ml-platform/minio/`
- `s3://<bucket>/<prefix>/monitoring/grafana/`
- `s3://<bucket>/<prefix>/monitoring/prometheus/`
