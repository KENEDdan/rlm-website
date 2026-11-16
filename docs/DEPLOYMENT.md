# Deployment runbook

> **Status (2026-11-16): prepared and rehearsed, NOT executed.** No server, domain, DNS or GitHub repository
> exists yet. Every file below was rehearsed on the development PC with the real scripts: first deploy,
> HTTPS, security headers, network isolation, uploads, encrypted backup + restore, and automatic rollback
> of a deliberately broken release (see "Rehearsal results" at the end).

## 0. Before anything: the ministry owns every account

Create these **in the ministry's name**, with the Founder plus one deputy as owners and 2FA switched on:

| Account | Purpose |
|---|---|
| Domain registrar | the domain (e.g. `rebuildinglives.org`); enable registrar lock |
| Cloudflare | DNS, proxy/WAF, Turnstile (free plan is enough) |
| VPS provider | the server (Ubuntu 24.04, 2 vCPU, 4 GB RAM, 80 GB SSD is plenty) |
| GitHub organisation | private repository + CI (`.github/workflows/ci.yml`) |
| Transactional email | sending from the domain (any SMTP provider supporting DKIM) |
| Off-site backup storage | S3-compatible bucket (e.g. Backblaze B2, Wasabi) or any rclone remote |
| Uptime monitor | e.g. UptimeRobot or Better Stack (free tiers) |
| Sentry (optional) | error reports, PII scrubbed |

Developers get **their own** user on each service, never the owner login.

## 1. DNS records (at Cloudflare)

Replace `example.org`, `203.0.113.10` / `2001:db8::10` with the real domain and server IPs.

| Type | Name | Value | Proxy | Why |
|---|---|---|---|---|
| A | `@` | `203.0.113.10` | Proxied (orange) | website |
| AAAA | `@` | `2001:db8::10` | Proxied | website over IPv6 (if the VPS has IPv6) |
| CNAME | `www` | `example.org` | Proxied | redirected to the bare domain by Caddy |
| CAA | `@` | `0 issue "letsencrypt.org"` | – | only Let's Encrypt may issue certificates |
| MX | `@` | from the email provider | DNS only | receiving mail (if the provider hosts the mailbox) |
| TXT | `@` | `v=spf1 include:<provider-spf> -all` | DNS only | SPF: who may send as the domain |
| TXT/CNAME | `<selector>._domainkey` | from the email provider | DNS only | DKIM signature key |
| TXT | `_dmarc` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@example.org; adkim=s; aspf=s` | DNS only | DMARC policy (start with `p=none` for two weeks, then `quarantine`) |

**Cloudflare settings:** SSL/TLS mode **Full (strict)**; *Always use HTTPS* on; minimum TLS 1.2; Bot Fight
mode on; a **rate-limiting rule** on `/<DJANGO_ADMIN_URL>account/login/` (e.g. 20 requests/minute per IP);
create a **Turnstile** widget for the domain and copy its keys into `.env`.

## 2. Prepare the server (once)

On your own computer:
```bash
ssh-keygen -t ed25519 -C "rlm-deploy" -f ~/.ssh/rlm_deploy        # protect it with a passphrase
scp ~/.ssh/rlm_deploy.pub root@203.0.113.10:/root/deploy_key.pub
scp scripts/server/setup-ubuntu.sh root@203.0.113.10:/root/
ssh root@203.0.113.10 'bash /root/setup-ubuntu.sh rlm /root/deploy_key.pub'
```
The script: updates the system, creates the `rlm` user with key-only SSH, disables root and password login,
enables `ufw` (22/80/443 only), `fail2ban`, automatic security updates (reboot 03:30), installs Docker from
the official repository with log rotation, creates `/srv/rlm` and the nightly backup cron job (02:30).

**Before closing the root session**, open a new terminal and confirm `ssh -i ~/.ssh/rlm_deploy rlm@203.0.113.10`
<!-- pragma: allowlist nextline secret -->
works. Then on the server set a sudo password: `sudo passwd rlm`.

## 3. First deployment

As `rlm` on the server:
```bash
git clone git@github.com:<org>/rlm-website.git /srv/rlm      # deploy key with read-only access
cd /srv/rlm
cp .env.production.example .env && chmod 600 .env
```
Fill in `.env` (every `change-me`). Generate secrets **on the server**:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"        # DJANGO_SECRET_KEY
python3 -c "import secrets; print('staff-' + secrets.token_hex(6) + '/')"   # DJANGO_ADMIN_URL
python3 -c "import secrets; print(secrets.token_urlsafe(24))"        # POSTGRES_PASSWORD, REDIS_PASSWORD (use in the URLs too)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"        # BLIND_INDEX_KEY
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # FIELD_ENCRYPTION_KEYS
```
`TRUSTED_PROXIES`: paste Cloudflare's IPv4 and IPv6 ranges from https://www.cloudflare.com/ips/ separated by
spaces (review every few months).

