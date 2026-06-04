output "lambda_function_name" {
  description = "Scrubber Lambda function name."
  value       = aws_lambda_function.scrubber.function_name
}

output "lambda_function_arn" {
  description = "Scrubber Lambda function ARN (use in S3 Batch job)."
  value       = aws_lambda_function.scrubber.arn
}

output "lambda_role_arn" {
  description = "Lambda execution role ARN."
  value       = aws_iam_role.scrubber.arn
}

output "dest_bucket_name" {
  description = "Sanitized output bucket name."
  value       = local.dest_bucket
}

output "batch_operations_policy_arn" {
  description = "Attach this policy to the IAM role used by S3 Batch Operations."
  value       = aws_iam_policy.batch_operations.arn
}

output "batch_operations_role_arn" {
  description = "IAM role ARN for S3 Batch Operations jobs (when create_batch_operations_role is true)."
  value       = try(aws_iam_role.batch_operations[0].arn, null)
}

output "ops_bucket_name" {
  description = "Bucket used for inventory, manifests, and batch reports."
  value       = local.ops_bucket
}

output "inventory_destination_prefix" {
  description = "Prefix where S3 Inventory manifests are delivered."
  value       = local.inventory_prefix
}

output "inventory_destination_policy_json" {
  description = "Bucket policy document for ops bucket (apply manually if manage_ops_bucket_inventory_policy is false)."
  value       = try(data.aws_iam_policy_document.ops_inventory_destination[0].json, null)
}
