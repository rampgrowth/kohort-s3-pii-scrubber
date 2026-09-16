variable "ops_bucket_name" {
  description = "Bucket for batch manifests and job reports. Defaults to the ruleset bucket parsed from ruleset_uri."
  type        = string
  default     = null
}

variable "create_batch_operations_role" {
  description = "Create an IAM role for S3 Batch Operations (manifest read, report write, Lambda invoke)."
  type        = bool
  default     = true
}

variable "batch_role_arn_override" {
  description = <<-EOT
    ARN of an existing S3 Batch Operations role to use when create_batch_operations_role
    is false. Required in that case if enable_schedule is also true, since the
    orchestrator Lambda needs a role ARN to pass to s3:CreateJob.
  EOT
  type        = string
  default     = null
}

variable "batch_reports_prefix" {
  description = "Prefix in the ops bucket for S3 Batch job completion reports."
  type        = string
  default     = "batch-reports/"
}

variable "manifests_prefix" {
  description = "Prefix in the ops bucket for optional custom batch manifests."
  type        = string
  default     = "manifests/"
}
