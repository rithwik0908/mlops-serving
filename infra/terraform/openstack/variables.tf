variable "project_id_suffix" {
  description = "Course project id suffix for resource names, e.g. proj15"
  type        = string
}

variable "openstack_auth_url" {
  description = "OpenStack auth URL from Chameleon"
  type        = string
}

variable "openstack_region" {
  description = "OpenStack region name"
  type        = string
}

variable "openstack_tenant_name" {
  description = "Project/tenant name (optional if using application credential scoped to project or OS_PROJECT_ID)"
  type        = string
  default     = ""
}

variable "openstack_user_name" {
  description = "User name (omit when using application credentials)"
  type        = string
  default     = ""
}

variable "openstack_password" {
  description = "Password for username auth only (omit when using application credentials; never commit)"
  type        = string
  sensitive   = true
  default     = null
}

variable "application_credential_id" {
  description = "Application credential ID from Horizon (preferred over password for SSO accounts)"
  type        = string
  default     = ""
}

variable "application_credential_secret" {
  description = "Application credential secret (use TF_VAR_application_credential_secret; never commit)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openstack_tenant_id" {
  description = "OpenStack project/tenant UUID from Horizon (optional; recommended with application credentials on Chameleon)"
  type        = string
  default     = ""
}

variable "instance_name" {
  description = "VM name prefix for the control-plane and worker nodes"
  type        = string
  default     = "mlops-k8s"
}

variable "flavor_name" {
  description = "OpenStack flavor, e.g. m1.large"
  type        = string
  default     = "m1.large"
}

variable "image_name" {
  description = "Glance image name for your Chameleon site (set in tfvars)"
  type        = string
}

variable "key_pair" {
  description = "Existing OpenStack key pair name for SSH"
  type        = string
}

variable "network_id" {
  description = "Tenant network UUID the VM attaches to"
  type        = string
}

variable "subnet_id" {
  description = "Subnet UUID for the public router interface (Horizon -> Network -> Subnets). Required when create_public_router is true."
  type        = string
  default     = ""

  validation {
    condition     = !var.create_public_router || var.subnet_id != ""
    error_message = "When create_public_router is true, subnet_id must be set to your tenant subnet UUID."
  }
}

variable "floating_ip_pool" {
  description = "External network name for allocating a floating IP (site-specific)"
  type        = string
  default     = "public"
}

variable "create_public_router" {
  description = "If true, create a router with external gateway and attach your project's first subnet. Set false if you already have a router connecting this network to public."
  type        = bool
  default     = true
}

variable "blazar_reservation_id" {
  description = "Legacy single-node reservation UUID. Prefer control_plane_blazar_reservation_id and worker_blazar_reservation_id for a two-node cluster."
  type        = string
  default     = ""
}

variable "control_plane_blazar_reservation_id" {
  description = "Blazar reservation UUID for the control-plane node. When set, used as flavor_id; flavor_name is ignored for that node."
  type        = string
  default     = ""
}

variable "worker_blazar_reservation_id" {
  description = "Blazar reservation UUID for the worker node. When set, used as flavor_id; flavor_name is ignored for that node."
  type        = string
  default     = ""
}

variable "install_k3s_cloud_init" {
  description = "If true, embed cloud-init that installs k3s on the control-plane node on first boot"
  type        = bool
  default     = false
}

variable "security_groups" {
  description = "Existing security group names for the instances. A managed mlops cluster group is added automatically."
  type        = list(string)
}

variable "attach_block_volume" {
  description = "Attach a persistent block volume to the control-plane node."
  type        = bool
  default     = false
}

variable "existing_block_volume_id" {
  description = "Existing Cinder volume UUID to reattach for persistent data. Recommended for rebuilds where data must survive VM recreation."
  type        = string
  default     = ""
}

variable "create_block_volume" {
  description = "Create a new block volume in Terraform instead of reusing an existing one."
  type        = bool
  default     = false
}

variable "block_volume_name" {
  description = "Name to use when Terraform creates the persistent block volume."
  type        = string
  default     = ""
}

variable "block_volume_size_gib" {
  description = "Size in GiB for a Terraform-managed block volume."
  type        = number
  default     = 150
}

variable "block_volume_type" {
  description = "Chameleon/OpenStack block volume type, e.g. ceph-ssd."
  type        = string
  default     = "ceph-ssd"
}

variable "block_volume_availability_zone" {
  description = "Availability zone for the block volume."
  type        = string
  default     = "nova"
}
