resource "aws_route53_record" "apex" {
  count   = var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.hostname
  type    = "A"
  ttl     = 60
  records = [aws_eip.this.public_ip]
}

resource "aws_route53_record" "wildcard" {
  count   = var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = "*.${var.hostname}"
  type    = "A"
  ttl     = 60
  records = [aws_eip.this.public_ip]
}
