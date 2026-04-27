# Infrastructure

Infrastructure is split into Terraform for cloud resources and Ansible for cluster and workload deployment.

## Layout

- [terraform/openstack/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\terraform\openstack\README.md): OpenStack resources and generated inventory
- [ansible/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\README.md): k3s bootstrap and workload playbooks
- [ONE_PLATFORM_AND_CLEANUP.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ONE_PLATFORM_AND_CLEANUP.md): operational cleanup notes for shared platform ownership

## Recommended order

1. Run [run-terraform](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\run-terraform)
2. Run [run-ansible](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\run-ansible)

## One-command entrypoints

Terraform bring-up plus inventory generation:

```bash
./infra/run-terraform --action apply --write-inventory
```

Full Ansible bring-up:

```bash
./infra/run-ansible
```

Safe rerun for an existing live cluster:

```bash
./infra/run-ansible --skip-pvc-migration
```

`run-ansible` prints a short preflight summary before it starts so you can see whether it will:
- auto-generate self-signed TLS
- auto-render Zulip secret values
- deploy or skip object-storage backups
- apply static sealed secrets or use bootstrap-only runtime secrets

Useful flags:

```bash
./infra/run-ansible --skip-backups
./infra/run-ansible --skip-pvc-migration
./infra/run-terraform --action destroy --auto-approve
```

For persistent live data across VM rebuilds, configure the OpenStack Terraform module to reattach the same control-plane block volume by ID, then run [run-ansible](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\run-ansible) so the OS mount and k3s storage wiring are restored.
