variable "ops_bucket_name" {
  description = "Bucket for inventory reports, batch manifests, and job reports. Defaults to the ruleset bucket parsed from ruleset_uri."
  type        = string
  default     = null
}

variable "enable_s3_inventory" {
  description = "Enable daily S3 Inventory on the source prefix, delivered to ops_bucket_name."
  type        = bool
  default     = true
}

variable "inventory_destination_prefix" {
  description = "Prefix in the ops bucket where inventory CSV manifests are written."
  type        = string
  default     = "inventory/raw/"
}

variable "inventory_id" {
  description = "S3 Inventory configuration id on the source bucket."
  type        = string
  default     = null
}

variable "manage_ops_bucket_inventory_policy" {
  description = "If true, apply a bucket policy on the ops bucket allowing S3 Inventory writes from the source bucket. Only enable when no conflicting bucket policy exists."
  type        = bool
  default     = false
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
