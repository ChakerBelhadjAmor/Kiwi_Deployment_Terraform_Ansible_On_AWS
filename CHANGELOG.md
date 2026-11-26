# Changelog

## v1.0.0 - 2026-11-26

- Kiwi TCMS on one AWS EC2 VM (Terraform + Ansible), Caddy with DuckDNS and Let's Encrypt.
- Importer for the test-case workbooks and the two requirements test plans.
- GitHub Actions CI (terraform, ansible, importer, gitleaks) and dependabot.
- Terraform state moved to a versioned, encrypted S3 bucket created by `terraform/bootstrap/`.

Known: `kiwi_image_tag` is still `latest`; pin it to a digest after the first good deploy.
