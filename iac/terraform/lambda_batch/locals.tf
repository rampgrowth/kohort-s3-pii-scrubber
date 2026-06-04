locals {
  name_prefix = var.name_prefix

  source_prefix = var.source_prefix != "" && !endswith(var.source_prefix, "/") ? "${var.source_prefix}/" : var.source_prefix
  dest_prefix   = var.dest_prefix != "" && !endswith(var.dest_prefix, "/") ? "${var.dest_prefix}/" : var.dest_prefix

  # s3://my-bucket/path/to/ruleset.yaml -> my-bucket
  ruleset_bucket = split("/", trimprefix(var.ruleset_uri, "s3://"))[0]
  ops_bucket     = coalesce(var.ops_bucket_name, local.ruleset_bucket)

  batch_reports_prefix = var.batch_reports_prefix != "" && !endswith(var.batch_reports_prefix, "/") ? "${var.batch_reports_prefix}/" : var.batch_reports_prefix
  manifests_prefix     = var.manifests_prefix != "" && !endswith(var.manifests_prefix, "/") ? "${var.manifests_prefix}/" : var.manifests_prefix

  common_tags = merge(var.tags, {
    Project = "kohort-s3-sanitizer"
  })
}
