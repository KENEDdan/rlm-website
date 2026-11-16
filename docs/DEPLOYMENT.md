# Deployment (plan, NOT done yet)

> **Current state:** the site runs only on a local PC. Nothing is deployed, there is no GitHub repository
> yet, and no server, domain or DNS exists. This document records what phase K will build so nothing is
> forgotten. Do not follow it as a runbook until phase K turns it into one.

## Order of work (when the ministry is ready)

1. **Ownership first.** The ministry (not a developer) creates and owns: GitHub organisation/repository,
   domain at a registrar, Cloudflare account, VPS hosting account, transactional email account, off-site
   backup storage. Founder plus one deputy as owners, 2FA on every account.
2. **Push the code** to the private GitHub repository. CI (`.github/workflows/ci.yml`) then runs lint,
   bandit, pip-audit, detect-secrets, tests (85% coverage gate) and `check --deploy` on every push.
   Enable Dependabot and secret scanning.
3. **Server hardening:** non-root deploy user, SSH keys only, password login off, `ufw` 22/80/443,
   fail2ban, unattended security upgrades.
4. **Production stack** `docker-compose.prod.yml`: Caddy (automatic HTTPS) is the only service publishing
   ports; web (gunicorn, `target: prod`), worker (Celery + beat), Postgres, Redis on an internal network;
   read-only containers, resource limits, healthchecks, restart policies, log rotation.
5. **Secrets:** generate `.env` **on the server** (never on a laptop, never in Git), `chmod 600`.
   Required: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `SITE_URL`,
   `DJANGO_ADMIN_URL`, database password, `FIELD_ENCRYPTION_KEYS`, `BLIND_INDEX_KEY`, SMTP credentials,
   `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY`. Copy the encryption keys to the ministry's safe storage
   (`docs/BACKUP_RESTORE.md` §1) **before** any real data arrives.
6. **Deploy script:** build → migrate (one-off container) → collectstatic is baked into the image →
   healthcheck → switch → roll back on failure.
7. **Backups:** nightly encrypted Postgres + media to off-site storage, 30-day retention, tested restore
   (`docs/BACKUP_RESTORE.md` §4).
8. **Email:** send from the ministry domain with SPF, DKIM and DMARC records.
9. **Monitoring:** uptime check on `/healthz/`, Sentry with PII scrubbing (`SENTRY_DSN`).
10. **Launch checklist** (phase L handover): privacy policy reviewed, real logo/photos/social links, officers
    confirmed, giving settings entered by Finance, every form tested, restore tested.

## Requirements already identified (from the phase I audit and local testing)

| # | Requirement | Why |
|---|---|---|
| 1 | Caddy sets `X-Real-IP` to the **real visitor IP**; behind Cloudflare use `trusted_proxies` with Cloudflare's ranges and `CF-Connecting-IP` | otherwise rate limits and lockouts see one Cloudflare IP for everyone |
| 2 | Caddy serves `/uploads/` itself with `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox; default-src 'none'`, long cache, no listing, nothing under `uploads/private/` | Django serves media only in DEBUG |
| 3 | `GUNICORN_FORWARDED_ALLOW_IPS` = the Caddy container address, not `*` | trust proxy headers only from Caddy |
| 4 | Turnstile keys set; `manage.py check --deploy` must show no `rlm.E001`/`rlm.W001` | public forms fail closed without them |
| 5 | Pin GitHub Actions to commit SHAs and images to digests | supply chain (audit R-5) |
| 6 | Use the image's own `HEALTHCHECK` (`docker/healthcheck.py`) | it sends an allowed Host header; a plain request to 127.0.0.1 is rejected by `ALLOWED_HOSTS` |

A local rehearsal of items 1–2 (Caddy in front of the production image, used for the Lighthouse run in phase
J) worked; its Caddyfile is the starting point:

```caddyfile
:80 {
	encode zstd gzip
	handle_path /uploads/* {
		root * /media
		header X-Content-Type-Options nosniff
		header Content-Security-Policy "sandbox; default-src 'none'"
		header Cache-Control "public, max-age=2592000"
		file_server
	}
	reverse_proxy web:8000 {
		header_up X-Real-IP {remote_host}
	}
}
```
(In production: the real domain instead of `:80` for automatic HTTPS, plus the Cloudflare IP settings.)
