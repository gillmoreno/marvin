data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name_prefix        = "${var.name}-"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = { Name = var.name }
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "params" {
  statement {
    sid       = "ReadBootPasswords"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${var.name}/*"]
  }
}

resource "aws_iam_role_policy" "params" {
  name   = "ssm-parameters"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.params.json
}

resource "aws_iam_instance_profile" "this" {
  name_prefix = "${var.name}-"
  role        = aws_iam_role.this.name
}

resource "aws_ssm_parameter" "room_password" {
  name  = "/${var.name}/room_password"
  type  = "SecureString"
  value = var.room_password
  tags  = { Name = var.name }
}

resource "aws_ssm_parameter" "admin_password" {
  name  = "/${var.name}/admin_password"
  type  = "SecureString"
  value = var.admin_password
  tags  = { Name = var.name }
}

resource "aws_ssm_parameter" "git_token" {
  count = var.git_token != "" ? 1 : 0
  name  = "/${var.name}/git_token"
  type  = "SecureString"
  value = var.git_token
  tags  = { Name = var.name }
}
