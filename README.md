# Kiwi TCMS on AWS (Terraform + Ansible)

Provisions one `t3.small` EC2 VM in `us-east-1` and runs Kiwi TCMS behind Caddy
with a free DuckDNS name and a Let's Encrypt certificate. Expected cost is about
$21 for one month. Everything is removed by `terraform destroy`.

**Never commit:** `terraform.tfvars`, `*.tfstate`, `vault.yml`, `inventory/hosts.ini`,
keys, `~/.tcms.conf`. `.gitignore` covers them; `git status` must stay clean of them.

## Prerequisites

`terraform`, `ansible` (+ `ansible-galaxy collection install -r ansible/requirements.yml`),
AWS CLI v2 logged in via SSO (`aws configure sso`, `export AWS_PROFILE=...`),
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

**Let's Encrypt limits:** while iterating set `caddy_acme_staging: true` in
`ansible/group_vars/all/vars.yml` (no rate limits, browser warning), then flip to `false` once.
Do not delete the `kiwi_caddy_data` volume casually: re-issuing the cert repeatedly hits the limit.

**After the first good deploy:** pin the Kiwi image. Run
`ssh ... docker inspect --format '{{index .RepoDigests 0}}' pub.kiwitcms.eu/kiwitcms/kiwitcms:latest`
and set `kiwi_image_tag` to `latest@sha256:...` style digest in `vars.yml`.
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

Try the importer first against a throwaway local Kiwi:

```sh
docker compose -f local/docker-compose.yml up -d
docker compose -f local/docker-compose.yml exec web /Kiwi/manage.py migrate --noinput
docker compose -f local/docker-compose.yml exec web /Kiwi/manage.py createsuperuser
# point ~/.tcms.conf at https://127.0.0.1:8443/xml-rpc/ (self-signed cert), run the importer
docker compose -f local/docker-compose.yml down -v
```

## 4. Verify

`curl -sI http://<host>` redirects to HTTPS; the certificate is valid; only 22 (your IP),
80, 443 are reachable; `ssh ... free -m` shows swap; a reboot brings the site back.
A backup (DB dump + uploads + Caddy cert volume) runs daily at 02:30 into `/var/backups/kiwi` (7 days kept,
on the same disk: `scp` it to your machine before teardown):
`ssh ... sudo /usr/local/sbin/kiwi-backup.sh`.

## 5. Teardown (end of the month)

Copy a backup off the VM first. Then:

```sh
cd terraform && terraform plan -destroy && terraform destroy
```

Check the EC2, VPC and Billing consoles are empty. Delete the DuckDNS subdomain at duckdns.org.
Keep `terraform.tfstate` until `destroy` finishes.
