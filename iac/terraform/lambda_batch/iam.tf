data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  source_bucket_arn = "arn:aws:s3:::${var.source_bucket_name}"
  dest_bucket = var.create_dest_bucket ? aws_s3_bucket.dest[0].id : var.dest_bucket_name
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scrubber" {
  name               = "${local.name_prefix}-scrubber"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "scrubber" {
  statement {
    sid    = "ReadSource"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket",
    ]
    resources = [
      local.source_bucket_arn,
      "${local.source_bucket_arn}/${local.source_prefix}*",
    ]
  }

  statement {
    sid    = "WriteDest"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:PutObjectAcl",
    ]
    resources = [
      "arn:aws:s3:::${local.dest_bucket}/${local.dest_prefix}*",
    ]
  }

  statement {
    sid    = "ReadRuleset"
    effect = "Allow"
    actions = [
      "s3:GetObject",
    ]
    resources = [
      replace(var.ruleset_uri, "s3://", "arn:aws:s3:::"),
    ]
  }

  dynamic "statement" {
    for_each = var.kms_key_arn != null ? [1] : []
    content {
      sid    = "KMS"
      effect = "Allow"
      actions = [
        "kms:Decrypt",
        "kms:Encrypt",
        "kms:GenerateDataKey",
      ]
      resources = [var.kms_key_arn]
    }
  }
}

resource "aws_iam_role_policy" "scrubber" {
  name   = "${local.name_prefix}-scrubber"
  role   = aws_iam_role.scrubber.id
  policy = data.aws_iam_policy_document.scrubber.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.scrubber.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# S3 Batch Operations invokes Lambda; clients attach this policy to the Batch Operations role.
data "aws_iam_policy_document" "batch_operations" {
  statement {
    sid    = "InvokeLambda"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [aws_lambda_function.scrubber.arn]
  }
}

resource "aws_iam_policy" "batch_operations" {
  name   = "${local.name_prefix}-batch-invoke"
  policy = data.aws_iam_policy_document.batch_operations.json
  tags   = local.common_tags
}
