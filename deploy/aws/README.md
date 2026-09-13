# Marvin on AWS

Terraform root module. See `docs_and_changelog/aws-terraform.md` for the full story (secrets, DNS, public vs private).

```sh
cp terraform.tfvars.example terraform.tfvars   # edit hostname + passwords
terraform init
terraform apply
terraform output            # URL is not live yet
# wait until https://<hostname>/healthz is 200
```

This stack is new. It will not attach to the Frankfurt pilot.
