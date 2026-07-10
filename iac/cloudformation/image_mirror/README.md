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
    PublicImage=public.ecr.aws/g9w2z6w5/kohort-s3-sanitizer:<version-tag> \
    EcrRepo=kohort-s3-sanitizer \
    ImageTag=<version-tag> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region eu-west-1

aws codebuild start-build --project-name kohort-s3-sanitizer-image-mirror
```

Use the same `<version-tag>` for `PublicImage` and `ImageTag` so the private image tag matches the published version. Avoid floating tags like `latest`: re-mirroring under the same tag may leave Lambda running a stale image.

## Requirements

- CodeBuild project uses **privileged** mode (Docker-in-Docker).
- No Docker required on the operator laptop.
