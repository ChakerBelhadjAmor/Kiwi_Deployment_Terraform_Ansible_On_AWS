output "bucket_name" {
  description = "Name of the Terraform state bucket; put it in terraform/versions.tf backend block."
  value       = aws_s3_bucket.state.bucket
}

output "backup_bucket_name" {
  description = "Bucket that receives the VM's nightly backups (set kiwi_backup_bucket in ansible vars)."
  value       = aws_s3_bucket.backups.bucket
}
