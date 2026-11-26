# State bucket bootstrap

Creates the versioned S3 bucket that stores the Kiwi stack's Terraform state.
Run once, from this directory, with AWS SSO logged in:

```sh
terraform init && terraform plan -out tfplan && terraform apply tfplan
terraform output bucket_name   # copy into ../versions.tf backend block
```

This directory keeps its own **local** state (gitignored, small). Keep a copy somewhere safe.
The bucket has `prevent_destroy`; old state versions expire after 365 days.
Do not delete the bucket while the Kiwi stack exists: you could no longer destroy it.
