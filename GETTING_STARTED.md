# Getting Started

This guide describes the recommended bring-up and rerun flow for the current repository state.

## Prerequisites

- Chameleon leases for one control-plane node and one worker node
- OpenStack application credentials
- A floating IP
- Terraform installed on Windows or Linux
- WSL or Linux shell with Ansible in `infra/ansible/.venv`
- SSH key available to both Terraform and Ansible

## Local files you need

- `infra/terraform/openstack/terraform.tfvars`
- `infra/ansible/inventory.ini`

Do not commit any of those files.

## Recommended commands

For a clean bring-up from the repo root:

```bash
./infra/run-terraform --action apply --write-inventory
./infra/run-ansible
```

For a normal rerun on an existing live cluster:

```bash
./infra/run-ansible --skip-pvc-migration
```

Use the playbook-by-playbook flow below when you need to debug or run individual stages.

## Bring-up order

### 1. Provision infrastructure

From [infra/terraform/openstack](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\terraform\openstack):

```bash
terraform init
terraform plan
terraform apply
terraform output -raw ansible_inventory_ini
```

Copy the generated inventory into [infra/ansible/inventory.ini](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\inventory.ini) and add your SSH key path if needed.

### 2. Install k3s

From [infra/ansible](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible):

```bash
source .venv/bin/activate
ansible-playbook -i inventory.ini playbooks/k3s_install.yml
```

This installs k3s server on the control-plane and joins the worker through the control-plane jump host.

### 3. Install Sealed Secrets and bootstrap runtime secrets

```bash
ansible-playbook -i inventory.ini playbooks/deploy_sealed_secrets.yml
```

This installs the Sealed Secrets controller and bootstraps the required runtime secrets.

By default it will:

- create `minio-root` in the runtime namespaces
- create `grafana-admin` in `monitoring`
- generate a self-signed `chameleon-nip-tls` certificate for the current `*.nip.io` hosts
- create the TLS secret in `zulip`, `ml-platform`, `monitoring`, and `ml-serving`

Optional:

- if you set `CHAMELEON_TLS_CERT_FILE` and `CHAMELEON_TLS_KEY_FILE` in the local shell,
  those files will be used instead of generating a self-signed certificate
- if you set `APPLY_STATIC_SEALED_SECRETS=true`, the playbook will also apply the static
  manifests from [k8s/secrets](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\secrets)

### 4. Prepare block storage for persistent state

If you attached a Chameleon block volume for persistent service data, prepare it on the
control-plane before deploying workloads:

```bash
ansible-playbook -i inventory.ini playbooks/prepare_block_storage.yml
```

This playbook:

- persists the `/mnt/block` mount in `/etc/fstab`
- creates service directories under `/mnt/block`
- labels the control-plane node as the block-backed storage node
- updates k3s `local-path` so new claims scheduled on the control-plane use the block volume

Important:

- the playbook expects the attached partition to be `/dev/vdb1`
- existing PVCs are not migrated automatically; only newly provisioned or recreated claims will move

If the platform services already exist and you want to move their current PVC contents to
the block-backed path, run the migration after the next platform apply:

```bash
ansible-playbook -i inventory.ini playbooks/migrate_platform_pvcs_to_block.yml
```

This migrates:

- MinIO
- MLflow
- Prometheus
- Grafana

The migration is serialized and service-by-service: scale down, stream backup, recreate
the PVC, restore, then scale back up.

This is a one-time disruptive migration step. Do not include it in normal reruns of the
cluster after the data has already been moved.

### 5. Deploy the shared platform

```bash
ansible-playbook -i inventory.ini playbooks/deploy_platform.yml
```

This deploys:

- namespaces
- MLflow
- MinIO
- Prometheus
- Grafana
- Alertmanager

The playbook also rewrites `*.nip.io` hostnames in the synced VM manifests to the current floating IP.

### 6. Deploy automated backups to Chameleon object storage

Export the object-storage values in the local shell that will run Ansible:

