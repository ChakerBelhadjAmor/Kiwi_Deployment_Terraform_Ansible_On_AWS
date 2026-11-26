# Kiwi TCMS on AWS (Terraform + Ansible)

Provisions one `t3.small` EC2 VM in `eu-north-1` and runs Kiwi TCMS behind Caddy
with a free DuckDNS name and a Let's Encrypt certificate. Expected cost is about
$21 for one month. Everything is removed by `terraform destroy`.

**Never commit:** `terraform.tfvars`, `*.tfstate`, `vault.yml`, `inventory/hosts.ini`,
keys, `~/.tcms.conf`. `.gitignore` covers them; `git status` must stay clean of them.

## Prerequisites

`terraform` >= 1.10, `ansible` (+ `ansible-galaxy collection install -r ansible/requirements.yml`),
AWS CLI v2 with credentials for your profile (`export AWS_PROFILE=kiwi`; SSO or access keys both work),
Docker (for the local importer test), Python 3 with `pip install -r importer/requirements.txt`.

## 1. One-time setup

```sh
ssh-keygen -t ed25519 -f ~/.ssh/kiwi_aws          # private key never leaves your machine
umask 077; openssl rand -base64 32 > ~/.ansible_vault_pass

# DuckDNS: sign in at duckdns.org, create your subdomain, copy the token.
cp terraform/terraform.tfvars.example terraform/terraform.tfvars   # set admin_cidr (your IP/32), email, expiry
cp ansible/group_vars/all/vault.yml.example ansible/group_vars/all/vault.yml
# fill vault.yml (use `openssl rand -base64 32` for passwords), then:
ansible-vault encrypt ansible/group_vars/all/vault.yml
```

## 2. Deploy

```sh
cd terraform && terraform init && terraform plan -out tfplan && terraform apply tfplan
cd ../ansible && ansible kiwi -m ping            # accept the host key once
ansible-playbook site.yml
ansible-playbook site.yml                        # 2nd run must report changed=0
```

Open `https://<your-subdomain>.duckdns.org` and log in as the vault admin user.
Registration is disabled; create the 3 user accounts in the Kiwi admin.

If your own IP changes (`curl -s ifconfig.me`): edit `admin_cidr` in `terraform.tfvars` and
`terraform apply`; or, in a hurry, `aws ec2 authorize-security-group-ingress` for port 22.
After a rebuild the SSH host key changes: `ssh-keygen -R <ip>`.

**Let's Encrypt limits:** for a first run use the staging CA per run (no rate limits, browser
warning, never committed): `ansible-playbook site.yml -e caddy_acme_staging=true`. Then run the
playbook again without the flag to get the real certificate (see the cert reset note in step 7 of the
walkthrough: delete `/data/caddy/certificates` in the Caddy container and restart it).
Do not delete the `kiwi_caddy_data` volume casually: re-issuing the cert repeatedly hits the limit.

**Image pinning:** all three images are pinned by digest in `ansible/group_vars/all/vars.yml`
(`scripts/image-digests.sh` prints current values; needs `skopeo`). The Kiwi pin was taken from Docker Hub's
`kiwitcms/kiwitcms`, which `pub.kiwitcms.eu` proxies, and has not been pulled through `pub.kiwitcms.eu` yet.
Before the first deploy with these pins, compare it with what runs now
(`ssh ... docker inspect --format '{{index .RepoDigests 0}}' kiwi-web-1`) and use the running digest if you do not
want Kiwi upgraded as a side effect. Update pins deliberately: run the script, review, commit.
On the first run check `docker compose exec web /Kiwi/manage.py shell -c "from django.conf import settings as s; print(s.SECRET_KEY[:4])"`:
it must NOT be the image default (confirm `KIWI_SECRET_KEY` is honoured).

## 3. Import the test cases

```sh
# credentials file, mode 600 (outside git)
cat > ~/.tcms.conf <<'CONF'
[tcms]
url = https://<your-subdomain>.duckdns.org/xml-rpc/
username = <admin user>
password = <admin password>
CONF
chmod 600 ~/.tcms.conf

python importer/import_xlsx.py docs/*.xlsx --product "Budget Tracker" --dry-run
python importer/import_xlsx.py docs/*.xlsx --product "Budget Tracker"
```

Re-running is safe: existing cases are skipped. `Budget_Tracker_Tests_Niveaux.xlsx`
repeats the other four workbooks, so IDs are de-duplicated (206 unique cases).

Publish the requirements as two test plans, "Besoin fonctionnel" and "Besoin non fonctionnel"
(Kiwi has no wiki; a plan description renders Markdown tables and shows in the dashboard):

```sh
python importer/import_requirements.py docs/besoin_fonctionnel.md     --product "Budget Tracker" --plan-name "Besoin fonctionnel"
python importer/import_requirements.py docs/besoin_non_fonctionnel.md --product "Budget Tracker" --plan-name "Besoin non fonctionnel"
```

