resource "aws_cloudwatch_log_group" "scrubber" {
  name              = "/aws/lambda/${local.name_prefix}-scrubber"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_lambda_function" "scrubber" {
  function_name = "${local.name_prefix}-scrubber"
  role          = aws_iam_role.scrubber.arn
  package_type  = "Image"
  image_uri     = var.lambda_image_uri

  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_seconds

  reserved_concurrent_executions = var.reserved_concurrent_executions >= 0 ? var.reserved_concurrent_executions : null

  environment {
    variables = {
      DEST_BUCKET   = local.dest_bucket
      DEST_PREFIX   = local.dest_prefix
      SOURCE_PREFIX = local.source_prefix
      RULESET_URI   = var.ruleset_uri
    }
  }

  depends_on = [aws_cloudwatch_log_group.scrubber]

  tags = local.common_tags
}

# Allow S3 Batch Operations service to invoke the function.
resource "aws_lambda_permission" "allow_s3_batch" {
  statement_id  = "AllowS3BatchOperations"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scrubber.function_name
  principal     = "s3.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
}
