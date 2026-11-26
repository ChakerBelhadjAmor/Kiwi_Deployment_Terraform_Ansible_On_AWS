# Off-VM backup bucket. Lives here (not in the Kiwi stack) so that
# `terraform destroy` of the stack never deletes the backups.
resource "aws_s3_bucket" "backups" {
  bucket = "kiwi-backups-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket = aws_s3_bucket.backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Keep 30 days of backups; overwritten (noncurrent) versions also kept 30 days.
resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "expire-old-backups"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 30 # a compromised VM could overwrite a key; the good version must outlive the retention window
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 2
    }
  }

  depends_on = [aws_s3_bucket_versioning.backups]
}