Try the importer first against a throwaway local Kiwi (verified: 206 cases, re-run is a no-op):

```sh
docker compose -f local/docker-compose.yml up -d
k() { docker compose -f local/docker-compose.yml exec -T web /Kiwi/manage.py "$@"; }
k migrate --noinput && k createsuperuser     # or any admin you like
# ~/.tcms.conf -> url = https://127.0.0.1:8443/xml-rpc/ (+ that admin's credentials)
# The local cert is self-signed for another hostname, so for LOCAL testing only:
KIWI_INSECURE_TLS=1 python importer/import_xlsx.py docs/*.xlsx --product "Budget Tracker"
docker compose -f local/docker-compose.yml down -v && rm ~/.tcms.conf
```

Never set `KIWI_INSECURE_TLS` against the real server: it has a valid certificate.

## 4. Verify

`curl -sI http://<host>` redirects to HTTPS; the certificate is valid; only 22 (your IP),
80, 443 are reachable; `ssh ... free -m` shows swap; a reboot brings the site back.
A backup (DB dump + uploads + Caddy cert volume) runs daily at 02:30 into `/var/backups/kiwi` (7 days kept,
on the same disk; with `kiwi_backup_bucket` set each run is also uploaded to S3, see "Backups and restore"):
`ssh ... sudo /usr/local/sbin/kiwi-backup.sh`.

## 5. Teardown (end of the month)

Copy a backup off the VM first. Then:

```sh
cd terraform && terraform plan -destroy && terraform destroy
```

Check the EC2, VPC and Billing consoles are empty. Delete the DuckDNS subdomain at duckdns.org.
The state lives in S3 (see below), so you can destroy from any machine.

## 6. State and destroy

Terraform state is stored in a versioned, encrypted S3 bucket (`kiwi-tfstate-<account-id>`, key
`kiwi/terraform.tfstate`, native S3 locking). It is created once by `terraform/bootstrap/`, which keeps
its own small local state: keep a copy of `terraform/bootstrap/terraform.tfstate` somewhere safe.
The bucket is not part of the Kiwi stack, so `terraform destroy` never removes it.

Destroy from a fresh machine (needs your `terraform.tfvars`, AWS credentials for the same account):

```sh
git clone <repo> && cd <repo>/terraform
cp /path/to/terraform.tfvars .
export AWS_PROFILE=kiwi
terraform init            # connects to the S3 backend
terraform plan -destroy && terraform destroy
```

Restore an older state version (old versions expire after 365 days):

```sh
B=kiwi-tfstate-<account-id>
aws s3api list-object-versions --bucket $B --prefix kiwi/terraform.tfstate --query 'Versions[].[VersionId,LastModified]' --output text
aws s3api get-object --bucket $B --key kiwi/terraform.tfstate --version-id <id> old.tfstate
terraform state push old.tfstate     # review first with: terraform show old.tfstate
```

## CI

`.github/workflows/ci.yml` runs on every PR and push to `main`: `terraform fmt`/`validate` (no backend, no AWS),
`ansible-lint` + syntax-check, importer tests, and gitleaks. `main` is protected by a ruleset: PR required,
those four checks must pass, no force-push.

## Backups and restore

Three layers: a nightly dump on the VM (7 days), the same files uploaded to S3, and daily EBS snapshots of the disk.

**Turn on the S3 copy** (once, in this order):
```sh
cd terraform/bootstrap && terraform apply      # creates kiwi-backups-<account-id> (versioned, encrypted, 30 days)
cd .. && terraform apply                       # creates the VM role (write-only to that bucket) and the DLM snapshot policy
# set kiwi_backup_bucket: kiwi-backups-<account-id> in ansible/group_vars/all/vars.yml, then:
cd ../ansible && ansible-playbook site.yml
ssh ... sudo /usr/local/sbin/kiwi-backup.sh    # run once by hand, then check the bucket has a <stamp>/ folder
```
The VM can only add objects to the bucket (no read, list or delete), so a compromised host cannot erase its backups.
The bucket is in `terraform/bootstrap`, so `terraform destroy` of the stack does not delete it.

**Restore** (new or existing VM, after `ansible-playbook site.yml` has deployed the stack):
```sh
aws s3 ls s3://kiwi-backups-<account-id>/                      # pick a <stamp>, e.g. 2026-11-26-0230
sudo mkdir -p /var/backups/kiwi
aws s3 cp s3://kiwi-backups-<account-id>/<stamp>/ /var/backups/kiwi/ --recursive   # run where you have read access (your laptop), then scp to the VM
sudo /usr/local/sbin/kiwi-restore.sh <stamp>                   # asks you to type "yes"; replaces the DB and uploads
```
Test a restore once before you need it. `kiwi-restore.sh` was exercised end to end against a throwaway
MariaDB stack (backup, destroy data, restore, compare); it has not run on the real VM yet.

