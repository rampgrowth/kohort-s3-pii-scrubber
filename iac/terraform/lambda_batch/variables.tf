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

variable "enable_schedule" {
  description = "Deploy the daily orchestrator Lambda + EventBridge schedule."
  type        = bool
  default     = false
}

variable "schedule_expression" {
  description = "EventBridge schedule expression for the orchestrator (default daily 06:00 UTC)."
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "schedule_prefixes" {
  description = "Prefixes the orchestrator scrubs each run, relative to source_prefix."
  type        = list(string)
  default     = []
}

variable "orchestrator_memory_mb" {
  description = "Memory for the orchestrator Lambda (listing-heavy, not transform-heavy)."
  type        = number
  default     = 1024
}

variable "orchestrator_timeout_seconds" {
  description = "Timeout for the orchestrator Lambda."
  type        = number
  default     = 900
}
