# Changelog

## v2.0.0 - 2026-11-26

Hardening release. Nothing in it is applied automatically: see "Upgrading from v1.0.0".

### Backups and recovery
- Nightly backups also go to a versioned, encrypted S3 bucket (`terraform/bootstrap`, outlives `terraform destroy`), through a write-only instance role.
- Daily EBS snapshots (DLM), `kiwi-restore.sh` and a restore runbook. Backup and restore were tested end to end on a throwaway stack.
- **Fixed:** backups archived an empty uploads volume (`kiwi_uploads` instead of `kiwi_kiwi_uploads`). Every backup taken before this release has an empty uploads archive; the database dump was fine.
- Optional separate encrypted data disk for MariaDB (off by default).

### Supply chain
- Kiwi, MariaDB and Caddy images pinned by digest (`scripts/image-digests.sh` to refresh).
- GitHub Actions pinned to commit SHAs; Trivy scan of the Terraform in CI; Dependabot for Terraform providers.
- AWS provider upgraded from 5.x to 6.x (plans verified identical against live AWS).

### Access and secrets
- SSM Session Manager access, and `ssh_ingress_enabled` to close port 22 (default stays open).
- TLS-only policies and S3 access logging on the state and backup buckets. Docs for moving from IAM access keys to SSO.

### Runtime and monitoring
- CloudWatch alarms (host failure with auto-recover, OS check, CPU credits, CPU) with email alerts.
- `no-new-privileges` on all containers, read-only Caddy with dropped capabilities, security headers.

### Upgrading from v1.0.0
1. `terraform init -upgrade` in `terraform/` and `terraform/bootstrap/` (provider 6.x).
2. Apply bootstrap, then the main stack, then set `kiwi_backup_bucket` and run the playbook (README, "Backups and restore").
3. Compare the pinned Kiwi digest with the running one before the first playbook run, or Kiwi upgrades as a side effect.
4. Confirm the SNS subscription email, or no alert is delivered.

### Known
- No disk-space or memory alarms, external uptime check, CSP header or GitHub OIDC plan job yet.

## v1.0.0 - 2026-11-26

- Kiwi TCMS on one AWS EC2 VM (Terraform + Ansible), Caddy with DuckDNS and Let's Encrypt.
- Importer for the test-case workbooks and the two requirements test plans.
- GitHub Actions CI (terraform, ansible, importer, gitleaks) and dependabot.
- Terraform state moved to a versioned, encrypted S3 bucket created by `terraform/bootstrap/`.

Known: `kiwi_image_tag` is still `latest`; pin it to a digest after the first good deploy.
