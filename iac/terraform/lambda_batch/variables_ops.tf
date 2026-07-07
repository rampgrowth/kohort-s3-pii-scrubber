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
