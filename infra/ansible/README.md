# Ansible

These playbooks install k3s and deploy the cluster workloads from the control-plane node.

If you want the full initial bring-up in one command, use
[infra/run-ansible](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\run-ansible).

## Playbooks

- `playbooks/k3s_install.yml`: installs k3s server on `control_plane` and joins `workers`
- `playbooks/deploy_sealed_secrets.yml`: installs the Sealed Secrets controller and bootstraps runtime secrets and TLS
- `playbooks/deploy_platform.yml`: deploys MLflow, MinIO, Prometheus, Grafana, Alertmanager
- `playbooks/deploy_backups.yml`: deploys scheduled backups from PVC-backed services to Chameleon object storage
- `playbooks/deploy_zulip.yml`: installs or upgrades Zulip through Helm
- `playbooks/deploy_ml_workloads.yml`: deploys data, training, inference, and bridge workloads

## Inventory

Use the generated Terraform inventory shape:

```ini
[control_plane]
control-plane ansible_host=<floating_ip> private_ip=<control_plane_private_ip>

[workers]
worker-1 ansible_host=<worker_private_ip> private_ip=<worker_private_ip> ansible_ssh_common_args='-o ProxyJump=cc@<floating_ip>'

[chameleon:children]
control_plane
workers

[chameleon:vars]
ansible_user=cc
ansible_ssh_private_key_file=~/.ssh/YOUR_KEY
ansible_python_interpreter=/usr/bin/python3.12
```

## Bring-up order

```bash
source .venv/bin/activate
ansible-playbook -i inventory.ini playbooks/k3s_install.yml
ansible-playbook -i inventory.ini playbooks/deploy_sealed_secrets.yml
ansible-playbook -i inventory.ini playbooks/prepare_block_storage.yml
ansible-playbook -i inventory.ini playbooks/deploy_platform.yml
ansible-playbook -i inventory.ini playbooks/migrate_platform_pvcs_to_block.yml
ansible-playbook -i inventory.ini playbooks/deploy_backups.yml
ansible-playbook -i inventory.ini playbooks/deploy_zulip.yml \
  -e zulip_chart_dir=/home/cc/docker-zulip/helm/zulip \
  -e project_id_suffix=proj15 \
  -e zulip_values_file=/opt/mlops_project/k8s/zulip/values-chameleon.yaml \
  -e zulip_secret_values_file=/home/cc/values-secret.yaml
ansible-playbook -i inventory.ini playbooks/deploy_ml_workloads.yml
```

Equivalent single-command wrapper:

```bash
./infra/run-ansible
```

For normal reruns after the initial storage migration, use:

```bash
./infra/run-ansible --skip-pvc-migration
```

## Notes

- The playbooks only run cluster-admin actions on `control_plane`.
- `deploy_sealed_secrets.yml` installs the controller, creates `minio-root`, `grafana-admin`, and `chameleon-nip-tls`, and can optionally apply static SealedSecret manifests when `APPLY_STATIC_SEALED_SECRETS=true`.
- If `CHAMELEON_TLS_CERT_FILE` and `CHAMELEON_TLS_KEY_FILE` are not set in the local shell, `deploy_sealed_secrets.yml` generates a self-signed `*.nip.io` certificate for the current floating IP.
- `prepare_block_storage.yml` assumes the Chameleon block volume is already attached,
  partitioned as `/dev/vdb1`, and mounted or mountable at `/mnt/block`.
- `prepare_block_storage.yml` is non-destructive. It makes future `local-path` claims
  use `/mnt/block/local-path-provisioner` on the control-plane, but it does not migrate
  already-bound PVCs off the root disk.
- `migrate_platform_pvcs_to_block.yml` performs a stop-copy-recreate-restore migration
  for MinIO, MLflow, Prometheus, and Grafana PVCs. Run it only after
  `prepare_block_storage.yml` and a fresh `deploy_platform.yml`, and treat it as a one-time
  disruptive migration or explicit recovery step rather than a normal rerun stage.
- `deploy_backups.yml` expects these environment variables in the local shell that
  runs Ansible:
  - `CHAMELEON_OBJECTSTORE_BUCKET`
  - `CHAMELEON_OBJECTSTORE_ACCESS_KEY`
  - `CHAMELEON_OBJECTSTORE_SECRET_KEY`
  - optional `CHAMELEON_OBJECTSTORE_ENDPOINT`
  - optional `CHAMELEON_OBJECTSTORE_PREFIX`
  - optional `CHAMELEON_OBJECTSTORE_REGION`
- `deploy_zulip.yml` auto-generates `zulip_secret_values_file` when it is missing. You can override its values with environment variables such as:
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
- `deploy_platform.yml` and `deploy_ml_workloads.yml` rewrite floating-IP-based hostnames in the synced VM manifests.
- `deploy_ml_workloads.yml` now waits for:
  - data jobs
  - inference deployment rollouts
  - Zulip bridge rollout
  - training jobs
  - `register-and-alias-latest`

## Inputs still required outside git

- `inventory.ini`
- `terraform.tfvars`
- optional custom TLS cert/key
- optional SMTP and Zulip credential values