## Separate data disk (optional)

By default MariaDB's data lives on the VM's root disk. To keep it on its own encrypted EBS disk (it survives a VM
replacement), set `data_volume_size_gb = 20` in `terraform.tfvars` and `terraform apply`, then migrate **once**:

```sh
# on the VM
cd /opt/kiwi && docker compose stop web db
sudo mkdir /mnt/newdb && sudo mkfs.ext4 /dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<volume-id-without-dash>
sudo mount /dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<volume-id-without-dash> /mnt/newdb
sudo rsync -a /var/lib/docker/volumes/kiwi_kiwi_db/_data/ /mnt/newdb/ && sudo umount /mnt/newdb
sudo sh -c 'rm -rf /var/lib/docker/volumes/kiwi_kiwi_db/_data/*'    # only after checking the copy and a fresh backup
# then, from your machine: set kiwi_data_volume_id (terraform output data_volume_id) in vars.yml and run the playbook
```
The playbook refuses to mount the disk over a data directory that still holds files, so skipping the migration cannot
hide your data. The disk has no `prevent_destroy` (it would block the end-of-month `terraform destroy`); the daily
snapshots are the safety net. This path is **not tested on a real VM**: take a backup first.

## Access without an open SSH port (SSM)

The VM's role includes `AmazonSSMManagedInstanceCore`, so you can reach it through AWS Systems Manager instead of port 22.
Needs the AWS CLI and the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) on your machine.

```sh
terraform -chdir=terraform apply                       # attaches the SSM policy
terraform -chdir=terraform output -raw ssm_shell_command   # a shell on the VM, no SSH key needed
terraform -chdir=terraform output -raw ssm_ssh_config      # add to ~/.ssh/config: SSH (and Ansible) over SSM
```
Check that it works **before** closing the port: `aws ssm describe-instance-information` must list the instance
(registration can take a few minutes). Then set `ssh_ingress_enabled = false` in `terraform.tfvars` and `terraform apply`.
With SSH off, `terraform apply` also rewrites `ansible/inventory/hosts.ini` so Ansible goes through SSM (an
`ansible_ssh_common_args` ProxyCommand); `ansible_host` stays the Elastic IP because the Caddy role compares it with the DNS answer.
If SSM ever breaks, set `ssh_ingress_enabled = true` again (your `admin_cidr` rule comes back).

## Short-lived AWS credentials instead of access keys

Terraform and the CLI currently use a long-lived IAM user key (`~/.aws/credentials`, profile `kiwi`). Prefer SSO:

1. Enable IAM Identity Center in the account and assign yourself a permission set (admin for this project).
2. `aws configure sso` (profile `kiwi`), then `aws sso login --profile kiwi` when the session expires.
3. Remove the `[kiwi]` block from `~/.aws/credentials`, then deactivate and delete the old access key in IAM.
Nothing in this repo has to change: Terraform and the CLI read the same `AWS_PROFILE`. For CI, plan jobs would use GitHub
OIDC (a role trusted for this repository, no stored keys); that needs repository variables for the Terraform inputs and is
not set up yet.

## State and backup bucket protections

`terraform/bootstrap` also denies non-TLS requests on the state and backup buckets and writes S3 access logs
(who read or wrote state and backups) to `kiwi-tfstate-logs-<account-id>`, kept 90 days. Apply it like the other bootstrap changes:
`cd terraform/bootstrap && terraform apply`. The buckets use SSE-S3, not a customer-managed KMS key (about $1/month per key, no extra
protection for this threat model).

## Monitoring and alerts

`terraform apply` creates an SNS topic and CloudWatch alarms that email the `alert_email` address:
VM host failure (also **auto-recovers** the instance on healthy hardware, same disk and IP), OS not responding,
CPU credits nearly exhausted (t3 throttles when they run out), and sustained CPU above 90%.
AWS sends a confirmation email first: **click the link** or no alert will arrive.
Test it: `aws cloudwatch set-alarm-state --alarm-name kiwi-tcms-cpu-high --state-value ALARM --state-reason test`.

Not covered: free disk space and memory (they need the CloudWatch agent) and an external "is the site up" check.
`df -h` and `docker stats` over SSH or SSM are the manual check for now.

## Container and proxy hardening

All three containers run with `no-new-privileges`. Caddy also runs with a read-only root filesystem and only the
`NET_BIND_SERVICE` capability, and sends HSTS, `X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN`, a Referrer-Policy and a
Permissions-Policy, and hides the `Server` header. No Content-Security-Policy yet: Kiwi uses inline scripts, so a CSP needs
testing in the browser before it is enabled.
