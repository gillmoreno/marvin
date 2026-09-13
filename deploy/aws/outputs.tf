output "url" {
  value       = "https://${var.hostname}"
  description = "Room URL. Not live the moment apply finishes; wait until healthz returns ok."
}

output "healthz" {
  value       = "https://${var.hostname}/healthz"
  description = "Ready when this returns HTTP 200. First boot is often 10–15 minutes (Docker images)."
}

output "public_ip" {
  value       = aws_eip.this.public_ip
  description = "Elastic IP. Stays put across stop/start. Point hostname and *.hostname here if you did not pass route53_zone_id."
}

output "instance_id" {
  value       = aws_instance.this.id
  description = "EC2 instance. Stop this to save compute; keep the Elastic IP."
}

output "dns_managed_by_terraform" {
  value       = var.route53_zone_id != ""
  description = "True when this apply wrote the two Route 53 A records."
}

output "secrets_path" {
  value       = "/home/ubuntu/marvin/.env"
  description = "On the VM, mode 0600. LiveKit keys and MARVIN_SESSION_SECRET were generated here. Login passwords are the Terraform variables (also in SSM)."
}

output "secrets_note" {
  value = <<-EOT
    Login passwords: the room_password and admin_password you passed to Terraform.
      Copies: AWS SSM /${var.name}/room_password and /${var.name}/admin_password (SecureString).
    LiveKit keys and MARVIN_SESSION_SECRET: generated on first boot on the VM only,
      at /home/ubuntu/marvin/.env (not in Terraform state, not in these outputs).
    Private-repo clone token (if you passed git_token): AWS SSM /${var.name}/git_token.
      Used once on first boot to clone; not written into .env.
    Bootstrap log: /var/log/marvin-bootstrap.log   status: /var/lib/marvin/status
  EOT
}

output "ssm" {
  value       = "aws ssm start-session --target ${aws_instance.this.id} --region ${var.region}"
  description = "Admin shell. No SSH port unless you set ssh_cidr."
}
