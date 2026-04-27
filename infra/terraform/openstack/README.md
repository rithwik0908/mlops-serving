# OpenStack Terraform

This module provisions the two-node Chameleon environment used by the project.

## What it creates

- one control-plane instance
- one worker instance
- one floating IP attached to the control-plane
- optional persistent block volume attached to the control-plane
- managed security group rules for SSH, HTTP, HTTPS, and internal k3s traffic
- outputs that generate the Ansible inventory

## Required local inputs

Create `terraform.tfvars` from `terraform.tfvars.example` and fill in:

- OpenStack auth values or use `TF_VAR_*` environment variables
- `network_id`
- `key_pair`
- lease or reservation ids
- image and flavor selections if different from defaults
- block volume settings if you want the control-plane data disk reattached automatically

## Apply

```bash
terraform init
terraform plan
terraform apply
```

Equivalent single-command wrapper from the repo root:

```bash
./infra/run-terraform --action apply --write-inventory
```

## Useful outputs

```bash
terraform output
terraform output -raw ansible_inventory_ini
```

The generated inventory includes:

- public `ansible_host` for the control-plane
- private worker address
- jump-host SSH path through the control-plane

## Persistent block volume

If you want live PVC data to survive VM recreation, the safest pattern is:

1. create the block volume once
2. keep the volume
3. reattach the same volume on later `terraform apply` runs

Use these `terraform.tfvars` settings:

```hcl
attach_block_volume      = true
existing_block_volume_id = "your-existing-volume-uuid"
```

Terraform can also create the first volume for you:

```hcl
attach_block_volume      = true
create_block_volume      = true
block_volume_name        = "block-data-proj15"
block_volume_size_gib    = 150
block_volume_type        = "ceph-ssd"
```

Important:

- Terraform can attach the volume, but the OS still needs it mounted.
- The repo's Ansible flow handles the mount and `/etc/fstab` setup in [prepare_block_storage.yml](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\playbooks\prepare_block_storage.yml).
- If Terraform creates the volume, it is protected with `prevent_destroy` so you do not accidentally delete your live data during a normal `terraform destroy`.

## Notes

- The worker intentionally has no floating IP.
- The control-plane floating IP is the public entry point for ingress and SSH.
- Existing user-managed security groups can still be attached; Terraform also adds the project-managed security group used by the cluster.
