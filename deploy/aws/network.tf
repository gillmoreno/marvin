data "aws_vpc" "default" {
  count   = var.vpc_id == "" ? 1 : 0
  default = true
}

data "aws_vpc" "given" {
  count = var.vpc_id != "" ? 1 : 0
  id    = var.vpc_id
}

locals {
  vpc_id = var.vpc_id != "" ? data.aws_vpc.given[0].id : data.aws_vpc.default[0].id
}

data "aws_subnets" "public" {
  count = var.subnet_id == "" ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }
}

data "aws_subnets" "any" {
  count = var.subnet_id == "" ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}

locals {
  subnet_id = var.subnet_id != "" ? var.subnet_id : (
    length(try(data.aws_subnets.public[0].ids, [])) > 0
    ? data.aws_subnets.public[0].ids[0]
    : data.aws_subnets.any[0].ids[0]
  )
  room_cidrs = var.access_mode == "public" ? ["0.0.0.0/0"] : compact([var.access_cidr])
}

resource "aws_security_group" "this" {
  name_prefix = "${var.name}-"
  description = "Marvin edge: HTTPS, LiveKit media; SSH only if ssh_cidr is set"
  vpc_id      = local.vpc_id

  tags = { Name = var.name }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  for_each          = toset(local.room_cidrs)
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "HTTP (ACME + redirect)"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  for_each          = toset(local.room_cidrs)
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS room"
}

resource "aws_vpc_security_group_ingress_rule" "https_udp" {
  for_each          = toset(local.room_cidrs)
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = each.value
  ip_protocol       = "udp"
  from_port         = 443
  to_port           = 443
  description       = "HTTP/3"
}

resource "aws_vpc_security_group_ingress_rule" "livekit_tcp" {
  for_each          = toset(local.room_cidrs)
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 7881
  to_port           = 7881
  description       = "LiveKit media TCP"
}

resource "aws_vpc_security_group_ingress_rule" "livekit_udp" {
  for_each          = toset(local.room_cidrs)
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = each.value
  ip_protocol       = "udp"
  from_port         = 7882
  to_port           = 7882
  description       = "LiveKit media UDP"
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  count             = var.ssh_cidr != "" ? 1 : 0
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = var.ssh_cidr
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  description       = "SSH from ssh_cidr only"
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "outbound: git docker ACME APIs"
}
