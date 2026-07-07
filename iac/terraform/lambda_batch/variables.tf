variable "name_prefix" {
  description = "Prefix for resource names (e.g. kohort-s3-sanitizer)."
  type        = string
}

variable "source_bucket_name" {
  description = "S3 bucket containing raw objects."
  type        = string
}

variable "source_prefix" {
  description = "Prefix within the source bucket (e.g. raw/). Used for IAM scoping and key mapping."
  type        = string
  default     = ""
}

variable "dest_bucket_name" {
  description = "S3 bucket for sanitized output. Created when create_dest_bucket is true."
  type        = string
}

variable "create_dest_bucket" {
  description = "Whether to create the destination bucket."
  type        = bool
  default     = true
}

variable "dest_prefix" {
  description = "Prefix prepended to mapped destination keys (e.g. sanitized/)."
  type        = string
  default     = ""
}

variable "ruleset_uri" {
  description = "S3 URI to the ruleset YAML/JSON (s3://bucket/key)."
  type        = string
}

variable "lambda_image_uri" {
  description = "ECR image URI for the scrubber Lambda (including tag)."
  type        = string
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB."
  type        = number
  default     = 1024
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 60
}

variable "reserved_concurrent_executions" {
  description = "Optional reserved concurrency cap (-1 to omit)."
  type        = number
  default     = -1
}

variable "kms_key_arn" {
  description = "Optional KMS key ARN for SSE-KMS on destination bucket."
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the Lambda function."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags applied to created resources."
  type        = map(string)
  default     = {}
}
