# Release v2.0.0: the hardened Kiwi TCMS deployment

**What this release is.** The same single-VM Kiwi TCMS deployment as [v1.0.0](../v1.0.0/README.md), hardened in four areas:
**(1)** backups and recovery, **(2)** supply chain, **(3)** access and secrets, **(4)** runtime and monitoring. It also fixes a real
bug in v1's backups. The application, the importer and the deployment steps are unchanged; what changed is how safely it runs and how
well you can recover from a failure.

Tag: `v2.0.0`. Setup, deploy and teardown steps are in the [root README](../../README.md); the change list is in the
[CHANGELOG](../../CHANGELOG.md). This page explains **what v2 contains and how the parts fit together**.

> **Nothing in v2 is applied automatically.** Merging the code changes nothing in AWS. You apply it yourself, in the order given in
> [Upgrading from v1.0.0](#upgrading-from-v100).

## Architecture diagram (Eraser)

The diagram source is [`diagram.eraser`](diagram.eraser) (Eraser "diagram-as-code" format). To view or edit it:

1. Go to [eraser.io](https://app.eraser.io) and create a new file.
2. Add a **Cloud architecture diagram** and paste the code below (or the contents of `diagram.eraser`).
3. Export a PNG or SVG if you want an image for slides or reports.

The code was written to follow Eraser's syntax but was **not rendered by the author**; if an icon name is not recognised, Eraser
draws the node without an icon, so rename or remove it.

```eraser
title Kiwi TCMS on AWS - release v2.0.0
direction right

// People and outside services
Testers [icon: users]
Alert email [icon: mail]
DuckDNS [icon: globe]
Lets Encrypt [icon: lock]

// Code hosting and checks
GitHub [icon: github] {
  CI checks [icon: github]
  Trivy scan [icon: shield]
  Gitleaks [icon: shield]
  Dependabot [icon: github]
}

// Everything that runs on the operator's own machine
Operator laptop [icon: laptop] {
  Terraform [icon: terraform]
  Ansible [icon: ansible]
  Importer [icon: python]
  AWS CLI [icon: aws]
}

AWS eu-north-1 [icon: aws] {

  // Buckets that outlive the Kiwi stack (terraform/bootstrap)
  Long lived buckets [icon: aws-s3] {
    State bucket [icon: aws-s3]
    Backups bucket [icon: aws-s3]
    Access logs bucket [icon: aws-s3]
  }

  Monitoring [icon: aws-cloudwatch] {
    CloudWatch alarms [icon: aws-cloudwatch]
    SNS alerts topic [icon: aws-sns]
  }

  Budget alert [icon: aws-budgets]
  Systems Manager [icon: aws-systems-manager]
  Snapshot policy [icon: aws-ebs]
  Instance role [icon: aws-iam]

  VPC [icon: aws-vpc] {
    Internet gateway [icon: aws-internet-gateway]
    Public subnet [icon: aws-vpc] {
      Security group [icon: aws-vpc] {
        EC2 t3 small [icon: aws-ec2] {
          Caddy [icon: docker]
          Kiwi web [icon: docker]
          MariaDB [icon: database]
          Local backup copy [icon: aws-ebs]
        }
        Root disk [icon: aws-ebs]
        Optional data disk [icon: aws-ebs]
      }
    }
  }
  Elastic IP [icon: aws-ec2]
}

// Traffic from users
Testers > Elastic IP: HTTPS 443
Elastic IP > Internet gateway
Internet gateway > Caddy
Caddy > Kiwi web: HTTPS 8443 internal
Kiwi web > MariaDB: MySQL 3306 backend network
Caddy > Lets Encrypt: certificate
EC2 t3 small > DuckDNS: keeps the name pointed at the IP

// Backups and recovery
MariaDB > Local backup copy: nightly dump
Local backup copy > Backups bucket: upload with write only role
Instance role > EC2 t3 small: attached
Snapshot policy > Root disk: daily snapshot kept 7 days
MariaDB > Optional data disk: database files when enabled

// Access without an open SSH port
AWS CLI > Systems Manager: start session
Systems Manager > EC2 t3 small: shell or SSH tunnel
Ansible > EC2 t3 small: configures over SSM or SSH

// Monitoring
EC2 t3 small > CloudWatch alarms: status and CPU metrics
CloudWatch alarms > EC2 t3 small: auto recover on host failure
CloudWatch alarms > SNS alerts topic
SNS alerts topic > Alert email
Budget alert > Alert email: spend at 80 and 100 percent

// State, logging and operator tooling
Terraform > State bucket: remote state
State bucket > Access logs bucket: access logs
Backups bucket > Access logs bucket: access logs
Terraform > VPC: provisions
Importer > Caddy: XML-RPC import of test cases

// Repository checks (no AWS access)
Dependabot > CI checks: update pull requests
CI checks > Trivy scan
CI checks > Gitleaks
```

### How to read it

- **User traffic** is unchanged from v1: Elastic IP, then Caddy (TLS), then Kiwi, then MariaDB on an internal network.
- **Backups** leave the VM: the nightly dump is uploaded to an S3 bucket through the instance role, which can only **add** objects.
  The daily EBS snapshot policy is a second, independent copy.
- **Access** no longer needs an open SSH port: you can reach the VM through AWS Systems Manager (SSM) from the AWS CLI.
- **Monitoring** watches the VM and emails you; on a host failure it also **recovers the VM automatically**.
- **The three S3 buckets** (state, backups, access logs) live in `terraform/bootstrap`, so `terraform destroy` of the Kiwi stack never
  deletes your state or your backups.
- **GitHub** runs checks only. It has no AWS credentials.

## What is new compared with v1

### 1. Backups and recovery

| Item | What it does |
|---|---|
| **Off-VM backup bucket** | `kiwi-backups-<account-id>`: versioned, encrypted (SSE-S3), all public access blocked, TLS-only. Objects expire after **30 days**; overwritten versions are also kept 30 days (a compromised VM could overwrite a key, so the good copy must outlive the window). `prevent_destroy` on the bucket. Created by `terraform/bootstrap`, so it survives `terraform destroy`. |
| **VM instance role** | An IAM role and instance profile attached to the VM. Its only backup permission is `s3:PutObject` (and abort-multipart) on that bucket: the VM **cannot read, list or delete** backups, so a compromised host cannot erase its own history. Credentials come from the instance metadata service; none are stored on disk. |
| **Nightly upload** | `backup.sh` (cron 02:30) still writes the local dump, uploads, and archives, and now also copies the day's files to `s3://<bucket>/<timestamp>/`. The upload runs in the official AWS CLI container on the **host network** (IMDSv2 allows one network hop, so the default Docker bridge cannot reach the credentials). Controlled by `kiwi_backup_bucket`; empty means v1 behaviour. |
| **EBS snapshots** | Data Lifecycle Manager takes a **daily snapshot** of the VM's root disk (03:30 UTC), keeps **7**, and copies tags. Targets any volume tagged `Snapshot=daily`. |
| **Restore script** | `kiwi-restore.sh <timestamp>` (installed on the VM): checks the three backup files exist and the dump is a valid gzip, asks you to type `yes`, then drops and recreates the database, loads the dump, and restores the uploads and certificate volumes. |
| **Optional data disk** | `data_volume_size_gb` (default `0` = off) adds a separate **encrypted gp3 volume** mounted over MariaDB's data directory, so replacing the VM does not take the database with it. The playbook **refuses to mount it over existing database files**, so skipping the manual migration cannot hide your data. No `prevent_destroy` (it would block the end-of-month destroy); the daily snapshots cover it. |
| **Bug fixed** | v1's backup archived a volume called `kiwi_uploads`; the real name is `kiwi_kiwi_uploads` (compose prefixes the project name). Docker silently created an empty volume, so **every v1 backup has an empty uploads archive**. v2 uses the real names (`kiwi_uploads_volume`, `kiwi_caddy_volume`) and **fails loudly** if a volume does not exist. |

### 2. Supply chain

| Item | What it does |
|---|---|
| **Images pinned by digest** | Kiwi, MariaDB and Caddy are pinned as `tag@sha256:...` in `ansible/group_vars/all/vars.yml`, so the same commit always deploys the same bytes. `scripts/image-digests.sh` (needs `skopeo`) prints fresh values for deliberate updates. |
| **Actions pinned to commit SHAs** | Each GitHub Action is referenced by full commit SHA with a `# vX.Y.Z` comment, so a moved tag cannot change what runs. Dependabot keeps the SHAs current. |
| **Trivy in CI** | New `iac-scan` job: `trivy config` on `terraform/` fails the build on HIGH or CRITICAL findings. Accepted findings are listed with reasons in `.trivyignore` (see [Accepted risks](#accepted-risks-and-why)). |
| **Dependabot for Terraform** | Weekly provider updates for `terraform/` and `terraform/bootstrap`, in addition to Actions and pip. |
| **AWS provider 5.x to 6.x** | Upgraded to `~> 6.73`. Before merging, the same read-only `terraform plan` was run against live AWS under both versions for both stacks: **identical resource plans**, no deprecation warnings. |

### 3. Access and secrets

| Item | What it does |
|---|---|
| **SSM Session Manager** | The instance role includes `AmazonSSMManagedInstanceCore`. Outputs `ssm_shell_command` (a shell with no SSH key) and `ssm_ssh_config` (an SSH config block that tunnels SSH through SSM). Needs the AWS CLI and the Session Manager plugin on your machine. |
| **Switch to close port 22** | `ssh_ingress_enabled` (default **`true`**, so nothing changes until you flip it). When `false`, the SSH security-group rule is removed and the generated Ansible inventory gains an SSM `ProxyCommand` (`ansible_host` stays the Elastic IP, which the Caddy role needs). |
| **Bucket protections** | The state and backup buckets deny any non-TLS request and write **S3 access logs** (who read or wrote state and backups) to `kiwi-tfstate-logs-<account-id>`, kept 90 days, `prevent_destroy`. |
| **SSO guide** | Step-by-step move from the long-lived IAM user key to IAM Identity Center (documentation only; nothing in the repo depends on the key). |

### 4. Runtime and monitoring

| Item | What it does |
|---|---|
| **CloudWatch alarms** | Four alarms, all publishing to an SNS topic that **emails `alert_email`**: `status-check-system` (host failure: also **auto-recovers** the instance onto healthy hardware, same disk and IP), `status-check-instance` (OS not responding for 3 minutes), `cpu-credits-low` (t3 balance under 20, because the VM is throttled when credits run out), `cpu-high` (above 90% for 30 minutes). |
| **Container hardening** | `no-new-privileges` on all three containers. Caddy additionally runs with a **read-only root filesystem** (tmpfs `/tmp`), all capabilities dropped except `NET_BIND_SERVICE`. |
| **Security headers** | Caddy sends `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`, and hides the `Server` header. No Content-Security-Policy yet (Kiwi uses inline scripts; it needs browser testing first). |

## Resource inventory

New in v2, by stack (counts are from `terraform plan` against the live account, defaults only):

| Stack | New resources | Count |
|---|---|---|
| `terraform/` (the Kiwi VM) | VM role, backup-upload policy, instance profile, SSM policy attachment, DLM role + attachment + lifecycle policy, SNS topic + email subscription, 4 CloudWatch alarms | **13 added**, 1 in-place change (the VM gets the instance profile; no reboot, no replacement), 0 destroyed |
| `terraform/bootstrap/` (long-lived buckets) | Backups bucket (+ versioning, encryption, public-access block, lifecycle), logs bucket (+ encryption, block, lifecycle, policy), TLS-only policies on state and backups, access logging for both | **14 added**, 0 changed, 0 destroyed |
| Optional | Data EBS volume + attachment (only if `data_volume_size_gb > 0`) | 0 by default |

New Terraform inputs: `ssh_ingress_enabled` (bool, default `true`), `data_volume_size_gb` (number, default `0`).
New outputs: `instance_id`, `ssm_shell_command`, `ssm_ssh_config`, `data_volume_id`; bootstrap: `backup_bucket_name`.
New Ansible variables: `kiwi_backup_bucket`, `kiwi_aws_cli_image`, `kiwi_uploads_volume`, `kiwi_caddy_volume`,
`kiwi_data_volume_id`, `kiwi_db_volume`, `kiwi_db_mountpoint`.

## Accepted risks (and why)

These Trivy findings are deliberately ignored in `.trivyignore`, each with its reason:

| Finding | Why it is accepted |
|---|---|
| `AVD-AWS-0107` public ingress | Ports 80 and 443 are the point of the service; SSH is restricted to `admin_cidr`. |
| `AVD-AWS-0104` open egress | The VM needs apt, Docker pulls, Let's Encrypt and DuckDNS. Restricting egress is brittle and low value here. |
| `AVD-AWS-0132` no customer-managed KMS key | SSE-S3 is free; a customer-managed key costs about $1/month per key and adds little for this threat model. |
| `AVD-AWS-0095` unencrypted alerts topic | The topic carries only alarm names. CloudWatch cannot publish to a topic encrypted with the AWS-managed key, so encrypting it needs a customer-managed key. |

Also accepted: single VM in a single availability zone (no high availability), and a Caddy-to-Kiwi hop that skips certificate
verification (it stays on a private Docker network).

## What was tested, and what was not

**Tested**
- `terraform validate` and a read-only `plan` against live AWS for both stacks (0 destroys).
- `ansible-lint` and syntax check; `shellcheck` on the rendered backup and restore scripts.
- **Backup, destroy data, restore, compare** end to end on a throwaway MariaDB stack (database row and uploaded file recovered; junk removed).
- The real Caddy image running read-only with dropped capabilities: all five security headers present, `Server` removed. MariaDB 11.8 starts
  healthy with `no-new-privileges`.
- CI on every change, including the new Trivy scan.

**Not tested** (needs your AWS account or the live VM)
- The S3 upload from the VM, an SSM session, Ansible over SSM, the data-disk migration, DLM snapshots running, alarms firing.
- The Kiwi image under `no-new-privileges` (Docker Hub rate-limited the test).
- The first real `terraform apply` under AWS provider 6.x (the plans matched, but an apply has not run on it).

## Known gaps

No disk-space or memory alarms (they need the CloudWatch agent), no external "is the site up" check, no Content-Security-Policy, no GitHub
OIDC `terraform plan` job (the Terraform inputs are not in the repo), S3 Object Lock for backups (optional follow-up).

## Upgrading from v1.0.0

1. `terraform init -upgrade` in `terraform/` and `terraform/bootstrap/` (AWS provider 6.x).
2. `cd terraform/bootstrap && terraform apply` (creates the backup and log buckets and the bucket protections).
3. `cd terraform && terraform apply` (instance role, snapshots, alarms; the VM is updated in place).
4. Set `kiwi_backup_bucket: kiwi-backups-<account-id>` in `ansible/group_vars/all/vars.yml`, then `ansible-playbook site.yml`.
   **First compare the pinned Kiwi digest with what runs now** (instructions in `vars.yml`), or Kiwi upgrades as a side effect.
5. **Click the confirmation link** in the SNS email, or no alert is delivered.
6. Run `sudo /usr/local/sbin/kiwi-backup.sh` once by hand and check the bucket has a `<timestamp>/` folder.
7. Optional: verify SSM works (`aws ssm describe-instance-information`), then set `ssh_ingress_enabled = false`.
