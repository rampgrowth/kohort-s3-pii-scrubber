#!/usr/bin/env python3
"""
Client driver for Kohort S3 Sanitizer: one-time setup and per-prefix scrub jobs.

  python3 scripts/kohort_sanitize.py --config client.yaml setup
  python3 scripts/kohort_sanitize.py --config client.yaml setup --terraform
  python3 scripts/kohort_sanitize.py --config client.yaml run --prefix kohort-datalocker/t=installs/dt=2025-09-28/
  python3 scripts/kohort_sanitize.py --config client.yaml status --job-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CFN_TEMPLATE = REPO_ROOT / "iac/cloudformation/lambda_batch/template.yaml"
IMAGE_MIRROR_CFN = REPO_ROOT / "iac/cloudformation/image_mirror/template.yaml"
TERRAFORM_DIR = REPO_ROOT / "iac/terraform/lambda_batch"
SCRIPTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ClientConfig:
    aws_profile: str | None
    region: str
    deploy: str  # cloudformation | terraform
    raw_bucket: str
    source_prefix: str
    dest_bucket: str
    dest_prefix: str
    create_dest_bucket: bool
    config_bucket: str
    ruleset_key: str
    ruleset_local_path: Path
    public_image: str
    ecr_repo: str
    image_tag: str
    image_publish: str  # codebuild | docker | skip
    name_prefix: str
    stack_name: str
    manifests_prefix: str
    batch_reports_prefix: str
    lambda_memory_mb: int
    lambda_timeout_seconds: int
    terraform_dir: Path


def load_client_config(path: Path) -> ClientConfig:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")

    public_image = str(data["public_image"])
    image_tag = str(data.get("image_tag") or public_image.rsplit(":", 1)[-1])

    ruleset_local = data.get("ruleset_local_path")
    if not ruleset_local:
        raise ValueError("ruleset_local_path is required in config (local YAML to upload during setup)")

    local_path = Path(str(ruleset_local))
    if not local_path.is_absolute():
        local_path = (path.parent / local_path).resolve()
        if not local_path.exists():
            local_path = (REPO_ROOT / ruleset_local).resolve()

    deploy = str(data.get("deploy", "cloudformation")).lower()
    if deploy not in ("cloudformation", "terraform"):
        raise ValueError(f"deploy must be cloudformation or terraform, got {deploy!r}")

    image_publish = str(data.get("image_publish", "codebuild")).lower()
    if image_publish not in ("codebuild", "docker", "skip"):
        raise ValueError(f"image_publish must be codebuild, docker, or skip, got {image_publish!r}")

    tf_dir = data.get("terraform_dir", "iac/terraform/lambda_batch")
    terraform_dir = Path(str(tf_dir))
    if not terraform_dir.is_absolute():
        terraform_dir = (REPO_ROOT / terraform_dir).resolve()

    raw_bucket = str(data["raw_bucket"])
    source_prefix = str(data["source_prefix"])
    dest_bucket = str(data.get("dest_bucket") or raw_bucket)
    dest_prefix_raw = data.get("dest_prefix")
    dest_prefix = (
        str(dest_prefix_raw) if dest_prefix_raw is not None else f"sanitized/{source_prefix}"
    )
    if dest_bucket == raw_bucket and not dest_prefix:
        raise ValueError(
            "dest_prefix is required when sanitized output goes to raw_bucket, "
            "otherwise the scrubber would overwrite the source objects. "
            "Set a dest_prefix, or set dest_bucket to a separate bucket."
        )

    separate_dest_bucket = dest_bucket != raw_bucket
    create_dest_bucket = bool(data.get("create_dest_bucket", separate_dest_bucket))
    if not separate_dest_bucket:
        create_dest_bucket = False

    return ClientConfig(
        aws_profile=data.get("aws_profile") or None,
        region=str(data["region"]),
        deploy=deploy,
        raw_bucket=raw_bucket,
        source_prefix=source_prefix,
        dest_bucket=dest_bucket,
        dest_prefix=dest_prefix,
        create_dest_bucket=create_dest_bucket,
        config_bucket=str(data["config_bucket"]),
        ruleset_key=str(data["ruleset_key"]),
        ruleset_local_path=local_path,
        public_image=public_image,
        ecr_repo=str(data.get("ecr_repo", "kohort-s3-sanitizer")),
        image_tag=image_tag,
        image_publish=image_publish,
        name_prefix=str(data.get("name_prefix", "kohort-s3-sanitizer")),
        stack_name=str(data.get("stack_name", data.get("name_prefix", "kohort-s3-sanitizer"))),
        manifests_prefix=_ensure_trailing_slash(str(data.get("manifests_prefix", "ops/manifests/"))),
        batch_reports_prefix=_ensure_trailing_slash(
            str(data.get("batch_reports_prefix", "ops/batch-reports/"))
        ),
        lambda_memory_mb=int(data.get("lambda_memory_mb", 2048)),
        lambda_timeout_seconds=int(data.get("lambda_timeout_seconds", 300)),
        terraform_dir=terraform_dir,
    )


def _ensure_trailing_slash(prefix: str) -> str:
    return prefix if prefix.endswith("/") else f"{prefix}/"


def resolve_run_prefix(cfg: ClientConfig, prefix: str) -> str:
    """Resolve a run prefix against source_prefix.

    Accepts a prefix relative to source_prefix (e.g. "t=installs/dt=2025-09-28/")
    or a full key prefix that already starts with source_prefix.
    """
    src = cfg.source_prefix
    if not prefix or prefix == src or f"{prefix}/" == src:
        return src
    if prefix.startswith(src):
        return prefix
    return f"{src}{prefix.lstrip('/')}"


def slug_from_prefix(prefix: str) -> str:
    slug = prefix.strip("/").replace("/", "-")
    slug = re.sub(r"[^a-zA-Z0-9._=-]+", "-", slug)
    return slug.strip("-") or "manifest"


def _session(cfg: ClientConfig):
    import boto3

    return boto3.Session(profile_name=cfg.aws_profile, region_name=cfg.region)


def _aws_env(cfg: ClientConfig) -> dict[str, str]:
    import os

    env = os.environ.copy()
    if cfg.aws_profile:
        env["AWS_PROFILE"] = cfg.aws_profile
    env["AWS_REGION"] = cfg.region
    env["AWS_DEFAULT_REGION"] = cfg.region
    return env


def _run(cmd: list[str], cfg: ClientConfig, *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, env=_aws_env(cfg), check=check, text=True, capture_output=True)


def account_id(cfg: ClientConfig) -> str:
    return _session(cfg).client("sts").get_caller_identity()["Account"]


def lambda_image_uri(cfg: ClientConfig) -> str:
    acct = account_id(cfg)
    return f"{acct}.dkr.ecr.{cfg.region}.amazonaws.com/{cfg.ecr_repo}:{cfg.image_tag}"


def ruleset_uri(cfg: ClientConfig) -> str:
    return f"s3://{cfg.config_bucket}/{cfg.ruleset_key}"


def stack_output(cfg: ClientConfig, key: str) -> str:
    cfn = _session(cfg).client("cloudformation")
    response = cfn.describe_stacks(StackName=cfg.stack_name)
    outputs = response["Stacks"][0].get("Outputs") or []
    for item in outputs:
        if item["OutputKey"] == key:
            return item["OutputValue"]
    raise KeyError(f"Stack output {key!r} not found on stack {cfg.stack_name!r}")


def terraform_output(cfg: ClientConfig, name: str) -> str:
    if not cfg.terraform_dir.exists():
        raise FileNotFoundError(f"Terraform directory not found: {cfg.terraform_dir}")
    result = _run(
        ["terraform", f"-chdir={cfg.terraform_dir}", "output", "-raw", name],
        cfg,
    )
    value = result.stdout.strip()
    if not value or value == "null":
        raise KeyError(f"Terraform output {name!r} is empty (run setup with deploy: terraform first)")
    return value


def get_lambda_arn(cfg: ClientConfig) -> str:
    if cfg.deploy == "terraform":
        return terraform_output(cfg, "lambda_function_arn")
    return stack_output(cfg, "LambdaFunctionArn")


def get_batch_role_arn(cfg: ClientConfig) -> str:
    if cfg.deploy == "terraform":
        return terraform_output(cfg, "batch_operations_role_arn")
    return stack_output(cfg, "BatchOperationsRoleArn")


def image_mirror_stack_name(cfg: ClientConfig) -> str:
    return f"{cfg.name_prefix}-image-mirror"


def _ecr_repo_exists(cfg: ClientConfig) -> bool:
    from botocore.exceptions import ClientError

    ecr = _session(cfg).client("ecr")
    try:
        ecr.describe_repositories(repositoryNames=[cfg.ecr_repo])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "RepositoryNotFoundException":
            return False
        raise
    return True


def _image_in_private_ecr(cfg: ClientConfig) -> bool:
    from botocore.exceptions import ClientError

    ecr = _session(cfg).client("ecr")
    try:
        ecr.describe_images(repositoryName=cfg.ecr_repo, imageIds=[{"imageTag": cfg.image_tag}])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in (
            "ImageNotFoundException",
            "RepositoryNotFoundException",
        ):
            return False
        raise
    return True


def cmd_deploy_image_mirror_stack(cfg: ClientConfig) -> str:
    """Deploy CodeBuild + ECR stack for mirroring the public scrubber image."""
    if not IMAGE_MIRROR_CFN.exists():
        raise FileNotFoundError(f"Image mirror template not found: {IMAGE_MIRROR_CFN}")

    stack = image_mirror_stack_name(cfg)
    remove_stuck_cfn_stack(cfg, stack_name=stack)

    create_repo = "true"
    if _ecr_repo_exists(cfg) and not stack_resource_ready(cfg, "EcrRepository", stack_name=stack):
        print(f"ECR repository {cfg.ecr_repo!r} already exists; reusing it.")
        create_repo = "false"

    params = {
        "NamePrefix": cfg.name_prefix,
        "PublicImage": cfg.public_image,
        "EcrRepo": cfg.ecr_repo,
        "ImageTag": cfg.image_tag,
        "CreateEcrRepo": create_repo,
    }
    param_file = Path("/tmp/kohort-image-mirror-cfn-params.json")
    param_file.write_text(
        json.dumps([{"ParameterKey": k, "ParameterValue": v} for k, v in params.items()]),
        encoding="utf-8",
    )

    print(f"Deploying image mirror stack: {stack}")
    result = _run(
        [
            "aws",
            "cloudformation",
            "deploy",
            "--stack-name",
            stack,
            "--template-file",
            str(IMAGE_MIRROR_CFN),
            "--parameter-overrides",
            f"file://{param_file}",
            "--capabilities",
            "CAPABILITY_NAMED_IAM",
            "--no-fail-on-empty-changeset",
            "--region",
            cfg.region,
        ],
        cfg,
        check=False,
    )
    if result.returncode != 0:
        output = result.stderr or result.stdout
        print(output, file=sys.stderr)
        if "ResourceExistenceCheck" in output or "EarlyValidation" in output:
            print(
                "\nA resource this stack creates already exists outside it. Check for:\n"
                f"  - IAM role:          {cfg.name_prefix}-image-mirror-codebuild\n"
                f"  - CodeBuild project: {cfg.name_prefix}-image-mirror\n"
                "Delete the conflicting resource, or set a unique name_prefix in client.yaml.",
                file=sys.stderr,
            )
        raise RuntimeError(f"Image mirror stack deploy failed (exit {result.returncode})")

    return f"{cfg.name_prefix}-image-mirror"


def cmd_run_codebuild_mirror(cfg: ClientConfig, project_name: str) -> None:
    """Start CodeBuild image mirror and wait until SUCCEEDED."""
    codebuild = _session(cfg).client("codebuild")

    print(f"Starting CodeBuild project: {project_name}")
    build = codebuild.start_build(projectName=project_name)
    build_id = build["build"]["id"]
    print(f"Build id: {build_id}")

    while True:
        detail = codebuild.batch_get_builds(ids=[build_id])["builds"][0]
        status = detail.get("buildStatus")
        phase = detail.get("currentPhase", "")
        print(f"  status={status} phase={phase}")
        if status == "SUCCEEDED":
            return
        if status in ("FAILED", "FAULT", "STOPPED", "TIMED_OUT"):
            logs = detail.get("logs", {}).get("deepLink", "")
            raise RuntimeError(f"CodeBuild image mirror failed: {status}. Logs: {logs}")
        time.sleep(15)


def publish_image(cfg: ClientConfig, *, force_skip: bool = False) -> str:
    """Mirror public image to private ECR; return Lambda image URI."""
    uri = lambda_image_uri(cfg)
    if force_skip or cfg.image_publish == "skip":
        print(f"Skipping image publish; using {uri}")
        return uri
    if _image_in_private_ecr(cfg):
        print(f"Image already in private ECR; skipping mirror: {uri}")
        return uri
    if cfg.image_publish == "codebuild":
        project = cmd_deploy_image_mirror_stack(cfg)
        cmd_run_codebuild_mirror(cfg, project)
        print(f"Lambda image: {uri}")
        return uri
    return cmd_mirror_image(cfg)


def cmd_mirror_image(cfg: ClientConfig) -> str:
    uri = lambda_image_uri(cfg)
    registry = f"{account_id(cfg)}.dkr.ecr.{cfg.region}.amazonaws.com"

    steps: list[tuple[str, list[str]]] = [
        (
            "private ECR login",
            [
                "sh",
                "-c",
                f"aws ecr get-login-password --region {cfg.region} | "
                f"docker login --username AWS --password-stdin {registry}",
            ],
        ),
        (
            "create repository",
            [
                "aws",
                "ecr",
                "describe-repositories",
                "--region",
                cfg.region,
                "--repository-names",
                cfg.ecr_repo,
            ],
        ),
        ("pull public image", ["docker", "pull", cfg.public_image]),
        ("tag image", ["docker", "tag", cfg.public_image, uri]),
        ("push image", ["docker", "push", uri]),
    ]

    for label, cmd in steps:
        if label == "create repository":
            result = _run(cmd, cfg, check=False)
            if result.returncode != 0:
                _run(
                    ["aws", "ecr", "create-repository", "--region", cfg.region, "--repository-name", cfg.ecr_repo],
                    cfg,
                )
            continue
        print(f"  {label}...")
        result = _run(cmd, cfg, check=False)
        if result.returncode != 0:
            print(result.stderr or result.stdout, file=sys.stderr)
            raise RuntimeError(f"{label} failed (exit {result.returncode})")

    print(f"Lambda image: {uri}")
    return uri


def _bucket_exists(s3: Any, bucket: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code", "") in ("404", "NoSuchBucket", "NotFound"):
            return False
        raise
    return True


def _ensure_bucket(cfg: ClientConfig, s3: Any, bucket: str, *, label: str) -> None:
    if _bucket_exists(s3, bucket):
        print(f"{label} exists: {bucket}")
    else:
        print(f"Creating {label.lower()}: {bucket}")
        params: dict[str, Any] = {"Bucket": bucket}
        if cfg.region != "us-east-1":
            params["CreateBucketConfiguration"] = {"LocationConstraint": cfg.region}
        s3.create_bucket(**params)

    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )


def cmd_bootstrap_config(cfg: ClientConfig) -> None:
    s3 = _session(cfg).client("s3")

    _ensure_bucket(cfg, s3, cfg.config_bucket, label="Config bucket")

    if cfg.dest_bucket != cfg.raw_bucket:
        if cfg.create_dest_bucket:
            _ensure_bucket(cfg, s3, cfg.dest_bucket, label="Sanitized bucket")
        elif not _bucket_exists(s3, cfg.dest_bucket):
            raise RuntimeError(
                f"Sanitized bucket does not exist: {cfg.dest_bucket}. "
                "Create it first, or set create_dest_bucket: true in your config."
            )

    if not cfg.ruleset_local_path.exists():
        raise FileNotFoundError(f"Ruleset file not found: {cfg.ruleset_local_path}")

    print(f"Uploading ruleset → s3://{cfg.config_bucket}/{cfg.ruleset_key}")
    s3.upload_file(str(cfg.ruleset_local_path), cfg.config_bucket, cfg.ruleset_key)


def batch_role_name(cfg: ClientConfig) -> str:
    return f"{cfg.name_prefix}-batch-role"


def scrubber_function_name(cfg: ClientConfig) -> str:
    return f"{cfg.name_prefix}-scrubber"


def scrubber_log_group_name(cfg: ClientConfig) -> str:
    return f"/aws/lambda/{scrubber_function_name(cfg)}"


def batch_invoke_policy_name(cfg: ClientConfig) -> str:
    return f"{cfg.name_prefix}-batch-invoke"


_CFN_READY_STATUSES = frozenset({"CREATE_COMPLETE", "UPDATE_COMPLETE"})


def stack_resource_ready(cfg: ClientConfig, logical_id: str, *, stack_name: str | None = None) -> bool:
    """True when the stack already owns a resource in a stable state."""
    cfn = _session(cfg).client("cloudformation")
    try:
        resources = cfn.describe_stack_resources(StackName=stack_name or cfg.stack_name)["StackResources"]
    except cfn.exceptions.ClientError:
        return False
    for resource in resources:
        if resource.get("LogicalResourceId") == logical_id:
            return resource.get("ResourceStatus") in _CFN_READY_STATUSES
    return False


def stack_manages_batch_role(cfg: ClientConfig) -> bool:
    return stack_resource_ready(cfg, "BatchOperationsRole")


def _delete_iam_role(iam: Any, role_name: str) -> None:
    from botocore.exceptions import ClientError

    try:
        iam.get_role(RoleName=role_name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "NoSuchEntity":
            return
        raise

    print(f"Removing pre-existing IAM role {role_name!r} so CloudFormation can create it...")
    for policy in iam.list_attached_role_policies(RoleName=role_name).get("AttachedPolicies", []):
        iam.detach_role_policy(RoleName=role_name, PolicyArn=policy["PolicyArn"])
    for policy_name in iam.list_role_policies(RoleName=role_name).get("PolicyNames", []):
        iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
    iam.delete_role(RoleName=role_name)
    print(f"Deleted role: {role_name}")


def _delete_managed_policy_by_name(iam: Any, policy_name: str) -> None:
    from botocore.exceptions import ClientError

    for policy in iam.list_policies(Scope="Local").get("Policies", []):
        if policy.get("PolicyName") != policy_name:
            continue
        arn = policy["Arn"]
        for role in iam.list_entities_for_policy(PolicyArn=arn, EntityFilter="Role").get(
            "PolicyRoles", []
        ):
            iam.detach_role_policy(RoleName=role["RoleName"], PolicyArn=arn)
        print(f"Removing pre-existing IAM policy {policy_name!r} so CloudFormation can create it...")
        iam.delete_policy(PolicyArn=arn)
        print(f"Deleted policy: {policy_name}")
        return


def remove_stuck_cfn_stack(cfg: ClientConfig, *, stack_name: str | None = None) -> None:
    """Delete stacks left in non-deployable states after a failed changeset."""
    from botocore.exceptions import ClientError

    name = stack_name or cfg.stack_name
    cfn = _session(cfg).client("cloudformation")
    try:
        stack = cfn.describe_stacks(StackName=name)["Stacks"][0]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ValidationError":
            return
        raise

    status = stack["StackStatus"]
    if status not in (
        "REVIEW_IN_PROGRESS",
        "ROLLBACK_COMPLETE",
        "CREATE_FAILED",
        "ROLLBACK_FAILED",
        "DELETE_FAILED",
    ):
        return

    print(f"Deleting CloudFormation stack {name!r} (status={status}) before redeploy...")
    cfn.delete_stack(StackName=name)
    waiter = cfn.get_waiter("stack_delete_complete")
    waiter.wait(StackName=name)
    print(f"Deleted stack: {name}")


def remove_orphan_cfn_resources(cfg: ClientConfig) -> None:
    """Delete leftover Terraform/manual resources that block CFN named-resource creation."""
    from botocore.exceptions import ClientError

    lam = _session(cfg).client("lambda")
    logs = _session(cfg).client("logs")
    iam = _session(cfg).client("iam")

    fn = scrubber_function_name(cfg)
    if not stack_resource_ready(cfg, "ScrubberFunction"):
        try:
            lam.delete_function(FunctionName=fn)
            print(f"Deleted Lambda function: {fn}")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                raise

    if not stack_resource_ready(cfg, "ScrubberLogGroup"):
        try:
            logs.delete_log_group(logGroupName=scrubber_log_group_name(cfg))
            print(f"Deleted log group: {scrubber_log_group_name(cfg)}")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                raise

    if not stack_resource_ready(cfg, "ScrubberRole"):
        _delete_iam_role(iam, fn)

    if not stack_resource_ready(cfg, "BatchOperationsRole"):
        _delete_iam_role(iam, batch_role_name(cfg))

    if not stack_resource_ready(cfg, "BatchInvokePolicy"):
        _delete_managed_policy_by_name(iam, batch_invoke_policy_name(cfg))


def remove_unmanaged_batch_role(cfg: ClientConfig) -> None:
    """Delete a manually created batch role so CloudFormation can own it."""
    if stack_manages_batch_role(cfg):
        return
    _delete_iam_role(_session(cfg).client("iam"), batch_role_name(cfg))


def cmd_deploy_stack(cfg: ClientConfig, image_uri: str) -> None:
    if not CFN_TEMPLATE.exists():
        raise FileNotFoundError(f"CloudFormation template not found: {CFN_TEMPLATE}")

    remove_stuck_cfn_stack(cfg)
    remove_orphan_cfn_resources(cfg)

    params = {
        "NamePrefix": cfg.name_prefix,
        "SourceBucketName": cfg.raw_bucket,
        "SourcePrefix": cfg.source_prefix,
        "DestBucketName": cfg.dest_bucket,
        "CreateDestBucket": "false",
        "DestPrefix": cfg.dest_prefix,
        "RulesetBucketName": cfg.config_bucket,
        "RulesetObjectKey": cfg.ruleset_key,
        "LambdaImageUri": image_uri,
        "LambdaMemoryMb": str(cfg.lambda_memory_mb),
        "LambdaTimeoutSeconds": str(cfg.lambda_timeout_seconds),
        "ManifestsPrefix": cfg.manifests_prefix,
        "BatchReportsPrefix": cfg.batch_reports_prefix,
    }

    param_file = Path("/tmp/kohort-sanitize-cfn-params.json")
    param_file.write_text(
        json.dumps([{"ParameterKey": k, "ParameterValue": v} for k, v in params.items()]),
        encoding="utf-8",
    )

    print(f"Deploying CloudFormation stack: {cfg.stack_name}")
    result = _run(
        [
            "aws",
            "cloudformation",
            "deploy",
            "--stack-name",
            cfg.stack_name,
            "--template-file",
            str(CFN_TEMPLATE),
            "--parameter-overrides",
            f"file://{param_file}",
            "--capabilities",
            "CAPABILITY_NAMED_IAM",
            "--no-fail-on-empty-changeset",
            "--region",
            cfg.region,
        ],
        cfg,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        raise RuntimeError(f"CloudFormation deploy failed (exit {result.returncode})")

    print(f"Lambda ARN: {get_lambda_arn(cfg)}")
    print(f"Batch role ARN: {get_batch_role_arn(cfg)}")


def render_tfvars(cfg: ClientConfig, image_uri: str) -> str:
    return "\n".join(
        [
            "# Generated by kohort_sanitize.py — edit client.yaml and re-run setup.",
            "",
            f"name_prefix        = {json.dumps(cfg.name_prefix)}",
            f"source_bucket_name = {json.dumps(cfg.raw_bucket)}",
            f"source_prefix      = {json.dumps(cfg.source_prefix)}",
            "",
            f"dest_bucket_name   = {json.dumps(cfg.dest_bucket)}",
            f"create_dest_bucket = false",
            f"dest_prefix        = {json.dumps(cfg.dest_prefix)}",
            "",
            f"ruleset_uri      = {json.dumps(ruleset_uri(cfg))}",
            f"lambda_image_uri = {json.dumps(image_uri)}",
            "",
            f"ops_bucket_name              = {json.dumps(cfg.config_bucket)}",
            f"manifests_prefix             = {json.dumps(cfg.manifests_prefix)}",
            f"batch_reports_prefix         = {json.dumps(cfg.batch_reports_prefix)}",
            f"create_batch_operations_role = true",
            "",
            f"lambda_memory_mb       = {cfg.lambda_memory_mb}",
            f"lambda_timeout_seconds = {cfg.lambda_timeout_seconds}",
            "",
        ]
    )


def cmd_deploy_terraform(cfg: ClientConfig, image_uri: str) -> None:
    if not cfg.terraform_dir.exists():
        raise FileNotFoundError(f"Terraform module not found: {cfg.terraform_dir}")

    tfvars_path = cfg.terraform_dir / "terraform.tfvars"
    tfvars_path.write_text(render_tfvars(cfg, image_uri), encoding="utf-8")
    print(f"Wrote {tfvars_path}")

    print(f"Running terraform init in {cfg.terraform_dir}")
    init = _run(
        ["terraform", f"-chdir={cfg.terraform_dir}", "init", "-input=false"],
        cfg,
        check=False,
    )
    if init.returncode != 0:
        print(init.stderr or init.stdout, file=sys.stderr)
        raise RuntimeError(f"terraform init failed (exit {init.returncode})")

    print("Running terraform apply")
    apply = _run(
        [
            "terraform",
            f"-chdir={cfg.terraform_dir}",
            "apply",
            "-auto-approve",
            "-input=false",
        ],
        cfg,
        check=False,
    )
    if apply.returncode != 0:
        print(apply.stderr or apply.stdout, file=sys.stderr)
        raise RuntimeError(f"terraform apply failed (exit {apply.returncode})")

    print(f"Lambda ARN: {get_lambda_arn(cfg)}")
    print(f"Batch role ARN: {get_batch_role_arn(cfg)}")


def cmd_deploy_infra(cfg: ClientConfig, image_uri: str) -> None:
    if cfg.deploy == "terraform":
        cmd_deploy_terraform(cfg, image_uri)
    else:
        cmd_deploy_stack(cfg, image_uri)


def cmd_setup(
    cfg: ClientConfig,
    *,
    skip_image: bool,
    deploy: str | None = None,
    image_publish: str | None = None,
) -> None:
    if deploy:
        cfg = replace(cfg, deploy=deploy)
    if image_publish:
        cfg = replace(cfg, image_publish=image_publish)
    if skip_image:
        cfg = replace(cfg, image_publish="skip")

    print(f"=== Kohort S3 Sanitizer setup ({cfg.deploy}, image={cfg.image_publish}) ===")
    print(f"Source:    s3://{cfg.raw_bucket}/{cfg.source_prefix}")
    print(f"Sanitized: s3://{cfg.dest_bucket}/{cfg.dest_prefix}")
    image_uri = publish_image(cfg)
    cmd_bootstrap_config(cfg)
    cmd_deploy_infra(cfg, image_uri)
    print("Setup complete.")


def create_batch_job(cfg: ClientConfig, manifest_key: str) -> str:
    s3 = _session(cfg).client("s3")
    s3control = _session(cfg).client("s3control")
    acct = account_id(cfg)

    lambda_arn = get_lambda_arn(cfg)
    batch_role_arn = get_batch_role_arn(cfg)

    etag = s3.head_object(Bucket=cfg.config_bucket, Key=manifest_key)["ETag"].strip('"')

    manifest = {
        "Spec": {"Format": "S3BatchOperations_CSV_20180820", "Fields": ["Bucket", "Key"]},
        "Location": {
            "ObjectArn": f"arn:aws:s3:::{cfg.config_bucket}/{manifest_key}",
            "ETag": etag,
        },
    }
    report = {
        "Bucket": f"arn:aws:s3:::{cfg.config_bucket}",
        "Prefix": cfg.batch_reports_prefix,
        "Format": "Report_CSV_20180820",
        "Enabled": True,
        "ReportScope": "AllTasks",
    }
    operation = {"LambdaInvoke": {"FunctionArn": lambda_arn}}

    response = s3control.create_job(
        AccountId=acct,
        ConfirmationRequired=False,
        Priority=10,
        RoleArn=batch_role_arn,
        Operation=operation,
        Manifest=manifest,
        Report=report,
        ClientRequestToken=f"scrub-{int(time.time())}",
    )
    return response["JobId"]


def cmd_run(cfg: ClientConfig, prefix: str, *, dry_run: bool, config_path: Path | None = None) -> None:
    import os

    if cfg.aws_profile:
        os.environ["AWS_PROFILE"] = cfg.aws_profile

    sys.path.insert(0, str(SCRIPTS_DIR))
    from generate_batch_manifest import main as generate_main

    prefix = resolve_run_prefix(cfg, prefix)
    manifest_key = f"{cfg.manifests_prefix}{slug_from_prefix(prefix)}.csv"
    output_uri = f"s3://{cfg.config_bucket}/{manifest_key}"

    print(f"Prefix: {prefix}")
    print(f"Manifest: {output_uri}")

    gen_args = [
        "--bucket",
        cfg.raw_bucket,
        "--prefix",
        prefix,
        "--ruleset",
        ruleset_uri(cfg),
        "--output",
        output_uri,
        "--region",
        cfg.region,
    ]
    if dry_run:
        gen_args.append("--dry-run")
        raise SystemExit(generate_main(gen_args))

    code = generate_main(gen_args)
    if code != 0:
        raise SystemExit(code)

    job_id = create_batch_job(cfg, manifest_key)
    config_arg = config_path.name if config_path else "<config>"
    print(f"Batch job created: {job_id}")
    print(
        f"Monitor: python3 scripts/kohort_sanitize.py --config {config_arg} "
        f"status --job-id {job_id} --watch"
    )


def cmd_status(cfg: ClientConfig, job_id: str, *, watch: bool) -> None:
    s3control = _session(cfg).client("s3control")
    acct = account_id(cfg)

    while True:
        job = s3control.describe_job(AccountId=acct, JobId=job_id)["Job"]
        progress = job.get("ProgressSummary") or {}
        print(
            f"Status={job.get('Status')} "
            f"Total={progress.get('TotalNumberOfTasks', '?')} "
            f"Succeeded={progress.get('NumberOfTasksSucceeded', '?')} "
            f"Failed={progress.get('NumberOfTasksFailed', '?')}"
        )
        status = job.get("Status")
        if not watch or status in ("Complete", "Failed", "Cancelled"):
            if status == "Complete":
                print(f"Reports: s3://{cfg.config_bucket}/{cfg.batch_reports_prefix}")
            break
        time.sleep(15)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kohort S3 Sanitizer client driver.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("client.yaml"),
        help="Path to client YAML config (default: ./client.yaml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="Publish image, bootstrap config bucket, deploy infrastructure.")
    setup.add_argument(
        "--skip-image",
        action="store_true",
        help="Skip image publish (image already in your ECR). Same as image_publish: skip.",
    )
    setup.add_argument(
        "--codebuild-image",
        action="store_const",
        const="codebuild",
        dest="image_publish",
        help="Publish image via CodeBuild in AWS (no local Docker).",
    )
    setup.add_argument(
        "--docker-image",
        action="store_const",
        const="docker",
        dest="image_publish",
        help="Publish image via local Docker pull/push.",
    )
    setup.add_argument(
        "--terraform",
        action="store_const",
        const="terraform",
        dest="deploy",
        help="Deploy with Terraform (overrides deploy in client.yaml).",
    )
    setup.add_argument(
        "--cloudformation",
        action="store_const",
        const="cloudformation",
        dest="deploy",
        help="Deploy with CloudFormation (overrides deploy in client.yaml).",
    )

    run = sub.add_parser("run", help="Generate prefix manifest and start an S3 Batch scrub job.")
    run.add_argument(
        "--prefix",
        required=True,
        help=(
            "Prefix to scrub, relative to source_prefix in client.yaml "
            "(e.g. t=installs/dt=2025-09-28/). A full key prefix starting with "
            "source_prefix also works."
        ),
    )
    run.add_argument("--dry-run", action="store_true", help="List matching keys only; do not run Batch job.")

    status = sub.add_parser("status", help="Show S3 Batch job status.")
    status.add_argument("--job-id", required=True)
    status.add_argument("--watch", action="store_true", help="Poll every 15s until terminal state.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config if args.config.is_absolute() else Path.cwd() / args.config
    if not config_path.exists():
        print(
            f"Config not found: {config_path}\n"
            f"Copy scripts/client.yaml.example to client.yaml and edit.",
            file=sys.stderr,
        )
        return 1

    cfg = load_client_config(config_path)

    if args.command == "setup":
        cmd_setup(
            cfg,
            skip_image=args.skip_image,
            deploy=getattr(args, "deploy", None),
            image_publish=getattr(args, "image_publish", None),
        )
        return 0
    if args.command == "run":
        cmd_run(cfg, args.prefix, dry_run=args.dry_run, config_path=config_path)
        return 0
    if args.command == "status":
        cmd_status(cfg, args.job_id, watch=args.watch)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
