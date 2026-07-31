# Client runbook

Step-by-step guide for deploying the scrubber with **Terraform** or **CloudFormation**, then running a backfill via **S3 Batch Operations**.

## Prerequisites (local tools)

The driver (`kohort_sanitize.py`) is Python; it shells out to the AWS CLI (and Terraform when `deploy: terraform`). You do **not** need local Docker if `image_publish: codebuild` (default).

| Tool | Required? | Notes |
|------|-----------|--------|
| **Python 3.10+** | Yes | Driver uses `dataclasses.replace` and modern type hints |
| **pip + venv** | Recommended | `scripts/bootstrap-client.sh` creates `.venv` and installs deps |
| **AWS CLI v2** | Yes | Must match credentials for `aws_profile` in `client.yaml` |
| **Terraform ≥ 1.5** | If `deploy: terraform` | Not needed for CloudFormation-only deploy |
| **Docker** | Only if `image_publish: docker` | CodeBuild path mirrors the image in AWS |
| **Bash** | Optional | Only for `bootstrap-client.sh` and other `scripts/*.sh` helpers |

Python packages (installed by bootstrap or `pip install -r scripts/requirements.txt`): `boto3`, `PyYAML`.

### Quick check

Run from any directory before `setup`:

```bash
python3 --version          # expect 3.10 or newer
aws --version              # AWS CLI v2
aws sts get-caller-identity --profile "<your-profile>"   # omit --profile if using default chain

# Only when deploy: terraform in client.yaml (or setup --terraform):
terraform version        # expect >= 1.5

# Only when image_publish: docker in client.yaml (or setup --docker-image):
docker version
```

**Not required on the operator laptop:** building the scrubber image (CodeBuild does that by default), or the Python runtime inside the Lambda container (that runs in AWS).

**AWS permissions:** IAM access to deploy ECR/Lambda/CloudFormation/CodeBuild/IAM (as applicable), plus S3 read on the raw bucket and read/write on the config bucket.

---

## Quick start (automated)