**Backup key pair** (the private key must not stay on the server):
```bash
docker build -t rlm-backup:prod docker/backup
docker run --rm --entrypoint age-keygen rlm-backup:prod > /tmp/age.key
grep 'public key' /tmp/age.key          # -> put the age1... value in BACKUP_AGE_RECIPIENT
cat /tmp/age.key                        # -> store the WHOLE file in the ministry password manager
shred -u /tmp/age.key
```
Store **`FIELD_ENCRYPTION_KEYS`, `BLIND_INDEX_KEY` and the age private key** in the ministry password manager
now (`docs/BACKUP_RESTORE.md` §1). Without them, backups and personal data cannot be recovered.

Optional off-site copy: create `docker/rclone/rclone.conf` (git-ignored, `chmod 600`) with the bucket
credentials (`docker run --rm -it -v /srv/rlm/docker/rclone:/config/rclone rclone/rclone config`) and set
`BACKUP_REMOTE=<remote>:<bucket>/rlm`. Give that key **write-only / no-delete** permission on the bucket and
set a lifecycle rule (e.g. delete after 90 days) on the bucket itself.

Deploy and create the Founder account:
```bash
scripts/deploy.sh --no-pull
docker compose -f docker-compose.prod.yml exec web python manage.py create_founder --email <founder email> --name "<full name>"
docker compose -f docker-compose.prod.yml exec web python manage.py launch_check
```
Sign in at `https://example.org/<DJANGO_ADMIN_URL>account/login/` and enrol the authenticator.
Then run the launch checklist in `docs/HANDOVER.md` (phase L).

## 4. Updating the site

```bash
cd /srv/rlm && scripts/deploy.sh
```
It pulls the code, builds, runs `check --deploy` (stops on any warning), takes an **encrypted backup**,
migrates, starts the new version and waits for the health check. If the new version is not healthy, it
**rolls back automatically** to the last version that passed (`rlm-web:good`). Database migrations are not
reversed automatically; if one must be undone, restore the pre-deploy backup (`docs/BACKUP_RESTORE.md` §4).

## 5. Monitoring

* Uptime monitor: `https://example.org/healthz/` every 5 minutes, alert the Founder and the technical lead.
* Sentry (optional): set `SENTRY_DSN`; personal data is scrubbed before sending.
* Weekly: `tail /var/log/rlm-backup.log` (a line `backup ok: ...` per night) and `df -h` (disk space).
* Monthly: restore test (`docs/BACKUP_RESTORE.md` §4), review the admin **Audit log**, `docker compose ps`.

## 6. Secret rotation

* `DJANGO_SECRET_KEY`: replace in `.env`, `scripts/deploy.sh --no-pull` (everyone is signed out).
* Database / Redis passwords: change in Postgres (`ALTER USER rlm PASSWORD '...'`) and in `.env`, redeploy.
* Encryption keys: `docs/BACKUP_RESTORE.md` §3.
* After any suspected compromise: `docs/INCIDENT_RESPONSE.md` §3.

## 7. What the production stack enforces

| Rule | How |
|---|---|
| Only the proxy is public | Caddy is the only service with published ports (80/443) |
| DB and Redis private | on the `data` network (`internal: true`): no ports, no internet; Redis needs a password |
| Least privilege containers | read-only root filesystem, non-root user (uid 10001), all capabilities dropped, `no-new-privileges` |
| Real client IP | Caddy trusts only `TRUSTED_PROXIES` (Cloudflare) and passes the visitor IP as `X-Real-IP` |
| Safe uploads | served by Caddy with `nosniff` and a sandbox CSP; `uploads/private/` always 404 |
| Pinned supply chain | images pinned by digest, GitHub Actions by commit SHA, Python deps by hash; Dependabot updates them |
| Limits | CPU/memory limits per container, log rotation (10 MB x 5) |

## Rehearsal results (local PC, 2026-11-16)

Run with the real `scripts/deploy.sh`, `docker-compose.prod.yml`, Caddyfile and backup image, using a
throwaway `.env` with fresh secrets and Cloudflare's test Turnstile keys, on `https://localhost:8443`.

| Check | Result |
|---|---|
| First deploy (build, `check --deploy`, migrate, start, health) | passed |
| `check --deploy` blocks an unsafe setting (HSTS disabled) | deploy stopped, as designed |
| HTTPS + HTTP→HTTPS redirect; HSTS, CSP (nonces), X-Frame-Options, COOP, Referrer-Policy, Permissions-Policy; no `Server` header | passed |
| Only Caddy publishes ports; `db`/`redis` unresolvable from the proxy; `data` network has no internet; Redis rejects unauthenticated clients | passed |
| App containers non-root and read-only | passed (uid 10001, writes refused) |
| Upload through the app, served by Caddy with sandbox CSP + `nosniff`; `uploads/private` 404; `/admin/` 404 | passed |
| Encrypted backup (age), checksum, restore into a scratch DB with the private key; refusal to overwrite the live DB | passed |
| Broken release → detected → automatic rollback to last good version, site stays up | passed (after two fixes below) |

Problems the rehearsal found and fixed: the media volume could be created root-owned (new `media-init`
step); Caddy could not read uploads saved as `0640` (Caddy joins the app group, read-only); the deploy
script aborted before rolling back, and rolled back to a broken image (now rolls back to the last
**known-good** image).
