# CloudFormation: S3 Batch + Lambda scrubber

Console- and CLI-friendly deployment when you do not use Terraform.

## Full runbook

**Step-by-step instructions** (image publish, stack deploy, manifests, Batch job):  
[../../../docs/RUNBOOK.md](../../../docs/RUNBOOK.md) — see **Quick start (automated)** or **Step 3B**.

## Quick reference

| File | Purpose |
|------|---------|
| `template.yaml` | Stack template (Lambda + scrubber IAM + **batch operations role**) |
| `parameters.json` | Example parameters |

## What this stack creates

- Lambda scrubber + execution role
- S3 Batch operations IAM role (`BatchOperationsRoleArn`)
- `BatchOperationsPolicyArn` (Lambda invoke; attached to batch role)

## Automated client setup

```bash
cp scripts/client.yaml.example client.yaml
pip install -r scripts/requirements.txt
python3 scripts/kohort_sanitize.py --config client.yaml setup
```

## What you still do manually (without the driver)

1. Pull public image → push to your ECR (Step 1 in runbook)
2. Create config bucket + upload ruleset (Step 2)
3. Deploy stack (Step 3B) — batch role is included in current template
4. Run Batch jobs (Step 4) — or `kohort_sanitize.py run --prefix ...`

For **S3 Inventory**, use [Terraform](../../terraform/lambda_batch/README.md) (optional; manifest-based jobs do not require inventory).