```bash
export CHAMELEON_OBJECTSTORE_BUCKET=<your-object-store-container>
export CHAMELEON_OBJECTSTORE_ACCESS_KEY=<your-ec2-access-key>
export CHAMELEON_OBJECTSTORE_SECRET_KEY=<your-ec2-secret-key>
export CHAMELEON_OBJECTSTORE_ENDPOINT=https://chi.tacc.chameleoncloud.org:7480
export CHAMELEON_OBJECTSTORE_PREFIX=proj15-backups
```

Then deploy the backup CronJobs:

```bash
ansible-playbook -i inventory.ini playbooks/deploy_backups.yml
```

This creates `chameleon-objectstore-backup` in `zulip`, `ml-platform`, and `monitoring`,
then applies scheduled backups for:

- Zulip PostgreSQL
- Zulip app data
- MLflow SQLite metadata
- MinIO bucket contents
- Grafana SQLite metadata
- Prometheus TSDB snapshots

### 7. Deploy Zulip

If `/home/cc/values-secret.yaml` does not already exist, the playbook will generate it
automatically using:

- environment variables when provided
- otherwise sensible defaults plus random passwords/secrets

Useful optional environment variables:

- `ZULIP_ADMIN_EMAIL`
- `ZULIP_EMAIL_HOST`
- `ZULIP_EMAIL_HOST_USER`
- `ZULIP_EMAIL_PORT`
- `ZULIP_EMAIL_USE_TLS`
- `ZULIP_EMAIL_PASSWORD`
- `ZULIP_SECRET_KEY`
- `ZULIP_MEMCACHED_PASSWORD`
- `ZULIP_RABBITMQ_PASSWORD`
- `ZULIP_RABBITMQ_ERLANG_COOKIE`
- `ZULIP_REDIS_PASSWORD`
- `ZULIP_POSTGRES_SUPERUSER_PASSWORD`
- `ZULIP_POSTGRES_PASSWORD`

```bash
ansible-playbook -i inventory.ini playbooks/deploy_zulip.yml \
  -e zulip_chart_dir=/home/cc/docker-zulip/helm/zulip \
  -e project_id_suffix=proj15 \
  -e zulip_values_file=/opt/mlops_project/k8s/zulip/values-chameleon.yaml \
  -e zulip_secret_values_file=/home/cc/values-secret.yaml
```

### 8. Deploy ML workloads

```bash
ansible-playbook -i inventory.ini playbooks/deploy_ml_workloads.yml
```

The playbook now:

- syncs the current `k8s/` tree to the VM
- rewrites public hostnames to the active floating IP
- verifies `minio-root` is present in workload namespaces
- runs the data jobs and waits for them
- applies inference and bridge manifests and waits for rollouts
- runs training jobs and waits for them
- runs the registry job and waits for completion

## Verification checklist

On the control-plane VM:

```bash
kubectl get nodes
kubectl get pods,svc,ingress -n ml-platform
kubectl get pods,svc,ingress -n monitoring
kubectl get pods,svc,ingress -n zulip
kubectl get cronjobs,jobs -n ml-platform
kubectl get cronjobs,jobs -n monitoring
kubectl get cronjobs,jobs -n zulip
kubectl get pods,svc -n ml-data
kubectl get pods,svc -n ml-serving
kubectl get jobs,pods -n ml-training
```

Expected high-level state:

- both nodes `Ready`
- platform pods `Running`
- Zulip pods `Running`
- data jobs `Complete`
- training jobs `Complete`
- `register-and-alias-latest` `Complete`
- classifier and generator deployments ready in `staging`, `canary`, and `prod`

## Browser checks

Verify:

- `https://zulip.<floating-ip>.nip.io`
- `https://mlflow.<floating-ip>.nip.io`
- `https://minio-console.<floating-ip>.nip.io`
- `https://grafana.<floating-ip>.nip.io`

Then log into Zulip and test `Tone suggestions`.

Grafana also includes a `Data Monitoring and Quality` dashboard that shows:

- bridge feedback counters
- feature-log activity
- data and training job health
- data and training pod restarts

Some bridge-related panels require at least one successful Prometheus scrape interval after
live traffic has hit the bridge metrics endpoint.

## If something fails

- Platform issues: see [infra/ansible/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\README.md)
- Kubernetes manifest ownership and layout: see [k8s/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\README.md)
- Serving and integration checks: see [serving/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\serving\README.md)