Use the driver script instead of running each step by hand. See [Prerequisites](#prerequisites-local-tools) for local tool versions and quick checks.

```bash
# 0. From repo root — copy config template, create venv, install deps
chmod +x scripts/bootstrap-client.sh
./scripts/bootstrap-client.sh

# 1. Edit client.yaml (AWS profile, buckets, source_prefix, public_image tag, name_prefix)
#    name_prefix must be unique in your account (Lambda + IAM role names derive from it).

# 2. Activate venv (if not already)
source .venv/bin/activate

# 3. One-time setup (image via CodeBuild by default — no local Docker)
python3 scripts/kohort_sanitize.py --config client.yaml setup
# Alternatives:
#   setup --skip-image          # image already in your ECR
#   setup --docker-image      # local docker pull/push
#   setup --terraform         # deploy Lambda with Terraform instead of CloudFormation

# 4. Preview objects for a prefix (optional)
python3 scripts/kohort_sanitize.py --config client.yaml run \
  --prefix kohort-datalocker/t=installs/dt=2025-09-28/ --dry-run

# 5. Run a scrub job
python3 scripts/kohort_sanitize.py --config client.yaml run \
  --prefix kohort-datalocker/t=installs/dt=2025-09-28/

# 6. Check job status
python3 scripts/kohort_sanitize.py --config client.yaml status --job-id <job-id>
```

If you previously created the batch IAM role manually (old runbook Step 3B.4), `setup` removes that role when it is not stack-managed, then CloudFormation recreates it.

Preview object count without starting a job: add `--dry-run` to `run`.

The sections below are the **manual reference** (Terraform path, console steps, troubleshooting). The driver automates **Step 3A (Terraform)** or **Step 3B (CloudFormation)** via `deploy` in `client.yaml` or `setup --terraform` / `setup --cloudformation`. Both paths include the batch IAM role; `run` and `status` read the correct outputs automatically.

---

| Choose your deploy path | Section | Automated |
|-------------------------|---------|-----------|
| **Terraform** (Lambda + batch IAM role) | [Step 3A](#step-3a--deploy-with-terraform) | `deploy: terraform` or `setup --terraform` |
| **CloudFormation** (Lambda + scrubber IAM + batch role) | [Step 3B](#step-3b--deploy-with-cloudformation) | `deploy: cloudformation` (default) |

Steps 1–2 (image + config bucket) and Steps 4–6 (Batch job, monitor, validate) are the same for both paths.

---

## Before you start

Fill in this checklist before deploy (`terraform apply` or `cloudformation deploy`).

| Item | Description | Example |
|------|-------------|-------------------|
| **AWS account** | Account where raw data lives | `123456789012` |
| **Region** | Same region as S3 buckets | `eu-west-1` |
| **AWS profile** | CLI profile with deploy permissions | `staging` |
| **Raw bucket** | Bucket containing source objects | `kohort-raw-data` |
| **Raw prefix** | Prefix to scope IAM and manifests (trailing `/`) | `kohort-datalocker/` |
| **Sanitized bucket** | Bucket for cleaned output — the only one you share with Kohort | `kohort-sanitized` |
| **Config bucket** | Constant bucket for rulesets + ops artifacts (see naming below) | `kohort-sanitizer-config` |
| **Ruleset key** | Path to YAML ruleset in ruleset bucket | `rulesets/kohort-datalocker.yaml` |
| **Lambda image** | Your ECR URI after Step 1 | `123456789012.dkr.ecr.eu-west-1.amazonaws.com/kohort-s3-sanitizer:<tag>` |

### Output layout (default)

- **Destination bucket** = `dest_bucket` if set (recommended: separate from raw data), otherwise the raw bucket.
- **Destination key** = `sanitized/<full source key>` (default; override via `dest_prefix`).

| Source key | Sanitized key |
|------------|----------------|
| `kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000….gz.parquet` | `sanitized/kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000.gz.parquet` |

Deploy settings for this mapping (Terraform **or** CloudFormation - use **both** values together):

| Setting | Terraform | CloudFormation parameter |
|---------|-----------|---------------------------|
| Source scope | `source_prefix = "kohort-datalocker/"` | `SourcePrefix=kohort-datalocker/` |
| Sanitized prefix | `dest_prefix = "sanitized/kohort-datalocker/"` | `DestPrefix=sanitized/kohort-datalocker/` |
| Sanitized bucket | `dest_bucket_name = "kohort-sanitized"`, `create_dest_bucket = false` | `DestBucketName=kohort-sanitized`, `CreateDestBucket=false` |

Alternative: omit `dest_bucket` to write back into the raw bucket under `dest_prefix`.

### Config bucket naming

One **config bucket per AWS account** (shared across datasets in that account). Use this pattern:

**Generic** : `kohort-sanitizer-config`

Raw data stays in buckets like `kohort-raw-data`. Config holds rulesets, manifests, and batch reports only.

### Ops layout (config bucket)

| Purpose | S3 path (examples) |
|---------|---------------------------|
| Ruleset | `s3://kohort-sanitizer-config/rulesets/kohort-datalocker.yaml` |
| Custom manifests | `s3://kohort-sanitizer-config/ops/manifests/<job>.csv` |
| Batch reports | `s3://kohort-sanitizer-config/ops/batch-reports/` |

---

## Step 1 — Publish the scrubber image to your ECR

**Lambda does not accept `public.ecr.aws/...` as `LambdaImageUri`.** The image must be in **private ECR** in the same region as Lambda.

### Recommended: CodeBuild (no local Docker)

Set `image_publish: codebuild` in `client.yaml` (default in `client.yaml.example`). `setup` deploys a small CloudFormation stack (`iac/cloudformation/image_mirror/template.yaml`) and runs CodeBuild to copy the public image into your ECR.

```bash
python3 scripts/kohort_sanitize.py --config client.yaml setup
# equivalent: setup --codebuild-image
```

### Alternative: local Docker

```bash
python3 scripts/kohort_sanitize.py --config client.yaml setup --docker-image
```

Or manual commands (legacy):

```bash
export AWS_PROFILE="<profile>"
export AWS_ACCOUNT_ID="<account-id>"
export AWS_REGION="<region>"
export ECR_REPO="kohort-s3-sanitizer" # or repo name

# Kohort public image
export PUBLIC_IMAGE="public.ecr.aws/g9w2z6w5/kohort-s3-sanitizer:latest"
export IMAGE_TAG="latest" # tag for image in your repository

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$ECR_REPO" >/dev/null 2>&1 \
  || aws ecr create-repository --region "$AWS_REGION" --repository-name "$ECR_REPO" >/dev/null

docker pull "$PUBLIC_IMAGE"

export LAMBDA_IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"
docker tag "$PUBLIC_IMAGE" "$LAMBDA_IMAGE_URI"
docker push "$LAMBDA_IMAGE_URI"

echo "Use in Terraform / CloudFormation LambdaImageUri: $LAMBDA_IMAGE_URI"
```

---

## Step 2 — Create the config bucket and upload the ruleset

The config bucket is **not** the raw data bucket. Create it once per account, then upload rulesets and use it for ops artifacts.

Edit the ruleset before upload: `drop_columns`, `include_globs`, `exclude_globs` (always exclude `**/_SUCCESS`).

```bash
export AWS_PROFILE="stg"   # staging example
export AWS_REGION="eu-west-1"
export CONFIG_BUCKET="kohort-sanitizer-config"
export RULESET_KEY="rulesets/kohort-datalocker.yaml"

# Create bucket once (skip if it already exists)
aws s3api head-bucket --bucket "$CONFIG_BUCKET" 2>/dev/null || \
  aws s3api create-bucket \
    --bucket "$CONFIG_BUCKET" \
    --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION"

# Recommended: block public access
aws s3api put-public-access-block --bucket "$CONFIG_BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Upload ruleset (from repo root)
aws s3 cp scrubber/rules/appsflyer-datalocker.yaml \
  "s3://${CONFIG_BUCKET}/${RULESET_KEY}"
```

Set:

```bash
export RULESET_URI="s3://${CONFIG_BUCKET}/${RULESET_KEY}"
export OPS_BUCKET="$CONFIG_BUCKET"
```

---

## Step 3A — Deploy with Terraform

### 3A.1 Create `terraform.tfvars`

**Automated:** skip this when using `kohort_sanitize.py setup --terraform` (writes `terraform.tfvars` from `client.yaml`).

Manual path:

```bash
cd iac/terraform/lambda_batch
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` (example):

```hcl
name_prefix        = "kohort-s3-sanitizer"
source_bucket_name = "kohort-raw-data"
source_prefix      = "kohort-datalocker/"   # IAM scope

dest_bucket_name   = "kohort-sanitized"        # separate bucket
create_dest_bucket = false
dest_prefix        = "sanitized/kohort-datalocker/"  # output: sanitized/kohort-datalocker/<path under source_prefix>

ruleset_uri        = "s3://kohort-sanitizer-config/rulesets/kohort-datalocker.yaml"
lambda_image_uri   = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/kohort-s3-sanitizer:<tag>"

ops_bucket_name              = "kohort-sanitizer-config"
manifests_prefix             = "ops/manifests/"
batch_reports_prefix         = "ops/batch-reports/"
create_batch_operations_role = true
```

### 3A.2 Init, plan, apply

```bash
export AWS_PROFILE="<profile>"
export AWS_REGION="<region>"

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### 3A.3 Save outputs for Batch

```bash
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export LAMBDA_ARN="$(terraform output -raw lambda_function_arn)"
export BATCH_ROLE_ARN="$(terraform output -raw batch_operations_role_arn)"
export OPS_BUCKET="$(terraform output -raw ops_bucket_name)"
export LAMBDA_NAME="$(terraform output -raw lambda_function_name)"

echo "LAMBDA_ARN=$LAMBDA_ARN"
echo "BATCH_ROLE_ARN=$BATCH_ROLE_ARN"
echo "OPS_BUCKET=$OPS_BUCKET"
```

---

## Step 3B — Deploy with CloudFormation

The CloudFormation template deploys:

- Scrubber **Lambda** (container image)
- Lambda **execution IAM** (read raw prefix, write sanitized prefix, read ruleset)
- **Managed policy** for S3 Batch to invoke Lambda (`BatchOperationsPolicyArn`)

It does **not** create: config bucket, ruleset, S3 Inventory, or the S3 Batch **operations role**. Complete Steps 1–2 first, then deploy the stack, then create the batch role (below).

Template: [`iac/cloudformation/lambda_batch/template.yaml`](../iac/cloudformation/lambda_batch/template.yaml)

### 3B.1 Staging parameter file (example)

Copy and edit [`iac/cloudformation/lambda_batch/parameters.json`](../iac/cloudformation/lambda_batch/parameters.json), or set parameters in the console.

| Parameter | Staging example |
|-----------|-----------------|
| `NamePrefix` | `kohort-s3-sanitizer` |
| `SourceBucketName` | `kohort-raw-data` |
| `SourcePrefix` | `kohort-datalocker/` |
| `DestBucketName` | `kohort-sanitized` |
| `CreateDestBucket` | `false` (`true` to let the stack create it) |
| `DestPrefix` | `sanitized/kohort-datalocker/` |
| `RulesetBucketName` | `kohort-sanitizer-config` |
| `RulesetObjectKey` | `rulesets/kohort-datalocker.yaml` |
| `LambdaImageUri` | `123456789012.dkr.ecr.eu-west-1.amazonaws.com/kohort-s3-sanitizer:latest` |
| `LambdaMemoryMb` | `2048` (optional; large Parquet) |
| `LambdaTimeoutSeconds` | `300` (optional) |

### 3B.2 Deploy the stack (CLI)

```bash
export AWS_PROFILE="<profile>"
export AWS_REGION="<region>"
export STACK_NAME="kohort-s3-sanitizer" # approriate name for the lambda stack

cd iac/cloudformation/lambda_batch

aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file template.yaml \
  --parameter-overrides file://parameters.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

**Console:** CloudFormation -> Create stack -> Upload `template.yaml` -> Enter the parameters above -> enable **IAM resource creation** (named IAM capabilities).

### 3B.3 Save stack outputs

```bash
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export LAMBDA_ARN="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionArn'].OutputValue" --output text)"
export BATCH_INVOKE_POLICY_ARN="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='BatchOperationsPolicyArn'].OutputValue" --output text)"
export BATCH_ROLE_ARN="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='BatchOperationsRoleArn'].OutputValue" --output text)"
export LAMBDA_NAME="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue" --output text)"

# From Step 2
export OPS_BUCKET="kohort-sanitizer-config"

echo "LAMBDA_ARN=$LAMBDA_ARN"
echo "BATCH_ROLE_ARN=$BATCH_ROLE_ARN"
echo "BATCH_INVOKE_POLICY_ARN=$BATCH_INVOKE_POLICY_ARN"
```

### 3B.4 S3 Batch operations IAM role

**Current CloudFormation template:** creates `${NamePrefix}-batch-role` automatically (read manifests/reports on the config bucket, invoke Lambda). Stack output: `BatchOperationsRoleArn`.

If you deployed an **older template** without the batch role, create it manually:

```bash
export NAME_PREFIX="kohort-s3-sanitizer"
export BATCH_ROLE_NAME="${NAME_PREFIX}-batch-role"
export CONFIG_BUCKET="kohort-sanitizer-config" # name of the config bucket with rulesets/ops

# Trust policy: S3 Batch Operations service
aws iam create-role --role-name "$BATCH_ROLE_NAME" \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "batchoperations.s3.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }' 2>/dev/null || true

# Inline policy: read manifests under config bucket; write batch reports
aws iam put-role-policy --role-name "$BATCH_ROLE_NAME" \
  --policy-name "${NAME_PREFIX}-batch-s3" \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {
        \"Sid\": \"ReadManifests\",
        \"Effect\": \"Allow\",
        \"Action\": [\"s3:GetObject\"],
        \"Resource\": \"arn:aws:s3:::${CONFIG_BUCKET}/ops/manifests/*\"
      },
      {
        \"Sid\": \"WriteReports\",
        \"Effect\": \"Allow\",
        \"Action\": [\"s3:PutObject\"],
        \"Resource\": \"arn:aws:s3:::${CONFIG_BUCKET}/ops/batch-reports/*\"
      }
    ]
  }"

# Attach stack output policy: invoke Lambda
aws iam attach-role-policy \
  --role-name "$BATCH_ROLE_NAME" \
  --policy-arn "$BATCH_INVOKE_POLICY_ARN"

export BATCH_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${BATCH_ROLE_NAME}"
echo "BATCH_ROLE_ARN=$BATCH_ROLE_ARN"
```

Or re-deploy with the current `template.yaml` / run `kohort_sanitize.py setup`.

## Step 4 — Run a scrub job (S3 Batch)

Choose **one** path:

| Path | When to use |
|------|-------------|
| **A. Single-object test** | Validate mapping + ruleset on one file (minutes) |
| **B. Prefix manifest** | Many files under one prefix (e.g. one `dt=`, all `h=*` hours) |

### Manifest format (required)

- **CSV**, one object per row: `bucket,key`
- **No header row** (a `bucket,key` header is treated as a failed task)
- Keys are the **full object key** (not `s3://` URIs)

**Valid example** (`ops/manifests/single-file.csv`):

```text
kohort-raw-data,kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000.gz.parquet
```

**Invalid** (do not use):

```text
bucket,key
kohort-raw-data,kohort-datalocker/...
```

**Multi-object example** (`ops/manifests/kohort-installs-one-hour.csv`):

```text
kohort-raw-data,kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000.gz.parquet
kohort-raw-data,kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00001.gz.parquet
```

### Path A — Single File

**1. Create manifest locally and upload**

```bash
export AWS_PROFILE="<profile>"
export RAW_BUCKET="kohort-raw-data"
export DEST_BUCKET="kohort-sanitized"
export SOURCE_KEY="kohort-datalocker/t=installs/dt=2022-08-27/h=1/part-00000.gz"
export MANIFEST_KEY="ops/manifests/single-file.csv"

cat > /tmp/manifest.csv <<EOF
${RAW_BUCKET},${SOURCE_KEY}
EOF

aws s3 cp /tmp/manifest.csv "s3://${OPS_BUCKET}/${MANIFEST_KEY}"
```

Expected sanitized output (separate bucket; with `DestPrefix=sanitized/kohort-datalocker/`):

```text
s3://${DEST_BUCKET}/sanitized/kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000.gz.parquet
```

**2. Create the Batch job**

```bash
export AWS_REGION="<region>"
export REPORT_PREFIX="ops/batch-reports/"

ETAG=$(aws s3api head-object --bucket "$OPS_BUCKET" --key "$MANIFEST_KEY" \
  --query ETag --output text | tr -d '"')

JOB_ID=$(aws s3control create-job \
  --region "$AWS_REGION" \
  --account-id "$ACCOUNT_ID" \
  --priority 10 \
  --role-arn "$BATCH_ROLE_ARN" \
  --operation "{\"LambdaInvoke\": {\"FunctionArn\": \"$LAMBDA_ARN\"}}" \
  --manifest "{\"Spec\": {\"Format\": \"S3BatchOperations_CSV_20180820\", \"Fields\": [\"Bucket\", \"Key\"]}, \"Location\": {\"ObjectArn\": \"arn:aws:s3:::$OPS_BUCKET/$MANIFEST_KEY\", \"ETag\": \"$ETAG\"}}" \
  --report "{\"Bucket\": \"arn:aws:s3:::$OPS_BUCKET\", \"Prefix\": \"$REPORT_PREFIX\", \"Format\": \"Report_CSV_20180820\", \"Enabled\": true, \"ReportScope\": \"AllTasks\"}" \
  --client-request-token "scrub-$(date +%s)" \
  --no-confirmation-required \
  --query JobId --output text)

echo "JobId: $JOB_ID"
```

**3. Wait for completion**

```bash
aws s3control describe-job \
  --region "$AWS_REGION" \
  --account-id "$ACCOUNT_ID" \
  --job-id "$JOB_ID" \
  --query 'Job.{Status:Status,Progress:ProgressSummary}'
```

Or use the helper script (same env vars):

```bash
export MANIFEST_KEY="ops/manifests/single-installs-test.csv"
./scripts/create-batch-job.example.sh
```

### Path B — Prefix manifest (recommended for multi-file jobs)

S3 Batch needs one manifest row per object. To scrub **all files under a prefix** (including every hour partition under a day), list the prefix and write the CSV with the helper script.

**Example:** all `h=0`, `h=1`, … objects for one day:

```bash
export AWS_PROFILE="<profile>"
export AWS_REGION="<region>"
export RAW_BUCKET="kohort-raw-data"
export CONFIG_BUCKET="kohort-sanitizer-config"
export RULESET_URI="s3://${CONFIG_BUCKET}/rulesets/kohort-datalocker.yaml"
export PREFIX="kohort-datalocker/t=installs/dt=2025-09-28/"
export MANIFEST_KEY="ops/manifests/installs-dt-2025-09-28.csv"

# Requires: python3 + scripts/requirements.txt
pip install -r scripts/requirements.txt

# Preview matching object count (no upload)
python3 scripts/generate_batch_manifest.py \
  --bucket "$RAW_BUCKET" \
  --prefix "$PREFIX" \
  --ruleset "$RULESET_URI" \
  --output "/tmp/manifest.csv" \
  --dry-run

# Generate and upload manifest to config bucket
python3 scripts/generate_batch_manifest.py \
  --bucket "$RAW_BUCKET" \
  --prefix "$PREFIX" \
  --ruleset "$RULESET_URI" \
  --output "s3://${CONFIG_BUCKET}/${MANIFEST_KEY}"
```

**Prefix tips**

| Goal | `--prefix` value |
|------|------------------|
| One day, all hours | `kohort-datalocker/t=installs/dt=2025-09-28/` |
| One hour only | `kohort-datalocker/t=installs/dt=2025-09-28/h=0/` |
| All installs tables/days | `kohort-datalocker/t=installs/` |

Use a **trailing `/`** on the prefix so keys like `.../dt=2025-09-28-extra/` are not included.

With `--ruleset`, include/exclude globs match the scrubber Lambda (skips `_SUCCESS`, applies `include_globs`). Without `--ruleset`, default excludes are `**/_SUCCESS` and `**/_temporary/**`; add `--include` for file types or pass explicit `--exclude`.

Then create the Batch job (same as Path A step 2) with `MANIFEST_KEY` above, or:

```bash
export OPS_BUCKET="$CONFIG_BUCKET"
export ACCOUNT_ID="<account-id>"
export LAMBDA_ARN="<lambda-arn>"
export BATCH_ROLE_ARN="<batch-role-arn>"
./scripts/create-batch-job.example.sh
```
---

## Step 5 — Monitor

| Where | What to check |
|-------|----------------|
| S3 Batch Operations console | Job status, succeeded/failed task counts |
| `s3://<ops-bucket>/ops/batch-reports/` | Per-task CSV report |
| CloudWatch Logs `/aws/lambda/<lambda_function_name>` | Scrub errors, ruleset skips |

---

## Step 6 — Validate

1. **Existence:** sanitized object under `sanitized/kohort-datalocker/...` (or your `DestPrefix`) in the sanitized bucket.
2. **Columns:** dropped fields absent (Parquet/CSV spot-check).
3. **Failures:** zero failures in Batch report; if failures, read Lambda logs (unsupported extension, ruleset skip, timeout).

```bash
# Example: confirm sanitized object exists
aws s3api head-object \
  --bucket "$DEST_BUCKET" \
  --key "sanitized/kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000.gz.parquet"
```

---

## Supported file types

| Extension | Supported |
|-----------|-----------|
| `.parquet`, `*.gz.parquet` | Yes (output keeps source column compression, e.g. GZIP) |
| `.csv`, `.csv.gz` | Yes |
| `.gz` only (legacy gzip CSV, e.g. `part-00000.gz`) | Yes |

---

## Tuning

| Symptom | Action |
|---------|--------|
| Lambda timeouts | Increase timeout/memory: Terraform `lambda_timeout_seconds` / `lambda_memory_mb`, or CloudFormation `LambdaTimeoutSeconds` / `LambdaMemoryMb` |
| `Runtime.InvalidEntrypoint` | Image must be **linux/amd64**; re-pull public image and push to ECR |
| High failure rate | CloudWatch logs; verify manifest has **no header**; verify ruleset globs |
| `NoSuchKey` with `t%3D` in the key | S3 Batch URL-encodes keys in the Lambda event; use scrubber image **after** `gz-csv-20260602155506` (includes URL decode fix) or newer |
| S3 / KMS throttling | Lower `reserved_concurrent_executions` |

---

## Rollback

1. Cancel or wait for in-flight Batch jobs to finish.
2. Delete sanitized objects under `sanitized/` if you need a clean re-run (scrubber overwrites on re-run).
3. **Terraform:** `terraform destroy` when no Batch jobs are running.
4. **CloudFormation:** `aws cloudformation delete-stack --stack-name kohort-s3-sanitizer` (includes batch role when using current template).

---

## Reference files

| File | Purpose |
|------|---------|
| [iac/terraform/lambda_batch/terraform.tfvars.example](../iac/terraform/lambda_batch/terraform.tfvars.example) | Terraform starter variables |
| [iac/cloudformation/lambda_batch/parameters.json](../iac/cloudformation/lambda_batch/parameters.json) | CloudFormation parameters |
| [iac/cloudformation/lambda_batch/template.yaml](../iac/cloudformation/lambda_batch/template.yaml) | CloudFormation template |
| [scripts/bootstrap-client.sh](../scripts/bootstrap-client.sh) | First-time venv + `client.yaml` bootstrap |
| [iac/cloudformation/image_mirror/template.yaml](../iac/cloudformation/image_mirror/template.yaml) | CodeBuild image mirror (public → private ECR) |
| [iac/codebuild/mirror-image/buildspec.yml](../iac/codebuild/mirror-image/buildspec.yml) | CodeBuild buildspec reference |
| [scripts/client.yaml.example](../scripts/client.yaml.example) | Client config template for automated setup |
| [scripts/kohort_sanitize.py](../scripts/kohort_sanitize.py) | Client driver (`setup`, `run`, `status`) |
| [scripts/requirements.txt](../scripts/requirements.txt) | Python deps for client scripts |
| [scripts/example-batch-manifest.csv](../scripts/example-batch-manifest.csv) | Manifest row format |
| [scripts/generate_batch_manifest.py](../scripts/generate_batch_manifest.py) | Build manifest CSV from an S3 prefix |
| [scripts/create-batch-job.example.sh](../scripts/create-batch-job.example.sh) | Batch job CLI wrapper |
| [scrubber/rules/appsflyer-datalocker.yaml](../scrubber/rules/appsflyer-datalocker.yaml) | AppsFlyer Data Locker ruleset |
| [scrubber/rules/example-ruleset.yaml](../scrubber/rules/example-ruleset.yaml) | Generic starter ruleset for other data |
