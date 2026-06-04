# Terraform: S3 Batch + Lambda scrubber

Deploys:

- Scrubber Lambda (container image) + execution IAM
- Optional destination bucket
- Policy allowing S3 Batch to invoke Lambda
- **S3 Batch Operations IAM role** (read manifests, write reports, invoke Lambda)

Batch jobs use **prefix manifests** (`scripts/generate_batch_manifest.py` or `kohort_sanitize.py run`), not S3 Inventory.

## Automated client setup

From repo root (requires [Terraform CLI](https://developer.hashicorp.com/terraform/install) >= 1.5):

```bash
# client.yaml: deploy: terraform
python3 scripts/kohort_sanitize.py --config client.yaml setup --terraform
# or: setup --skip-image --terraform
```

This writes `terraform.tfvars`, runs `terraform init` and `terraform apply`. Use `kohort_sanitize.py run` / `status` afterward (same as CloudFormation).

## Usage (module / manual)

```hcl
module "sanitizer" {
  source = "../../iac/terraform/lambda_batch"

  name_prefix        = "kohort-s3-sanitizer"
  source_bucket_name = "kohort-raw-data"

  # Same bucket; output key = sanitized/<full source object key>
  dest_bucket_name   = "kohort-raw-data"
  create_dest_bucket = false

  # Key mapping (see docs/RUNBOOK.md):
  # Option A (simplest): source_prefix="" and dest_prefix="sanitized/"
  # Option B (equivalent when all keys start with kohort-datalocker/):
  source_prefix      = "kohort-datalocker/"
  dest_prefix        = "sanitized/kohort-datalocker/"

  # Config bucket: rulesets + ops (one per account)
  ruleset_uri      = "s3://kohort-sanitizer-config/rulesets/kohort-datalocker.yaml"
  ops_bucket_name  = "kohort-sanitizer-config"

  # Recommended: pull Kohort public image and push into your ECR, then reference it here.
  lambda_image_uri = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/kohort-s3-sanitizer:<version-tag>"

  reserved_concurrent_executions = 500
}
```

Clients should not need to build the image. Prefer **pull public → push to your ECR** (see `scrubber/container/README.md`).

## After apply

1. Push a new image tag to your ECR; set `lambda_image_uri` (pin the tag).
2. Upload or generate a manifest under `manifests/` (see `kohort_sanitize.py run`).
3. Create an S3 Batch job using `batch_operations_role_arn` and `lambda_function_arn` (see [scripts/create-batch-job.example.sh](../../../scripts/create-batch-job.example.sh)).

## Outputs

| Output | Use |
|--------|-----|
| `lambda_function_arn` | S3 Batch job Lambda target |
| `batch_operations_role_arn` | S3 Batch job IAM role |
| `batch_operations_policy_arn` | Attached to batch role automatically |

**Full step-by-step commands (init, apply, manifests, Batch job):** [../../../docs/RUNBOOK.md](../../../docs/RUNBOOK.md).
