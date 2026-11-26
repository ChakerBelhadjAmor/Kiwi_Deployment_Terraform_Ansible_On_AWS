output "bucket_name" {
  description = "Name of the Terraform state bucket; put it in terraform/versions.tf backend block."
  value       = aws_s3_bucket.state.bucket
}
