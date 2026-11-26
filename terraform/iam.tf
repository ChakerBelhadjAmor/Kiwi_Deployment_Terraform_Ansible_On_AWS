data "aws_caller_identity" "current" {}

locals {
  # Created by terraform/bootstrap so it outlives this stack.
  backup_bucket = "kiwi-backups-${data.aws_caller_identity.current.account_id}"
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "kiwi" {
  name_prefix        = "${var.project_tag}-vm-"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# Write-only: the VM can add backups but not read, list or delete them, so a
# compromised host cannot destroy its own backup history.
data "aws_iam_policy_document" "backup_upload" {
  statement {
    sid       = "UploadBackups"
    actions   = ["s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["arn:aws:s3:::${local.backup_bucket}/*"]
  }
}

resource "aws_iam_role_policy" "backup_upload" {
  name   = "backup-upload"
  role   = aws_iam_role.kiwi.id
  policy = data.aws_iam_policy_document.backup_upload.json
}

resource "aws_iam_instance_profile" "kiwi" {
  name_prefix = "${var.project_tag}-vm-"
  role        = aws_iam_role.kiwi.name
}
