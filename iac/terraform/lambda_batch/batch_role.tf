data "aws_iam_policy_document" "batch_assume" {
  count = var.create_batch_operations_role ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["batchoperations.s3.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "batch_s3" {
  count = var.create_batch_operations_role ? 1 : 0

  statement {
    sid    = "ReadManifests"
    effect = "Allow"
    actions = [
      "s3:GetObject",
    ]
    resources = [
      "arn:aws:s3:::${local.ops_bucket}/${local.inventory_prefix}*",
      "arn:aws:s3:::${local.ops_bucket}/${local.manifests_prefix}*",
    ]
  }

  statement {
    sid    = "WriteReports"
    effect = "Allow"
    actions = [
      "s3:PutObject",
    ]
    resources = [
      "arn:aws:s3:::${local.ops_bucket}/${local.batch_reports_prefix}*",
    ]
  }
}

resource "aws_iam_role" "batch_operations" {
  count              = var.create_batch_operations_role ? 1 : 0
  name               = "${local.name_prefix}-batch-role"
  assume_role_policy = data.aws_iam_policy_document.batch_assume[0].json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "batch_s3" {
  count  = var.create_batch_operations_role ? 1 : 0
  name   = "${local.name_prefix}-batch-s3"
  role   = aws_iam_role.batch_operations[0].id
  policy = data.aws_iam_policy_document.batch_s3[0].json
}

resource "aws_iam_role_policy_attachment" "batch_invoke_lambda" {
  count      = var.create_batch_operations_role ? 1 : 0
  role       = aws_iam_role.batch_operations[0].name
  policy_arn = aws_iam_policy.batch_operations.arn
}
