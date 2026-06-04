resource "aws_s3_bucket" "dest" {
  count  = var.create_dest_bucket ? 1 : 0
  bucket = var.dest_bucket_name
  tags   = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "dest" {
  count  = var.create_dest_bucket ? 1 : 0
  bucket = aws_s3_bucket.dest[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dest" {
  count  = var.create_dest_bucket ? 1 : 0
  bucket = aws_s3_bucket.dest[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = var.kms_key_arn != null
  }
}
