check "access" {
  assert {
    condition     = var.access_mode != "private" || var.access_cidr != ""
    error_message = "access_mode=private requires access_cidr (your VPN / Firezone range)."
  }
  assert {
    condition     = var.access_mode != "public" || var.letsencrypt_email != ""
    error_message = "access_mode=public requires letsencrypt_email for Let's Encrypt."
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd*/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_eip" "this" {
  domain = "vpc"
  tags   = { Name = var.name }
}

locals {
  tls = var.access_mode == "public" ? var.letsencrypt_email : "internal"
  user_data = templatefile("${path.module}/bootstrap.sh.tftpl", {
    git_repo           = var.git_repo
    git_ref            = var.git_ref
    hostname           = var.hostname
    node_ip            = aws_eip.this.public_ip
    tls                = local.tls
    region             = var.region
    ssm_room           = aws_ssm_parameter.room_password.name
    ssm_admin          = aws_ssm_parameter.admin_password.name
    ssm_git            = try(aws_ssm_parameter.git_token[0].name, "")
    sandbox_harnesses  = var.sandbox_harnesses
    name               = var.name
  })
}

resource "aws_instance" "this" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.this.id]
  iam_instance_profile        = aws_iam_instance_profile.this.name
  associate_public_ip_address = true
  key_name                    = var.key_name != "" ? var.key_name : null
  user_data                   = local.user_data
  user_data_replace_on_change = true

  root_block_device {
    volume_size = var.volume_gb
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = { Name = var.name }

  lifecycle {
    precondition {
      condition     = var.access_mode != "private" || var.access_cidr != ""
      error_message = "access_mode=private requires access_cidr."
    }
    precondition {
      condition     = var.access_mode != "public" || var.letsencrypt_email != ""
      error_message = "access_mode=public requires letsencrypt_email."
    }
  }
}

resource "aws_eip_association" "this" {
  instance_id   = aws_instance.this.id
  allocation_id = aws_eip.this.id
}
