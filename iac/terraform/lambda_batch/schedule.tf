# Optional daily orchestrator: EventBridge schedule -> orchestrator Lambda that
# runs the incremental `run` path (list -> manifest -> S3 Batch job) per prefix.
# Reuses the scrubber container image with the orchestrator entrypoint command.

resource "aws_cloudwatch_log_group" "orchestrator" {
  count             = var.enable_schedule ? 1 : 0
  name              = "/aws/lambda/${local.name_prefix}-orchestrator"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

data "aws_iam_policy_document" "orchestrator" {
  count = var.enable_schedule ? 1 : 0

  statement {
    sid     = "ListSource"
    effect  = "Allow"
    actions = ["s3:ListBucket"]
    resources = [
      "arn:aws:s3:::${var.source_bucket_name}",
    ]
  }

  statement {
    sid     = "ListDest"
    effect  = "Allow"
    actions = ["s3:ListBucket"]
    resources = [
      "arn:aws:s3:::${local.dest_bucket}",
    ]
  }

  statement {
    sid     = "ReadRuleset"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      replace(var.ruleset_uri, "s3://", "arn:aws:s3:::"),
    ]
  }

  statement {
    sid    = "WriteAndReadManifests"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = [
      "arn:aws:s3:::${local.ops_bucket}/${local.manifests_prefix}*",
    ]
  }

  statement {
    sid       = "CreateBatchJob"
    effect    = "Allow"
    actions   = ["s3:CreateJob"]
    resources = ["*"]
  }

  statement {
    sid       = "PassBatchRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.batch_operations[0].arn]
  }
}

resource "aws_iam_role" "orchestrator" {
  count              = var.enable_schedule ? 1 : 0
  name               = "${local.name_prefix}-orchestrator"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "orchestrator" {
  count  = var.enable_schedule ? 1 : 0
  name   = "${local.name_prefix}-orchestrator"
  role   = aws_iam_role.orchestrator[0].id
  policy = data.aws_iam_policy_document.orchestrator[0].json
}

resource "aws_iam_role_policy_attachment" "orchestrator_basic" {
  count      = var.enable_schedule ? 1 : 0
  role       = aws_iam_role.orchestrator[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "orchestrator" {
  count         = var.enable_schedule ? 1 : 0
  function_name = "${local.name_prefix}-orchestrator"
  role          = aws_iam_role.orchestrator[0].arn
  package_type  = "Image"
  image_uri     = var.lambda_image_uri

  image_config {
    command = ["orchestrator.lambda_handler"]
  }

  memory_size = var.orchestrator_memory_mb
  timeout     = var.orchestrator_timeout_seconds

  environment {
    variables = {
      RAW_BUCKET            = var.source_bucket_name
      SOURCE_PREFIX         = local.source_prefix
      DEST_BUCKET           = local.dest_bucket
      DEST_PREFIX           = local.dest_prefix
      RULESET_URI           = var.ruleset_uri
      CONFIG_BUCKET         = local.ops_bucket
      MANIFESTS_PREFIX      = local.manifests_prefix
      BATCH_REPORTS_PREFIX  = local.batch_reports_prefix
      BATCH_ROLE_ARN        = aws_iam_role.batch_operations[0].arn
      SCRUBBER_FUNCTION_ARN = aws_lambda_function.scrubber.arn
      SCHEDULE_PREFIXES     = jsonencode(var.schedule_prefixes)
    }
  }

  depends_on = [aws_cloudwatch_log_group.orchestrator]
  tags       = local.common_tags
}

resource "aws_cloudwatch_event_rule" "schedule" {
  count               = var.enable_schedule ? 1 : 0
  name                = "${local.name_prefix}-schedule"
  description         = "Daily trigger for the Kohort S3 Sanitizer orchestrator."
  schedule_expression = var.schedule_expression
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "orchestrator" {
  count     = var.enable_schedule ? 1 : 0
  rule      = aws_cloudwatch_event_rule.schedule[0].name
  target_id = "orchestrator"
  arn       = aws_lambda_function.orchestrator[0].arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  count         = var.enable_schedule ? 1 : 0
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orchestrator[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}
