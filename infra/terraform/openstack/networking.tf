# Floating IPs require L3: the tenant subnet must reach the external network (e.g. "public").
# If you see: "External network ... is not reachable from subnet ...", enable create_public_router
# or attach your subnet to an existing router in Horizon (Network -> Routers).

data "openstack_networking_network_v2" "external" {
  name = var.floating_ip_pool
}

locals {
  project_subnet_id = var.subnet_id
}

resource "openstack_networking_router_v2" "public_router" {
  count               = var.create_public_router ? 1 : 0
  name                = "mlops-router-${var.project_id_suffix}"
  admin_state_up      = true
  external_network_id = data.openstack_networking_network_v2.external.id
}

resource "openstack_networking_router_interface_v2" "project_subnet" {
  count     = var.create_public_router ? 1 : 0
  router_id = openstack_networking_router_v2.public_router[0].id
  subnet_id = local.project_subnet_id

  lifecycle {
    precondition {
      condition     = local.project_subnet_id != ""
      error_message = "Set subnet_id in terraform.tfvars (Horizon -> Network -> Subnets). Required when create_public_router is true."
    }
  }
}

resource "openstack_networking_secgroup_v2" "mlops_cluster" {
  name        = "mlops-cluster-${var.project_id_suffix}"
  description = "Managed security group for the MLOps control-plane and worker nodes"
}

resource "openstack_networking_secgroup_rule_v2" "ssh_ingress" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.mlops_cluster.id
}

resource "openstack_networking_secgroup_rule_v2" "http_ingress" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 80
  port_range_max    = 80
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.mlops_cluster.id
}

resource "openstack_networking_secgroup_rule_v2" "https_ingress" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 443
  port_range_max    = 443
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.mlops_cluster.id
}

resource "openstack_networking_secgroup_rule_v2" "k3s_api_internal" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 6443
  port_range_max    = 6443
  remote_group_id   = openstack_networking_secgroup_v2.mlops_cluster.id
  security_group_id = openstack_networking_secgroup_v2.mlops_cluster.id
}

resource "openstack_networking_secgroup_rule_v2" "kubelet_internal" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 10250
  port_range_max    = 10250
  remote_group_id   = openstack_networking_secgroup_v2.mlops_cluster.id
  security_group_id = openstack_networking_secgroup_v2.mlops_cluster.id
}

resource "openstack_networking_secgroup_rule_v2" "flannel_internal" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "udp"
  port_range_min    = 8472
  port_range_max    = 8472
  remote_group_id   = openstack_networking_secgroup_v2.mlops_cluster.id
  security_group_id = openstack_networking_secgroup_v2.mlops_cluster.id
}
