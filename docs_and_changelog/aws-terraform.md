# AWS one-click (Terraform)

A root module in `deploy/aws/` that creates a **new** VM appliance: Elastic IP, security group, SSM,
cloud-init that installs Docker and runs `make edge-up`. It does **not** import or replace the
Frankfurt pilot (`i-03ee4ae19a18619c9` / `63.185.15.12`).

`terraform apply` returns when the AWS objects exist. The room is ready when
`https://<hostname>/healthz` returns 200 — often 10–15 minutes later (image builds). There is no waiter.

## What you pass

Required: `hostname`, `room_password`, `admin_password`. In `public` mode (the default), also
`letsencrypt_email`.

Copy `deploy/aws/terraform.tfvars.example` to `terraform.tfvars` (gitignored) and apply from
`deploy/aws/`.

Optional:

- `route53_zone_id` — Terraform writes `hostname` and `*.hostname` A records to the Elastic IP.
  Without it, you create those two records yourself (any DNS). Cloudflare is not in this module.
- `access_mode=private` + `access_cidr` — 80/443/media only from that CIDR (a Firezone / VPN range).
  TLS is Caddy's internal CA (browser warning). Let's Encrypt HTTP-01 cannot see a private box.
- `ssh_cidr` — open port 22 from that range. Omit it (default): no SSH; use SSM.
- `vpc_id` / `subnet_id` — otherwise the default VPC and its first public subnet.
- `instance_type` — default `c7i.xlarge` (cheap enough to log in). Pass `c7i.2xlarge` for real STT.
- `git_ref` — default `main`.
- `git_token` — HTTPS token for a **private** `git_repo`. Stored in SSM, used only to clone on
  first boot, never written into `.env` or user-data. Omit it when the repo is public.
- `ami_id` — a Marvin AMI from `packer build deploy/aws/ami.pkr.hcl`. First boot then
  writes `.env` and `docker compose up` (minutes). Omit it: stock Ubuntu and a 10–15
  minute image build, same as before.

## Where secrets live

Terraform **outputs never include secret values**. After apply it tells you the paths:

| What | Where |
| --- | --- |
| Room / admin login passwords | The values you put in `terraform.tfvars`. Copies in AWS SSM as SecureString `/<name>/room_password` and `/<name>/admin_password`. Also written into `.env` on first boot. |
| `git_token` (optional) | SSM `/<name>/git_token` if you passed one. Clone only; not in `.env`. |
| LiveKit key/secret, `MARVIN_SESSION_SECRET` | Generated on the VM, only at `/home/ubuntu/marvin/.env` (mode `0600`). Not in state. |
| Bootstrap log | `/var/log/marvin-bootstrap.log`; status `ok`/`failed` in `/var/lib/marvin/status` |

The login banner on the VM repeats the same map. Reboots keep `.env` (keys are not rotated).

Harness API keys and GitHub stay in Settings, as before. They are not Terraform inputs.

## After apply

```
terraform output
# url, healthz, public_ip, secrets_path, secrets_note, ssm
aws ssm start-session --target "$(terraform output -raw instance_id)"
```

Stop the instance to stop compute. Keep the Elastic IP so DNS does not move (~$3.60/month for the
address either way). `terraform destroy` releases the IP and deletes the SSM parameters.

After the box is up, new code on GitHub does **not** appear until an admin uses Settings → This
machine → Update (or `make update` on the VM). Terraform apply again would replace the instance.
See `updates.md`.

## Cost (order of magnitude)

- Elastic IP / public IPv4: about $0.005/hour whether the VM is running or stopped.
- `c7i.xlarge` while running: the real bill. Stop it when you are not testing.
- 60 GB gp3 root volume persists while the instance exists.

## Baked AMI

```
packer init deploy/aws
packer build -var region=eu-central-1 deploy/aws/ami.pkr.hcl
# then: terraform apply -var ami_id=ami-...
```

The image is Ubuntu 24.04 plus Docker, a clone of `git_repo` at `git_ref`, the
sandbox image, and the edge compose images. Cloud-init still writes `.env` and
starts the stack; it skips clone and `docker build`. Settings → Update still
pulls new code.

## Not in v1

Cloudflare provider, creating a VPC, a blocking health wait, replacing the existing pilot,
Cosign on the AMI / images (optional 5b).
