# Image mirror (CodeBuild)

Copies the Kohort scrubber image from **Amazon ECR Public** into the account **private ECR** so Lambda can use it (Lambda does not accept `public.ecr.aws/...` URIs).

Deployed automatically by `kohort_sanitize.py setup` when `image_publish: codebuild` in `client.yaml`.

## Manual deploy

```bash
aws cloudformation deploy \
  --stack-name kohort-s3-sanitizer-image-mirror \
  --template-file template.yaml \
  --parameter-overrides \
    NamePrefix=kohort-s3-sanitizer \
    PublicImage=public.ecr.aws/g9w2z6w5/kohort-s3-sanitizer:latest \
    EcrRepo=kohort-s3-sanitizer \
    ImageTag=latest \
  --capabilities CAPABILITY_NAMED_IAM \
  --region eu-west-1

aws codebuild start-build --project-name kohort-s3-sanitizer-image-mirror
```

## Requirements

- CodeBuild project uses **privileged** mode (Docker-in-Docker).
- No Docker required on the operator laptop.
