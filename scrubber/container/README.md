# Lambda scrubber container

Clients should not be required to build this image.

Kohort will publish a **public image** that clients can **pull and push into their own ECR**, then point Terraform/CloudFormation at the resulting image URI.

## Use the public image (recommended)

Lambda uses an ECR image URI. The simplest workflow is:

- Pull Kohort public image
- Push to your ECR (same account/region as the Lambda)
- Use that URI in IaC

```bash
export AWS_ACCOUNT_ID="<account-id>"
export AWS_REGION="<region>"

# Kohort-provided public image (pin the tag)
export PUBLIC_IMAGE="public.ecr.aws/kohort/kohort-s3-sanitizer:<version-tag>"

# Your destination ECR repo
export ECR_REPO="kohort-s3-sanitizer"
export IMAGE_TAG="<version-tag>"
export DEST_IMAGE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$ECR_REPO" >/dev/null 2>&1 \
  || aws ecr create-repository --region "$AWS_REGION" --repository-name "$ECR_REPO" >/dev/null

docker pull "$PUBLIC_IMAGE"
docker tag "$PUBLIC_IMAGE" "$DEST_IMAGE"
docker push "$DEST_IMAGE"
```

Use `DEST_IMAGE` in Terraform `lambda_image_uri` or CloudFormation `LambdaImageUri`.

## Build locally (only if you really need to)

Lambda runs **linux/amd64**. On Apple Silicon, build with `buildx` so PyArrow and other native wheels match Lambda's architecture:

```bash
export AWS_ACCOUNT_ID=<account-id>
export AWS_REGION=<region>
export IMAGE_TAG=$(date +%Y%m%d%H%M%S)

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker buildx build --platform linux/amd64 \
  -t "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/kohort-s3-sanitizer:${IMAGE_TAG}" \
  --push scrubber/container
```

Use that full URI (including tag) in Terraform `lambda_image_uri`. Prefer a **unique tag per deploy** so Lambda picks up the new image; reusing `:latest` alone may not refresh the function.

## Local smoke test

Set env vars and invoke the handler with a sample S3 Batch event JSON (see [AWS S3 Batch + Lambda invoke](https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops-invoke-lambda.html)).

```bash
docker run --rm --entrypoint python \
  -e DEST_BUCKET=my-dest \
  -e RULESET_URI=s3://my-config/ruleset.yaml \
  -e SOURCE_PREFIX=raw/ \
  -e DEST_PREFIX=sanitized/ \
  "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/kohort-s3-sanitizer:${IMAGE_TAG}" \
  -c "import handler; print(handler.lambda_handler)"
```

## Unit tests

```bash
cd scrubber/container
python3 -m pytest tests/ -q
```

## Environment variables

| Variable | Required |
|----------|----------|
| `DEST_BUCKET` | yes |
| `RULESET_URI` | yes (`s3://...`) |
| `DEST_PREFIX` | no |
| `SOURCE_PREFIX` | no |
