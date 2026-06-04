# Kohort S3 Sanitizer

In-account S3 scrubbing for client backfills: drop known PII columns from **CSV** or **Parquet** files while preserving **1:1 object key mapping**, using **S3 Batch Operations + Lambda**.

Raw data never leaves the client's AWS account. Sanitized output is written to a dedicated bucket/prefix.

## Repository layout

```
scrubber/
  container/          # Lambda container image (scrubber logic)
  rules/              # Example rulesets
docs/                 # Architecture, runbook, ruleset schema
iac/
  terraform/lambda_batch/
  cloudformation/lambda_batch/
```

## Quick start (platform team)

**Clients:** see [docs/RUNBOOK.md](docs/RUNBOOK.md#quick-start-automated) — `client.yaml` + `scripts/kohort_sanitize.py` (`setup` with CloudFormation or `--terraform`, then `run`, `status`).

Manual path:

1. Deploy infrastructure with **Terraform** or **CloudFormation** (see [docs/RUNBOOK.md](docs/RUNBOOK.md) Step 3A or 3B).
2. Upload a ruleset to S3 (see `scrubber/rules/example-ruleset.yaml` and `docs/RULESET_SCHEMA.md`).
3. Publish the scrubber image to your ECR (recommended: **pull public → push to your ECR**, see `scrubber/container/README.md`).
4. Create an **S3 Batch Operations** job that invokes the scrubber Lambda per object (manifest from prefix: `scripts/generate_batch_manifest.py`).
5. Validate using the Batch completion report and CloudWatch Logs.

See [docs/RUNBOOK.md](docs/RUNBOOK.md) for the full Terraform + S3 Batch runbook (image publish, apply, manifests, validation).

## Supported formats

| Format | Extensions | Notes |
|--------|------------|--------|
| CSV | `.csv`, `.csv.gz`, `.gz` | Header row required; `.gz` = gzip-compressed CSV (e.g. AppsFlyer `part-00000.gz`) |
| Parquet | `.parquet`, `.gz.parquet` | Column drop via PyArrow; preserves source compression codec (e.g. GZIP) |

## Configuration

Lambda environment variables (set by IaC):

| Variable | Description |
|----------|-------------|
| `DEST_BUCKET` | Sanitized output bucket |
| `DEST_PREFIX` | Prepended to mapped keys (default `sanitized/` → output at `sanitized/<source key>`) |
| `SOURCE_PREFIX` | Prefix stripped before mapping (default empty — keep full source key under `sanitized/`) |
| `RULESET_URI` | `s3://bucket/key` to YAML/JSON ruleset |
