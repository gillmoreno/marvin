# Bake Docker + the Marvin images so first boot is "write .env, docker compose up".
#   packer init deploy/aws && packer build -var region=eu-central-1 deploy/aws/ami.pkr.hcl
# Then terraform apply -var ami_id=ami-...
packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = ">= 1.3.0"
    }
  }
}

variable "region" { type = string }
variable "git_repo" {
  type    = string
  default = "https://github.com/gillmoreno/marvin.git"
}
variable "git_ref" {
  type    = string
  default = "main"
}
variable "sandbox_harnesses" {
  type    = string
  default = "claude-code grok"
}

source "amazon-ebs" "marvin" {
  region                  = var.region
  instance_type           = "c7i.xlarge"
  ami_name                = "marvin-{{timestamp}}"
  ssh_username            = "ubuntu"
  source_ami_filter {
    filters = {
      name                = "ubuntu/images/hvm-ssd*/ubuntu-noble-24.04-amd64-server-*"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
      architecture        = "x86_64"
    }
    owners      = ["099720109477"]
    most_recent = true
  }
  launch_block_device_mappings {
    device_name           = "/dev/sda1"
    volume_size           = 60
    volume_type           = "gp3"
    delete_on_termination = true
  }
}

build {
  sources = ["source.amazon-ebs.marvin"]
  provisioner "shell" {
    inline = [
      "export DEBIAN_FRONTEND=noninteractive",
      "sudo apt-get update -y",
      "sudo apt-get install -y git make curl ca-certificates",
      "curl -fsSL https://get.docker.com | sudo sh",
      "sudo usermod -aG docker ubuntu",
      "git clone --depth 1 --branch ${var.git_ref} ${var.git_repo} /home/ubuntu/marvin",
      "cd /home/ubuntu/marvin && (test -f .env || cp .env.example .env) && sg docker -c 'SANDBOX_HARNESSES=\"${var.sandbox_harnesses}\" make sandbox-image'",
      "cd /home/ubuntu/marvin && sg docker -c 'NODE_IP=127.0.0.1 LIVEKIT_API_KEY=marvin LIVEKIT_API_SECRET=packer-build-not-used-000000000000 MARVIN_INSTALL_DIR=/home/ubuntu/marvin docker compose -f docker-compose.edge.yml build'",
      "sudo chown -R ubuntu:ubuntu /home/ubuntu/marvin",
    ]
  }
}
