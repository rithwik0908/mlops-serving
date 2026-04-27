output "project_id_suffix" {
  value = var.project_id_suffix
}

output "control_plane_name" {
  value = openstack_compute_instance_v2.control_plane.name
}

output "control_plane_id" {
  value = openstack_compute_instance_v2.control_plane.id
}

output "control_plane_private_ip" {
  value = openstack_compute_instance_v2.control_plane.network[0].fixed_ip_v4
}

output "worker_name" {
  value = openstack_compute_instance_v2.worker.name
}

output "worker_id" {
  value = openstack_compute_instance_v2.worker.id
}

output "worker_private_ip" {
  value = openstack_compute_instance_v2.worker.network[0].fixed_ip_v4
}

output "floating_ip" {
  value       = openstack_networking_floatingip_v2.control_plane_fip.address
  description = "SSH here to reach the control-plane node; the worker is reached through the control-plane jump host."
}

output "control_plane_block_volume_id" {
  value       = var.attach_block_volume ? local.block_volume_id : null
  description = "Persistent block volume attached to the control-plane. Reuse this ID in future rebuilds to keep live PVC data."
}

output "managed_security_group" {
  value       = openstack_networking_secgroup_v2.mlops_cluster.name
  description = "Managed security group added to both nodes (includes SSH, HTTP, HTTPS, and k3s internal traffic)."
}

output "ansible_inventory_ini" {
  description = "Convenience output for Ansible inventory (INI format)."
  value       = <<-EOT
  [control_plane]
  control-plane ansible_host=${openstack_networking_floatingip_v2.control_plane_fip.address} private_ip=${openstack_compute_instance_v2.control_plane.network[0].fixed_ip_v4}

  [workers]
  worker-1 ansible_host=${openstack_compute_instance_v2.worker.network[0].fixed_ip_v4} private_ip=${openstack_compute_instance_v2.worker.network[0].fixed_ip_v4} ansible_ssh_common_args='-o ProxyJump=cc@${openstack_networking_floatingip_v2.control_plane_fip.address}'

  [chameleon:children]
  control_plane
  workers

  [chameleon:vars]
  ansible_user=cc
  EOT
}
