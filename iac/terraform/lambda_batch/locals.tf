locals {
  name_prefix = var.name_prefix

  source_prefix = var.source_prefix != "" && !endswith(var.source_prefix, "/") ? "${var.source_prefix}/" : var.source_prefix
  dest_prefix   = var.dest_prefix != "" && !endswith(var.dest_prefix, "/") ? "${var.dest_prefix}/" : var.dest_prefix

  # s3://my-bucket/path/to/ruleset.yaml -> my-bucket
  ruleset_bucket = split("/", trimprefix(var.ruleset_uri, "s3://"))[0]
  ops_bucket     = coalesce(var.ops_bucket_name, local.ruleset_bucket)

  batch_reports_prefix = var.batch_reports_prefix != "" && !endswith(var.batch_reports_prefix, "/") ? "${var.batch_reports_prefix}/" : var.batch_reports_prefix
  manifests_prefix     = var.manifests_prefix != "" && !endswith(var.manifests_prefix, "/") ? "${var.manifests_prefix}/" : var.manifests_prefix

  # Resolved S3 Batch Operations role ARN: the role this module creates, or the
  # caller-supplied override when create_batch_operations_role is false. Used by
  # the schedule/orchestrator, which needs a role ARN regardless of who owns it.
  batch_role_arn = var.create_batch_operations_role ? aws_iam_role.batch_operations[0].arn : var.batch_role_arn_override

  common_tags = merge(var.tags, {
    Project = "kohort-s3-sanitizer"
  })
}
