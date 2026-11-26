# Release v1.0.0: Kiwi TCMS on one AWS VM

**What this release is.** A complete, one-command-per-stage deployment of [Kiwi TCMS](https://kiwitcms.org) (an open-source
test-management web app) on a single AWS virtual machine in `eu-north-1`, with a free DuckDNS hostname and a Let's Encrypt
certificate, plus the tooling to load the "Budget Tracker" test cases into it. It is built for a **one-month, one-user-group
deployment at about $21 for the month**, and everything is removed by `terraform destroy`.

Tag: `v1.0.0`. Day-to-day instructions (setup, deploy, teardown) are in the [root README](../../README.md). This page explains
**what v1 contains and how the parts fit together**. For what changed afterwards, see [v2.0.0](../v2.0.0/README.md).

## Architecture diagram (Eraser)

The diagram source is [`diagram.eraser`](diagram.eraser) (Eraser "diagram-as-code" format). To view or edit it:

1. Go to [eraser.io](https://app.eraser.io) and create a new file.
2. Add a **Cloud architecture diagram** and paste the code below (or the contents of `diagram.eraser`).
3. Export a PNG or SVG if you want an image for slides or reports.

The code was written to follow Eraser's syntax but was **not rendered by the author**; if an icon name is not recognised,
Eraser simply draws the node without an icon, so rename or remove it.

```eraser
title Kiwi TCMS on AWS - release v1.0.0
direction right

// People and outside services
Testers [icon: users]
DuckDNS [icon: globe]
Lets Encrypt [icon: lock]
GitHub Actions [icon: github]

// Everything that runs on the operator's own machine
Operator laptop [icon: laptop] {
  Terraform [icon: terraform]
  Ansible [icon: ansible]
  Importer [icon: python]
}

AWS eu-north-1 [icon: aws] {
  State bucket [icon: aws-s3]
  Budget alert [icon: aws-budgets]

  VPC [icon: aws-vpc] {
    Internet gateway [icon: aws-internet-gateway]
    Public subnet [icon: aws-vpc] {
      Security group [icon: aws-vpc] {
        EC2 t3 small [icon: aws-ec2] {
          Caddy [icon: docker]
          Kiwi web [icon: docker]
          MariaDB [icon: database]
          Local backups [icon: aws-ebs]
        }
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
MariaDB > Local backups: nightly dump
Caddy > Lets Encrypt: certificate
EC2 t3 small > DuckDNS: keeps the name pointed at the IP

// Operator tooling
Terraform > VPC: provisions
Terraform > State bucket: remote state
Ansible > EC2 t3 small: configures over SSH 22 from the admin IP only
Importer > Caddy: XML-RPC import of test cases
Budget alert > Operator laptop: email at 80 and 100 percent
GitHub Actions > Terraform: fmt and validate only, no AWS access
```

### How to read it

- **Users** reach the VM only through the Elastic IP on 443. Caddy terminates TLS and forwards to Kiwi over the private Docker
  network. MariaDB is on an internal-only Docker network, so it cannot reach, or be reached from, the internet.
- **The operator** (you) runs Terraform, Ansible and the importer from a laptop. SSH (port 22) is open **only to your own
  IP** (`admin_cidr`, a `/32`).
- **GitHub Actions** runs checks on the code. It has no AWS credentials and never touches the infrastructure.

## What is in the release

### 1. Infrastructure (Terraform, `terraform/`)

| Resource | Details |
|---|---|
| VPC, subnet, internet gateway, route table | One VPC `10.20.0.0/16`, one public subnet `10.20.1.0/24`. `map_public_ip_on_launch = false`: the Elastic IP is the only public address. |
| Security group | Inbound: SSH 22 from `admin_cidr` only; HTTP 80 and HTTPS 443 from anywhere (80 is for the Let's Encrypt challenge and the redirect). Outbound: all. |
| EC2 instance | Ubuntu 24.04 (Canonical AMI, looked up at plan time), `t3.small` (2 GB RAM), 30 GB gp3 root disk, **encrypted**, **IMDSv2 required**. `ignore_changes = [ami]` so a newer Ubuntu image never recreates the VM (the data lives on its disk). |
| Elastic IP | Stable public address for DNS and the certificate. |
| Key pair | Your **public** SSH key only; the private key never leaves your machine. |
| Budget | Monthly cost budget (default $30) that emails `alert_email` at 80% and 100% of actual spend. |
| Tags | Every resource gets `Project` and `Expires` tags so a forgotten deployment is easy to spot. |
| Outputs | `public_ip`, `ssh_command`, and a generated Ansible inventory file (`ansible/inventory/hosts.ini`, gitignored). |

Input variables (`terraform.tfvars`, gitignored; `terraform.tfvars.example` is the template): `region`, `instance_type`,
`admin_cidr` (validated to be a single `/32`), `ssh_public_key_path`, `project_tag`, `expires_tag`, `alert_email`, `budget_limit_usd`.

**Remote state (`terraform/bootstrap/` and the `s3` backend).** Terraform state is stored in a **versioned, encrypted S3 bucket**
(`kiwi-tfstate-<account-id>`) with native S3 locking. The bucket is created once by `terraform/bootstrap/`, which keeps its own
small local state, so `terraform destroy` of the Kiwi stack never deletes it. Old state versions expire after 365 days. This is what
lets you come back later, from any machine, and destroy exactly what was built.

### 2. Server configuration (Ansible, `ansible/`)

`site.yml` applies four roles, in order. Running it twice must report `changed=0` (idempotent).

| Role | What it does |
|---|---|
| `common` | Full apt upgrade; installs `ufw`, `fail2ban`, `unattended-upgrades`, `curl`, `dnsutils`; creates a **2 GB swap file** (swappiness 10) because 2 GB of RAM is tight; turns on automatic security upgrades; `ufw` denies all inbound except 22/80/443; starts `fail2ban`; **hardens sshd** (no passwords, no root login) with a drop-in that sorts before Ubuntu's cloud-init file, then **asserts** the effective settings really are off. |
| `docker` | Adds Docker's apt repository and signing key, installs Docker Engine and the compose plugin, caps container logs at 3 files x 10 MB, lets the `ubuntu` user run Docker. |
| `caddy` | Writes the DuckDNS token to a root-only file (mode 0600), installs a script and a **systemd timer** that keep the DuckDNS name pointed at the Elastic IP, **waits until DNS resolves to the VM**, and writes the `Caddyfile` (reverse proxy to Kiwi; **self-registration is blocked with a 403** on `/accounts/register/`, so only the admin creates accounts). A `caddy_acme_staging` switch uses Let's Encrypt's staging CA to avoid rate limits while testing. |
| `kiwi` | Installs the compose file and secret env files (mode 0600), starts the stack, runs Django migrations, **checks that Kiwi really uses MariaDB and not SQLite**, creates the admin user if missing (the password is passed through the environment, never on a command line), waits for the site to answer over HTTPS, sets the Kiwi site domain, and installs the **nightly backup** (cron 02:30). |

Secrets (admin password, database passwords, Django secret key, DuckDNS token) live in `ansible/group_vars/all/vault.yml`, encrypted
with **Ansible Vault** and gitignored. Tasks that touch secrets use `no_log`.

### 3. The running application (three containers on the VM)

| Container | Image | Role |
|---|---|---|
| `caddy` | `caddy:2.11-alpine` | The **only** container that publishes ports (80, 443). Gets and renews the Let's Encrypt certificate. |
| `web` | `pub.kiwitcms.eu/kiwitcms/kiwitcms:latest` | Kiwi TCMS (Django). All Linux capabilities dropped, 900 MB memory limit. |
| `db` | `mariadb:11.8` | Kiwi's database. Healthcheck-gated start, 512 MB limit, on an **internal** Docker network. |

Named volumes: `kiwi_db` (database files), `kiwi_uploads` (attachments), `caddy_data` (certificates), `caddy_config`.

### 4. Test-case importer (`importer/`)

Python scripts that load the project's test documentation into Kiwi through its XML-RPC API (credentials come from
`~/.tcms.conf`, mode 600, never from arguments or the repo).

- `import_xlsx.py` reads the five `.xlsx` workbooks (component, integration, system, acceptance, and a combined "levels" workbook).
  Each sheet becomes a **Test Plan**; each row becomes a **Test Case** (ID and context become the summary; data, preconditions,
  postconditions and expected result become a Markdown body; priority maps Haute/Moyenne/Basse to P1/P3/P5; the linked requirement
  becomes a tag such as `BF-01`). It **skips non-case sheets**, supports `--dry-run`, and is **safe to re-run**: existing cases are skipped.
  The combined workbook repeats the other four, so IDs are de-duplicated to **206 unique cases**.
- `import_requirements.py` publishes the functional and non-functional requirement tables (Markdown) as two Test Plan descriptions,
  because Kiwi has no wiki but renders Markdown tables in a plan description.
- 21 automated tests (`pytest`), and `local/docker-compose.yml`, a throwaway Kiwi on `127.0.0.1:8443` to try the importer before
  touching the real server.

### 5. Quality and safety nets

- **CI (GitHub Actions)**: `terraform fmt` + `validate`, `ansible-lint` + syntax check, importer tests, and **gitleaks**. Check-only: no AWS
  credentials, no secrets. Dependabot keeps Actions and Python packages current.
- **Pre-commit gitleaks hook** blocks secrets before they are committed.
- **Branch protection** on `main`: pull request required, the four checks must pass, no force-push or deletion, linear history.
- **Never committed** (gitignored): `terraform.tfvars`, state files, `vault.yml`, the inventory, SSH keys, `~/.tcms.conf`.

## Cost

About $21 for one month: `t3.small` compute, 30 GB gp3, the Elastic IP attached to a running instance, and cents for the state bucket.
The budget alarm emails you at 80% and 100% of the limit.

## Security posture of v1

Good: encrypted disk, IMDSv2, SSH key-only and restricted to one IP, host firewall plus fail2ban, automatic security updates, no
published ports except Caddy's, internal database network, dropped capabilities on Kiwi, secrets in Ansible Vault, remote versioned state.

## Known limitations (the reason v2 exists)

- **Backups stay on the same disk** (7 days) and must be copied off by hand. Lose the VM and you lose the backups too.
- **A bug in the backup script:** it archives a volume called `kiwi_uploads`, but the real volume is `kiwi_kiwi_uploads`, so the **uploads
  archive in every v1 backup is empty**. The database dump is correct. Fixed in v2.
- Images are not pinned by digest (`latest` for Kiwi); Terraform AWS provider 5.x.
- No monitoring or alerting besides the budget; no restore procedure; SSH must stay open to your IP; long-lived IAM access keys.
- Single VM in a single availability zone: no high availability (accepted, to stay near $21/month).

## Upgrading

See [v2.0.0](../v2.0.0/README.md#upgrading-from-v100).
