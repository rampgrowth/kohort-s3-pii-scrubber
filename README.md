# Kohort S3 Sanitizer

Remove known PII columns from **CSV** and **Parquet** files in S3 — at scale, entirely **inside your own AWS account**.

The sanitizer uses **S3 Batch Operations + AWS Lambda**: point it at an S3 prefix and it writes a sanitized copy of every object, preserving a **1:1 key mapping** (default output: `sanitized/<original key>` in the same bucket). Source objects are never modified or deleted.

**Your raw data never leaves your account.** The only external artifact is Kohort's public scrubber image, which setup copies into your private ECR.

## What you need


| Requirement                             | Notes                                                                                                            |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Python 3.10+, AWS CLI v2                | The driver script shells out to the AWS CLI                                                                      |
| AWS credentials with deploy permissions | ECR, Lambda, CloudFormation, CodeBuild, IAM — plus S3 read on the raw bucket and read/write on the config bucket |


You do **not** need Docker (the image is mirrored by CodeBuild inside AWS) or Terraform (CloudFormation is the default; Terraform is [optional](iac/terraform/lambda_batch/README.md)). Full details and version checks: [Prerequisites](docs/RUNBOOK.md#prerequisites-local-tools).

**Credentials:** either set `aws_profile` in `client.yaml`, or leave it unset and export credentials into your environment — exported **temporary credentials** (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`, e.g. from AWS SSO or `sts assume-role`) work fine. Don't set both: a configured profile takes precedence and exported credentials are ignored. If a temporary token expires mid-run, only the local commands are affected — the scrub job itself runs on IAM roles in your account — so re-export and re-run.

## Quick start

```bash
# 1. BOOTSTRAP 
# Creates a virtualenv, installs dependencies, copies client.yaml
./scripts/bootstrap-client.sh
source .venv/bin/activate

# 2. CONFIGURE
# - client.yaml: your region, buckets, prefixes (the template is commented)
# - ruleset: which columns to drop per file type (see docs/RULESET_SCHEMA.md;
#      client.yaml points at scrubber/rules/example-ruleset.yaml by default)

# 3. AWS SETUP
# Mirrors the scrubber image into your ECR and deploys the Lambda + IAM roles via CloudFormation
python3 scripts/kohort_sanitize.py --config client.yaml setup

# 4. DRY RUN
# Preview which objects a run would touch (no job created). --prefix is relative to the source_prefix in client.yaml. Append a date partition (e.g. t=installs/dt=2025-09-28/) to scrub a single day only.
python3 scripts/kohort_sanitize.py --config client.yaml run --prefix t=installs/ --dry-run

# 5. RUN 
# Run one scrub job per event type (each prints a job id):
python3 scripts/kohort_sanitize.py --config client.yaml run --prefix t=installs/
python3 scripts/kohort_sanitize.py --config client.yaml run --prefix t=inapps/    # in-app events
python3 scripts/kohort_sanitize.py --config client.yaml run --prefix t=sessions/
python3 scripts/kohort_sanitize.py --config client.yaml run --prefix t=organic_ad_revenue/
python3 scripts/kohort_sanitize.py --config client.yaml run --prefix t=attributed_ad_revenue/
python3 scripts/kohort_sanitize.py --config client.yaml run --prefix t=cohort_unified/    # no columns dropped; copied so all shared data sits under sanitized/

# 6. MONITOR 
# Watch a job until it completes
python3 scripts/kohort_sanitize.py --config client.yaml status --job-id <job-id> --watch
```

Verify the output:

```bash
aws s3 ls s3://<your-raw-bucket>/sanitized/<your-prefix>/ --recursive
```

The **[Runbook](docs/RUNBOOK.md)** covers every step in depth, including manual paths without the driver script, Terraform deploys, and troubleshooting.

## How it works

1. `run` lists the objects under your prefix and uploads a manifest to your config bucket.
2. S3 Batch Operations invokes the scrubber Lambda once per object.
3. The Lambda drops the columns named in your ruleset and writes the sanitized copy.
4. A completion report lands in your config bucket; errors go to CloudWatch Logs.

More detail: [Architecture](docs/ARCHITECTURE.md)

## Supported formats


| Format  | Extensions                | Notes                                                                             |
| ------- | ------------------------- | --------------------------------------------------------------------------------- |
| CSV     | `.csv`, `.csv.gz`, `.gz`  | Header row required; `.gz` = gzip-compressed CSV (e.g. AppsFlyer `part-00000.gz`) |
| Parquet | `.parquet`, `.gz.parquet` | Column drop via PyArrow; preserves source compression codec (e.g. GZIP)           |


## Documentation


| Doc                                                      | What's in it                                                            |
| -------------------------------------------------------- | ----------------------------------------------------------------------- |
| [Runbook](docs/RUNBOOK.md)                               | Step-by-step deploy + run guide (automated and manual), troubleshooting |
| [Ruleset schema](docs/RULESET_SCHEMA.md)                 | How to define which columns are dropped                                 |
| [Architecture](docs/ARCHITECTURE.md)                     | Components, data flow, cost and security notes                          |
| [Terraform module](iac/terraform/lambda_batch/README.md) | Deploy with Terraform instead of CloudFormation                         |
| [Container image](scrubber/container/README.md)          | Scrubber image reference (you don't need to build it)                   |


## Security

- All processing happens in your AWS account; no data is sent to Kohort or any third party.
- The Lambda's IAM role is scoped to reading your source prefix and ruleset, writing the destination prefix, and CloudWatch logging — nothing else.
- Source objects are never modified or deleted; sanitized copies are written to a separate prefix.

## Support

Contact your Kohort representative. For job issues, include the S3 Batch **job ID** and any relevant **CloudWatch log** excerpts from the scrubber Lambda's log group.