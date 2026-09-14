variable "name" {
  type        = string
  description = "Prefix for AWS resource names (IAM, security group, SSM parameters)."
  default     = "marvin"
}

variable "region" {
  type        = string
  description = "AWS region for this throwaway stack."
  default     = "eu-central-1"
}

variable "hostname" {
  type        = string
  description = "Public DNS name of this install (MARVIN_DOMAIN), e.g. marvin.example.com. You must point it at the Elastic IP (Route 53 below, or by hand)."
}

variable "room_password" {
  type        = string
  sensitive   = true
  description = "Password that joins the room as a participant. Written to SSM, then into /home/ubuntu/marvin/.env on first boot. Not printed in outputs."
  validation {
    condition     = length(var.room_password) >= 8
    error_message = "room_password must be at least 8 characters."
  }
}

variable "admin_password" {
  type        = string
  sensitive   = true
  description = "Password that joins as admin (Settings, GitHub client id, coding agents). Same storage as room_password."
  validation {
    condition     = length(var.admin_password) >= 8
    error_message = "admin_password must be at least 8 characters."
  }
}

variable "access_mode" {
  type        = string
  description = "public: 80/443/media open to the world (Let's Encrypt). private: those ports only from access_cidr (VPN); TLS is the internal CA."
  default     = "public"
  validation {
    condition     = contains(["public", "private"], var.access_mode)
    error_message = "access_mode must be public or private."
  }
}

variable "access_cidr" {
  type        = string
  description = "CIDR that may reach 80/443/media (and the room) when access_mode is private. Ignored in public mode."
  default     = ""
}

variable "ssh_cidr" {
  type        = string
  description = "If set, open TCP/22 from this CIDR. Leave empty: no SSH port (use SSM). Never 0.0.0.0/0."
  default     = ""
  validation {
    condition     = var.ssh_cidr == "" || var.ssh_cidr != "0.0.0.0/0"
    error_message = "ssh_cidr cannot be 0.0.0.0/0; use SSM or a laptop/VPN CIDR."
  }
}

variable "key_name" {
  type        = string
  description = "Existing EC2 key pair name. Only needed if you set ssh_cidr and want SSH keys. SSM works without it."
  default     = ""
}

variable "letsencrypt_email" {
  type        = string
  description = "Let's Encrypt account e-mail. Required when access_mode is public."
  default     = ""
}

variable "route53_zone_id" {
  type        = string
  description = "If set, Terraform creates A records for hostname and *.hostname pointing at the Elastic IP. Otherwise you create DNS yourself."
  default     = ""
}

variable "vpc_id" {
  type        = string
  description = "VPC to use. Empty = the account default VPC."
  default     = ""
}

variable "subnet_id" {
  type        = string
  description = "Public subnet (route to an IGW). Empty = first default-VPC subnet that maps a public IP on launch."
  default     = ""
}

variable "instance_type" {
  type        = string
  description = "Default is cheap enough to log in; pass c7i.2xlarge when you want the real CPU Whisper."
  default     = "c7i.xlarge"
}

variable "volume_gb" {
  type        = number
  description = "Root disk. Images and the Whisper model need more than the AMI default 8 GB."
  default     = 60
}

variable "git_repo" {
  type        = string
  description = "Git URL cloud-init clones."
  default     = "https://github.com/gillmoreno/marvin.git"
}

variable "git_ref" {
  type        = string
  description = "Branch, tag, or sha to check out."
  default     = "main"
}

variable "git_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "HTTPS token used only to clone git_repo on first boot (private GitHub). Stored in SSM SecureString. Not written into .env and not put in user-data."
}

variable "ami_id" {
  type        = string
  default     = ""
  description = "If set, launch this AMI (Packer image from ami.pkr.hcl) instead of stock Ubuntu. First boot skips the 15-minute image build."
}

variable "sandbox_harnesses" {
  type        = string
  description = "Harnesses baked into marvin-sandbox:local. Keep this short on a small instance."
  default     = "claude-code grok"
}
